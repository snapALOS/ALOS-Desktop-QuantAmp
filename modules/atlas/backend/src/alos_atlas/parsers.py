"""Language extractors for AlosAtlas."""

from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Iterable

from .models import Edge, FileRecord, Node, ParseResult, RepositoryProfile
from .storage import node_id


JS_CALL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "function",
    "return",
    "typeof",
    "new",
    "class",
    "import",
    "export",
}


def make_node(
    repo_id: str,
    type_: str,
    name: str,
    path: str,
    language: str,
    start_line: int | None = None,
    end_line: int | None = None,
    signature: str | None = None,
    content_hash: str | None = None,
    confidence: float = 1.0,
) -> Node:
    node = Node(
        repo_id=repo_id,
        type=type_,
        name=name,
        path=path,
        start_line=start_line,
        end_line=end_line,
        language=language,
        signature=signature,
        content_hash=content_hash,
        confidence=confidence,
    )
    node.id = node_id(node)
    return node


def make_edge(
    repo_id: str,
    source: Node,
    target: Node,
    type_: str,
    reason: str,
    confidence: float,
    source_line: int | None = None,
) -> Edge:
    return Edge(
        repo_id=repo_id,
        source_id=source.id or node_id(source),
        target_id=target.id or node_id(target),
        type=type_,
        confidence=confidence,
        reason=reason,
        source_path=source.path,
        source_line=source_line,
    )


