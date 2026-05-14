#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

const repoRoot = process.argv[2];
const filePath = process.argv[3];

function loadTypescript() {
  const repoRequire = createRequire(path.join(repoRoot, 'package.json'));
  try {
    return repoRequire('typescript');
  } catch (_err) {
    return require('typescript');
  }
}

function lineOf(sourceFile, pos) {
  return sourceFile.getLineAndCharacterOfPosition(pos).line + 1;
}

function startOf(node) {
  return typeof node.getStart === 'function' ? node.getStart(sourceFile) : (node.pos || 0);
}

function propName(node) {
  if (!node) return '';
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isPropertyAccessExpression(node)) {
    const left = propName(node.expression);
    return left ? `${left}.${node.name.text}` : node.name.text;
  }
  return node.getText(sourceFile);
}

function stringArg(node, index = 0) {
  const arg = node.arguments && node.arguments[index];
  if (!arg) return '';
  if (ts.isStringLiteralLike(arg) || arg.kind === ts.SyntaxKind.NoSubstitutionTemplateLiteral) {
    return arg.text;
  }
  return '';
}

let ts;
try {
  ts = loadTypescript();
  const text = fs.readFileSync(filePath, 'utf8');
  var sourceFile = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const records = [];
  const ext = path.extname(filePath).toLowerCase();

  function add(record) {
    records.push(record);
  }

  function symbolKind(name, fallback = 'Function') {
    if (/^use[A-Z]/.test(name)) return 'Hook';
    if ((ext === '.tsx' || ext === '.jsx') && /^[A-Z]/.test(name)) return 'Component';
    return fallback;
  }

  function visit(node) {
    const line = lineOf(sourceFile, startOf(node));

    if (ts.isImportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteralLike(node.moduleSpecifier)) {
      add({ type: 'Import', name: node.moduleSpecifier.text, line, edge: 'IMPORTS', confidence: 1.0, signature: 'typescript import' });
    }

    if (ts.isFunctionDeclaration(node) && node.name) {
      const name = node.name.text;
      add({ type: symbolKind(name), name, line, edge: 'DEFINES', confidence: 1.0, signature: node.getText(sourceFile).split('{')[0].trim() });
    }

    if (ts.isClassDeclaration(node) && node.name) {
      add({ type: 'Class', name: node.name.text, line, edge: 'DEFINES', confidence: 1.0, signature: `class ${node.name.text}` });
    }

    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const name = node.name.text;
      if (
        ts.isArrowFunction(node.initializer) ||
        ts.isFunctionExpression(node.initializer) ||
        ts.isCallExpression(node.initializer)
      ) {
        add({ type: symbolKind(name), name, line, edge: 'DEFINES', confidence: 0.9, signature: node.getText(sourceFile).split('=>')[0].trim() });
      }
    }

    if (ts.isCallExpression(node)) {
      const callName = propName(node.expression);
      const first = stringArg(node, 0);

      if (/^(app|router)\.(get|post|put|delete|patch|use)$/.test(callName) && first) {
        const method = callName.split('.').pop().toUpperCase();
        add({ type: 'Route', name: `${method} ${first}`, line, edge: 'HANDLES', confidence: 0.9, signature: callName });
      } else if ((callName === 'fetch' || /^axios\.(get|post|put|delete|patch)$/.test(callName)) && first) {
        add({ type: 'Endpoint', name: first, line, edge: 'FETCHES', confidence: 0.85, signature: callName });
      } else if (/^(describe|it|test)$/.test(callName) && first) {
        add({ type: 'TestCase', name: first, line, edge: 'DEFINES', confidence: 0.95, signature: callName });
      } else if (/^use[A-Z]/.test(callName)) {
        add({ type: 'Hook', name: callName, line, edge: 'CALLS', confidence: 0.8, signature: callName });
      } else if (callName && !['if', 'for', 'while', 'switch'].includes(callName)) {
        add({ type: 'Call', name: callName, line, edge: 'CALLS', confidence: 0.55, signature: callName });
      }
    }

    if (ts.isPropertyAccessExpression(node)) {
      const text = propName(node);
      const envMatch = text.match(/^(process\.env|import\.meta\.env)\.([A-Z0-9_]+)$/);
      if (envMatch) {
        add({ type: 'EnvironmentVariable', name: envMatch[2], line, edge: 'USES_ENV', confidence: 0.9, signature: text });
      }
    }

    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  process.stdout.write(JSON.stringify({ ok: true, records }));
} catch (err) {
  process.stdout.write(JSON.stringify({ ok: false, error: err.message }));
}