class AlosAtlasParser:
    def __init__(self, profile: RepositoryProfile) -> None:
        self.profile = profile

    def parse(self, record: FileRecord) -> ParseResult:
        path = Path(record.absolute_path)
        result = ParseResult()
        file_node = make_node(
            record.repo_id,
            "File",
            record.path,
            record.path,
            record.language,
            1,
            None,
            f"{record.file_class}:{record.language}",
            record.content_hash,
            1.0,
        )
        result.nodes.append(file_node)

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result.warnings.append(f"Failed reading {record.path}: {exc}")
            return result

        if record.language == "python":
            self._parse_python(record, text, file_node, result)
        elif record.language in {"javascript", "typescript", "tsx"}:
            if not self._parse_js_ts_ast_bridge(record, file_node, result):
                self._parse_js_ts(record, text, file_node, result)
        elif record.language == "json":
            self._parse_json(record, text, file_node, result)
        elif record.language == "toml":
            self._parse_toml_like(record, text, file_node, result)
        elif record.language == "yaml":
            self._parse_yaml_like(record, text, file_node, result)
        elif record.language == "markdown":
            self._parse_markdown(record, text, file_node, result)
        elif record.language == "shell":
            self._parse_shell(record, text, file_node, result)
        elif record.language in {"rust", "go", "java", "csharp", "sql", "qml"}:
            self._parse_extended_language(record, text, file_node, result)
        else:
            self._parse_text_config(record, text, file_node, result)

        return result

    def _append_symbol(self, result: ParseResult, file_node: Node, node: Node, edge_type: str = "DEFINES") -> None:
        result.nodes.append(node)
        result.edges.append(
            make_edge(
                file_node.repo_id,
                file_node,
                node,
                edge_type,
                f"{file_node.path} {edge_type.lower()} {node.type} {node.name}",
                node.confidence,
                node.start_line,
            )
        )

    def _reference_node(self, result: ParseResult, file_node: Node, type_: str, name: str, line: int, edge_type: str, confidence: float, reason: str, signature: str | None = None) -> Node:
        node = make_node(
            file_node.repo_id,
            type_,
            name,
            file_node.path,
            file_node.language or "unknown",
            line,
            line,
            signature,
            file_node.content_hash,
            confidence,
        )
        result.nodes.append(node)
        result.edges.append(make_edge(file_node.repo_id, file_node, node, edge_type, reason, confidence, line))
        return node

    def _parse_python(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            result.warnings.append(f"Python parse failed for {record.path}: {exc}")
            return

        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        class_nodes: dict[ast.AST, Node] = {}

        for child in tree.body:
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                self._python_import(child, file_node, result)
            elif isinstance(child, ast.ClassDef):
                class_node = make_node(
                    record.repo_id,
                    "Class",
                    child.name,
                    record.path,
                    "python",
                    child.lineno,
                    getattr(child, "end_lineno", child.lineno),
                    f"class {child.name}",
                    record.content_hash,
                    1.0,
                )
                class_nodes[child] = class_node
                self._append_symbol(result, file_node, class_node)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_node = self._python_function_node(record, child, "Function")
                self._append_symbol(result, file_node, function_node)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_node = class_nodes.get(node)
                if not class_node:
                    continue
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_node = self._python_function_node(record, item, "Method", owner=node.name)
                        self._append_symbol(result, file_node, method_node)
                        result.edges.append(
                            make_edge(
                                record.repo_id,
                                class_node,
                                method_node,
                                "CONTAINS",
                                f"class {node.name} contains method {item.name}",
                                1.0,
                                item.lineno,
                            )
                        )
            elif isinstance(node, (ast.Import, ast.ImportFrom)) and parents.get(node) is not tree:
                self._python_import(node, file_node, result)
            elif isinstance(node, ast.Call):
                call_name = self._python_call_name(node.func)
                if call_name:
                    self._reference_node(
                        result,
                        file_node,
                        "Call",
                        call_name,
                        getattr(node, "lineno", 1),
                        "CALLS",
                        0.6,
                        f"static Python call reference {call_name}",
                    )
            elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                test_node = make_node(
                    record.repo_id,
                    "TestCase",
                    node.name,
                    record.path,
                    "python",
                    node.lineno,
                    getattr(node, "end_lineno", node.lineno),
                    f"def {node.name}",
                    record.content_hash,
                    1.0,
                )
                self._append_symbol(result, file_node, test_node)

        for match in re.finditer(r"os\.environ(?:\.get)?\(\s*['\"]([^'\"]+)['\"]|os\.getenv\(\s*['\"]([^'\"]+)['\"]", text):
            name = match.group(1) or match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(
                result,
                file_node,
                "EnvironmentVariable",
                name,
                line,
                "USES_ENV",
                0.8,
                f"Python environment variable reference {name}",
            )

        for decorator in re.finditer(r"@(?:\w+\.)?(?:route|get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", text):
            route = decorator.group(1)
            line = text.count("\n", 0, decorator.start()) + 1
            self._reference_node(
                result,
                file_node,
                "Route",
                route,
                line,
                "HANDLES",
                0.8,
                f"Python route decorator handles {route}",
            )

    def _python_function_node(self, record: FileRecord, node: ast.FunctionDef | ast.AsyncFunctionDef, type_: str, owner: str | None = None) -> Node:
        args = [arg.arg for arg in node.args.args]
        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        name = f"{owner}.{node.name}" if owner else node.name
        signature = f"{async_prefix}def {name}({', '.join(args)})"
        return make_node(
            record.repo_id,
            type_,
            name,
            record.path,
            "python",
            node.lineno,
            getattr(node, "end_lineno", node.lineno),
            signature,
            record.content_hash,
            1.0,
        )

    def _python_import(self, node: ast.Import | ast.ImportFrom, file_node: Node, result: ParseResult) -> None:
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            module = "." * node.level + (node.module or "")
            modules = [module.rstrip(".") or alias.name for alias in node.names]
        for module in modules:
            self._reference_node(
                result,
                file_node,
                "Import",
                module,
                getattr(node, "lineno", 1),
                "IMPORTS",
                1.0,
                f"Python import {module}",
                signature="python",
            )

    def _python_call_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._python_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def _parse_js_ts(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        for match in re.finditer(r"import\s+(?:[^'\"\n]+?\s+from\s+)?['\"]([^'\"]+)['\"]", text):
            module = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "Import", module, line, "IMPORTS", 1.0, f"ES import {module}", "js")

        for match in re.finditer(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
            module = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "Import", module, line, "IMPORTS", 0.9, f"CommonJS require {module}", "js")

        function_patterns = [
            (r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", "Function", 1.0),
            (r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", "Function", 0.8),
            (r"(?:export\s+)?(?:const|let|var)\s+([A-Z][A-Za-z0-9_$]*)\s*=\s*(?:React\.)?(?:memo\()? ?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", "Component", 0.8),
        ]
        for pattern, type_, confidence in function_patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1)
                line = text.count("\n", 0, match.start()) + 1
                node_type = "Component" if name[:1].isupper() and record.language == "tsx" else type_
                symbol = make_node(
                    record.repo_id,
                    node_type,
                    name,
                    record.path,
                    record.language,
                    line,
                    line,
                    match.group(0).strip(),
                    record.content_hash,
                    confidence,
                )
                self._append_symbol(result, file_node, symbol)

        for match in re.finditer(r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", text):
            name = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            symbol = make_node(record.repo_id, "Class", name, record.path, record.language, line, line, match.group(0), record.content_hash, 1.0)
            self._append_symbol(result, file_node, symbol)

        for match in re.finditer(r"\b(use[A-Z][A-Za-z0-9_$]*)\s*\(", text):
            hook = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "Hook", hook, line, "CALLS", 0.6, f"React hook call {hook}")

        route_pattern = r"\b(?:app|router)\.(get|post|put|delete|patch|use)\(\s*['\"]([^'\"]+)['\"]"
        for match in re.finditer(route_pattern, text):
            method, route = match.groups()
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "Route", f"{method.upper()} {route}", line, "HANDLES", 0.8, f"Express-style route {method.upper()} {route}")

        fetch_pattern = r"\b(?:fetch|axios\.(?:get|post|put|delete|patch))\(\s*['\"`]([^'\"`]+)['\"`]"
        for match in re.finditer(fetch_pattern, text):
            endpoint = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "Endpoint", endpoint, line, "FETCHES", 0.7, f"UI/API fetch to {endpoint}")

        env_pattern = r"(?:process\.env\.|import\.meta\.env\.)([A-Z0-9_]+)"
        for match in re.finditer(env_pattern, text):
            env_name = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "EnvironmentVariable", env_name, line, "USES_ENV", 0.8, f"JS environment variable {env_name}")

        for match in re.finditer(r"\b(?:describe|it|test)\(\s*['\"`]([^'\"`]+)['\"`]", text):
            test_name = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            test_node = make_node(record.repo_id, "TestCase", test_name, record.path, record.language, line, line, match.group(0), record.content_hash, 0.9)
            self._append_symbol(result, file_node, test_node)

        for match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", text):
            name = match.group(1)
            if name in JS_CALL_KEYWORDS:
                continue
            line = text.count("\n", 0, match.start()) + 1
            self._reference_node(result, file_node, "Call", name, line, "CALLS", 0.4, f"heuristic JS/TS call reference {name}")

    def _parse_js_ts_ast_bridge(self, record: FileRecord, file_node: Node, result: ParseResult) -> bool:
        bridge = Path(__file__).with_name("js_parser_bridge.js")
        if not bridge.exists():
            return False
        try:
            completed = subprocess.run(
                [
                    "node",
                    str(bridge),
                    str(self.profile.path),
                    record.absolute_path,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if completed.returncode != 0 or not completed.stdout.strip():
            return False
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return False
        if not payload.get("ok"):
            return False

        added = False
        for item in payload.get("records", []):
            type_ = str(item.get("type") or "Symbol")
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            line = int(item.get("line") or 1)
            edge = str(item.get("edge") or "DEFINES")
            confidence = float(item.get("confidence") or 0.8)
            signature = item.get("signature")
            node = make_node(
                record.repo_id,
                type_,
                name,
                record.path,
                record.language,
                line,
                line,
                str(signature) if signature else None,
                record.content_hash,
                confidence,
            )
            if edge == "DEFINES":
                self._append_symbol(result, file_node, node)
            else:
                result.nodes.append(node)
                result.edges.append(
                    make_edge(
                        record.repo_id,
                        file_node,
                        node,
                        edge,
                        f"TypeScript AST {edge.lower()} {name}",
                        confidence,
                        line,
                    )
                )
            added = True
        return added

    def _parse_json(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            result.warnings.append(f"JSON parse failed for {record.path}: {exc}")
            return
        for key in self._walk_keys(data):
            config = make_node(record.repo_id, "ConfigKey", key, record.path, "json", 1, 1, key, record.content_hash, 1.0)
            self._append_symbol(result, file_node, config, "READS_CONFIG")

    def _walk_keys(self, data: object, prefix: str = "") -> Iterable[str]:
        if isinstance(data, dict):
            for key, value in data.items():
                current = f"{prefix}.{key}" if prefix else str(key)
                yield current
                yield from self._walk_keys(value, current)
        elif isinstance(data, list):
            for index, value in enumerate(data[:20]):
                yield from self._walk_keys(value, f"{prefix}[{index}]")

    def _parse_toml_like(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        for index, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                name = stripped.strip("[]")
            elif "=" in stripped:
                name = stripped.split("=", 1)[0].strip()
            else:
                continue
            node = make_node(record.repo_id, "ConfigKey", name, record.path, record.language, index, index, stripped, record.content_hash, 0.8)
            self._append_symbol(result, file_node, node, "READS_CONFIG")

    def _parse_yaml_like(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        for index, line in enumerate(text.splitlines(), start=1):
            match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*:", line)
            if not match:
                continue
            name = match.group(1)
            node = make_node(record.repo_id, "ConfigKey", name, record.path, record.language, index, index, line.strip(), record.content_hash, 0.7)
            self._append_symbol(result, file_node, node, "READS_CONFIG")

    def _parse_markdown(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        for index, line in enumerate(text.splitlines(), start=1):
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                level = len(match.group(1))
                heading = match.group(2).strip()
                node = make_node(record.repo_id, "MarkdownHeading", heading, record.path, "markdown", index, index, f"h{level}", record.content_hash, 1.0)
                self._append_symbol(result, file_node, node, "CONTAINS")

    def _parse_shell(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        for index, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                parts = shlex.split(stripped)
            except ValueError:
                parts = stripped.split()
            if not parts:
                continue
            command = parts[0]
            node = make_node(record.repo_id, "CLICommand", command, record.path, "shell", index, index, stripped, record.content_hash, 0.6)
            self._append_symbol(result, file_node, node, "CALLS")

    def _parse_text_config(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        for index, line in enumerate(text.splitlines(), start=1):
            if "=" in line and not line.lstrip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                if key:
                    node = make_node(record.repo_id, "ConfigKey", key, record.path, record.language, index, index, line.strip(), record.content_hash, 0.5)
                    self._append_symbol(result, file_node, node, "READS_CONFIG")

    def _parse_extended_language(self, record: FileRecord, text: str, file_node: Node, result: ParseResult) -> None:
        patterns_by_language = {
            "rust": [
                (r"\b(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "Function", 0.9),
                (r"\b(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)", "Class", 0.8),
                (r"\b(?:pub\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)", "DataShape", 0.8),
                (r"\buse\s+([^;]+);", "Import", 0.9, "IMPORTS"),
            ],
            "go": [
                (r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", "Function", 0.9),
                (r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b", "DataShape", 0.8),
                (r"\bimport\s+(?:\(\s*)?[\"`]([^\"`]+)[\"`]", "Import", 0.8, "IMPORTS"),
            ],
            "java": [
                (r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", "Class", 0.9),
                (r"\b(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>,\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "Method", 0.6),
                (r"\bimport\s+([^;]+);", "Import", 0.9, "IMPORTS"),
            ],
            "csharp": [
                (r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", "Class", 0.9),
                (r"\b(?:public|private|protected|internal)?\s*(?:static\s+)?[A-Za-z0-9_<>,\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "Method", 0.6),
                (r"\busing\s+([^;]+);", "Import", 0.9, "IMPORTS"),
            ],
            "sql": [
                (r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", "DataShape", 0.8),
                (r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([A-Za-z0-9_.\"]+)", "Function", 0.8),
            ],
            "qml": [
                (r"^\s*([A-Z][A-Za-z0-9_]*)\s*\{", "Component", 0.7),
                (r"\bid:\s*([A-Za-z_][A-Za-z0-9_]*)", "Symbol", 0.7),
                (r"\bon([A-Z][A-Za-z0-9_]*)\s*:", "UIAction", 0.7),
            ],
        }
        for pattern_info in patterns_by_language.get(record.language, []):
            pattern, type_, confidence, *edge_override = pattern_info
            edge = edge_override[0] if edge_override else "DEFINES"
            flags = re.IGNORECASE if record.language == "sql" else re.MULTILINE
            for match in re.finditer(pattern, text, flags):
                name = match.group(1).strip()
                line = text.count("\n", 0, match.start()) + 1
                node = make_node(
                    record.repo_id,
                    type_,
                    name,
                    record.path,
                    record.language,
                    line,
                    line,
                    match.group(0).strip(),
                    record.content_hash,
                    float(confidence),
                )
                if edge == "DEFINES":
                    self._append_symbol(result, file_node, node)
                else:
                    result.nodes.append(node)
                    result.edges.append(make_edge(record.repo_id, file_node, node, edge, f"{record.language} {edge.lower()} {name}", float(confidence), line))
