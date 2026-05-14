#!/usr/bin/env node
/**
 * ALOS Scout QA audit harness.
 *
 * Runs release-oriented smoke checks against the live ALOS backend, records each
 * step into Scout, and writes a real CSV suitable for triage. If a frontend URL
 * is provided, the script can also launch/attach to Chrome via the Chrome
 * DevTools Protocol and crawl visible buttons/links without adding Playwright as
 * a project dependency.
 */

import { spawn } from 'node:child_process'
import { createWriteStream, existsSync } from 'node:fs'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { randomUUID } from 'node:crypto'
import net from 'node:net'

const DEFAULT_BASE_URL = 'http://localhost:8000'
const DEFAULT_OUT_DIR = 'qa/scout-audits'
const DEFAULT_TIMEOUT_MS = 10_000
const DANGEROUS_LABEL_RE = /\b(delete|remove|archive|revoke|clear|reset|send|execute|run|apply|publish|stop|cancel|approve|deny|logout|sign out|bootstrap|original admin)\b/i
const MODULES = ['Chat', 'Forge', 'Current', 'Atlas', 'Chamber', 'Scout', 'Settings']
const MODULE_NAV_LABELS = new Set([...MODULES, 'Extensions'])
const TELEMETRY_ROW_LABEL_RE = /^(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s/i

const CSV_HEADERS = [
  'run_id',
  'step_id',
  'timestamp',
  'module',
  'layer',
  'feature',
  'action',
  'target',
  'status',
  'severity',
  'duration_ms',
  'http_method',
  'http_url',
  'http_status',
  'message',
  'error_type',
  'scout_error_count',
  'scout_warning_count',
  'scout_event_ids',
  'details_json',
]

function usage() {
  return `
Usage:
  node scripts/scout_audit.mjs --api-key alos_... [options]

Core options:
  --base-url URL              Backend URL. Default: ${DEFAULT_BASE_URL}
  --api-key KEY               ALOS API key. Also reads ALOS_API_KEY.
  --out PATH                  CSV output path. Default: ${DEFAULT_OUT_DIR}/scout-audit-<run>.csv
  --jsonl PATH                Optional JSONL event output path.
  --timeout-ms N              Per-request timeout. Default: ${DEFAULT_TIMEOUT_MS}
  --write-checks              Exercise safe create/update/delete flows.

Frontend crawl options:
  --frontend-url URL          Browser URL to crawl, for example http://localhost:5173
  --chrome-path PATH          Chrome/Chromium executable path.
  --chrome-debug-port N       Attach to an existing Chrome debugging port.
  --max-ui-actions N          Max visible UI actions per module/view. Default: 80
  --include-dangerous         Allow UI clicks with destructive-looking labels.
  --keep-browser              Leave the launched Chrome profile/browser running.
  --no-ui                     Disable UI crawl even if frontend-url is set.

Notes:
  - The backend/API audit works with stock Node and the running ALOS backend.
  - The UI audit uses Chrome DevTools Protocol directly; no Playwright install is required.
  - The script records every audit step to Scout using source "qa.audit".
`
}

function parseArgs(argv) {
  const args = {
    baseUrl: process.env.ALOS_BASE_URL || DEFAULT_BASE_URL,
    apiKey: process.env.ALOS_API_KEY || process.env.ALOS_AUDIT_API_KEY || '',
    frontendUrl: '',
    out: '',
    jsonl: '',
    timeoutMs: DEFAULT_TIMEOUT_MS,
    writeChecks: false,
    includeDangerous: false,
    noUi: false,
    maxUiActions: 80,
    chromePath: '',
    chromeDebugPort: 0,
    keepBrowser: false,
  }

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    const next = () => {
      if (i + 1 >= argv.length) throw new Error(`Missing value for ${arg}`)
      i += 1
      return argv[i]
    }
    if (arg === '--help' || arg === '-h') {
      console.log(usage())
      process.exit(0)
    } else if (arg === '--base-url') args.baseUrl = next()
    else if (arg === '--api-key') args.apiKey = next()
    else if (arg === '--frontend-url') args.frontendUrl = next()
    else if (arg === '--out') args.out = next()
    else if (arg === '--jsonl') args.jsonl = next()
    else if (arg === '--timeout-ms') args.timeoutMs = Number(next())
    else if (arg === '--write-checks') args.writeChecks = true
    else if (arg === '--include-dangerous') args.includeDangerous = true
    else if (arg === '--no-ui') args.noUi = true
    else if (arg === '--max-ui-actions') args.maxUiActions = Number(next())
    else if (arg === '--chrome-path') args.chromePath = next()
    else if (arg === '--chrome-debug-port') args.chromeDebugPort = Number(next())
    else if (arg === '--keep-browser') args.keepBrowser = true
    else throw new Error(`Unknown argument: ${arg}`)
  }

  args.baseUrl = args.baseUrl.replace(/\/+$/, '')
  if (!Number.isFinite(args.timeoutMs) || args.timeoutMs < 1000) args.timeoutMs = DEFAULT_TIMEOUT_MS
  if (!Number.isFinite(args.maxUiActions) || args.maxUiActions < 1) args.maxUiActions = 80
  return args
}

function csvEscape(value) {
  const text = value === undefined || value === null ? '' : String(value)
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`
  return text
}

function jsonStable(value) {
  try {
    return JSON.stringify(value ?? {})
  } catch (err) {
    return JSON.stringify({ serialization_error: String(err) })
  }
}

function summarize(value, depth = 0) {
  if (value === null || value === undefined) return value
  if (typeof value === 'string') return value.length > 1_000 ? `${value.slice(0, 1_000)}…` : value
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (depth >= 4) return `[${Array.isArray(value) ? 'array' : 'object'}]`
  if (Array.isArray(value)) {
    const items = value.slice(0, 8).map((item) => summarize(item, depth + 1))
    if (value.length > items.length) items.push(`… ${value.length - items.length} more`)
    return items
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value)
    const out = {}
    for (const [key, item] of entries.slice(0, 40)) out[key] = summarize(item, depth + 1)
    if (entries.length > 40) out.__truncated_keys = entries.length - 40
    return out
  }
  return String(value)
}

function timestampForFile(date = new Date()) {
  return date.toISOString().replace(/[:.]/g, '-')
}

function parseScoutTime(value) {
  if (!value) return 0
  const normalized = String(value).includes('T')
    ? String(value)
    : `${String(value).replace(' ', 'T')}Z`
  const time = Date.parse(normalized)
  return Number.isFinite(time) ? time : 0
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms))
}

async function getFreePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolve(port))
    })
  })
}

class AuditRunner {
  constructor(args) {
    this.args = args
    this.runId = `scout-audit-${randomUUID()}`
    this.rows = []
    this.jsonlStream = null
    this.csvPath = args.out || path.join(DEFAULT_OUT_DIR, `scout-audit-${timestampForFile()}-${this.runId.slice(-8)}.csv`)
    this.jsonlPath = args.jsonl || ''
  }

  async init() {
    await mkdir(path.dirname(this.csvPath), { recursive: true })
    await writeFile(this.csvPath, `${CSV_HEADERS.join(',')}\n`, 'utf8')
    if (this.jsonlPath) {
      await mkdir(path.dirname(this.jsonlPath), { recursive: true })
      this.jsonlStream = createWriteStream(this.jsonlPath, { flags: 'w' })
    }
  }

  close() {
    if (this.jsonlStream) this.jsonlStream.end()
  }

  authHeaders(extra = {}) {
    const headers = { ...extra }
    if (this.args.apiKey) headers.Authorization = `Bearer ${this.args.apiKey}`
    return headers
  }

  async fetchJson(method, target, body, { noAuth = false } = {}) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.args.timeoutMs)
    const headers = body === undefined
      ? this.authHeaders()
      : this.authHeaders({ 'Content-Type': 'application/json' })
    if (noAuth) delete headers.Authorization
    try {
      const response = await fetch(target, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })
      const text = await response.text()
      let payload = null
      if (text) {
        try { payload = JSON.parse(text) } catch { payload = text }
      }
      return { response, payload, text }
    } finally {
      clearTimeout(timer)
    }
  }

  async recordScout(level, eventType, message, module, payload = {}) {
    if (!this.args.apiKey) return null
    try {
      const target = `${this.args.baseUrl}/api/scout/events`
      const { response, payload: event } = await this.fetchJson('POST', target, {
        source: 'qa.audit',
        level,
        event_type: eventType,
        message,
        module,
        run_id: this.runId,
        payload,
      })
      return response.ok ? event : null
    } catch {
      return null
    }
  }

  async scoutEventsSince(startedAtMs) {
    if (!this.args.apiKey) return []
    try {
      const target = `${this.args.baseUrl}/api/scout/events?limit=2000`
      const { response, payload } = await this.fetchJson('GET', target, undefined)
      if (!response.ok || !payload || !Array.isArray(payload.events)) return []
      return payload.events.filter((event) => parseScoutTime(event.created_at) >= startedAtMs)
    } catch {
      return []
    }
  }

  async writeRow(row) {
    const complete = {
      run_id: this.runId,
      step_id: row.step_id || randomUUID(),
      timestamp: row.timestamp || new Date().toISOString(),
      module: row.module || '',
      layer: row.layer || '',
      feature: row.feature || '',
      action: row.action || '',
      target: row.target || '',
      status: row.status || '',
      severity: row.severity || '',
      duration_ms: row.duration_ms ?? '',
      http_method: row.http_method || '',
      http_url: row.http_url || '',
      http_status: row.http_status ?? '',
      message: row.message || '',
      error_type: row.error_type || '',
      scout_error_count: row.scout_error_count ?? '',
      scout_warning_count: row.scout_warning_count ?? '',
      scout_event_ids: Array.isArray(row.scout_event_ids) ? row.scout_event_ids.join('|') : (row.scout_event_ids || ''),
      details_json: typeof row.details_json === 'string' ? row.details_json : jsonStable(row.details_json || {}),
    }
    const line = CSV_HEADERS.map((header) => csvEscape(complete[header])).join(',')
    await writeFile(this.csvPath, `${line}\n`, { flag: 'a' })
    if (this.jsonlStream) this.jsonlStream.write(`${JSON.stringify(complete)}\n`)
    this.rows.push(complete)
  }

  async step(meta, fn) {
    const stepId = randomUUID()
    const startedAt = Date.now()
    await this.recordScout('info', 'audit.step.start', `${meta.layer}:${meta.module}:${meta.feature}`, meta.module, {
      step_id: stepId,
      action: meta.action,
      target: meta.target,
    })

    try {
      const result = await fn()
      const scoutEvents = await this.scoutEventsSince(startedAt)
      const externalEvents = scoutEvents.filter((event) => event.source !== 'qa.audit')
      const errors = externalEvents.filter((event) => ['error', 'critical'].includes(String(event.level).toLowerCase()))
      const warnings = externalEvents.filter((event) => ['warn', 'warning'].includes(String(event.level).toLowerCase()))
      const status = result.status || (errors.length ? 'fail' : warnings.length ? 'warn' : 'pass')
      const severity = result.severity || (errors.length ? 'high' : warnings.length ? 'medium' : 'info')
      const message = result.message || (errors[0]?.message ?? warnings[0]?.message ?? 'ok')
      const row = {
        ...meta,
        step_id: stepId,
        status,
        severity,
        duration_ms: Date.now() - startedAt,
        http_status: result.httpStatus,
        message,
        error_type: result.errorType,
        scout_error_count: errors.length,
        scout_warning_count: warnings.length,
        scout_event_ids: externalEvents.slice(0, 25).map((event) => event.id),
        details_json: summarize({ ...(result.details || {}), scout_events: externalEvents.slice(0, 20) }),
      }
      await this.writeRow(row)
      await this.recordScout(status === 'pass' ? 'info' : status === 'warn' ? 'warning' : 'error', 'audit.step.result', message, meta.module, row)
      return result.value
    } catch (err) {
      const scoutEvents = await this.scoutEventsSince(startedAt)
      const externalEvents = scoutEvents.filter((event) => event.source !== 'qa.audit')
      const row = {
        ...meta,
        step_id: stepId,
        status: 'fail',
        severity: 'high',
        duration_ms: Date.now() - startedAt,
        message: err?.message || String(err),
        error_type: err?.name || 'Error',
        scout_error_count: externalEvents.filter((event) => ['error', 'critical'].includes(String(event.level).toLowerCase())).length,
        scout_warning_count: externalEvents.filter((event) => ['warn', 'warning'].includes(String(event.level).toLowerCase())).length,
        scout_event_ids: externalEvents.slice(0, 25).map((event) => event.id),
        details_json: summarize({ stack: err?.stack, scout_events: externalEvents.slice(0, 20) }),
      }
      await this.writeRow(row)
      await this.recordScout('error', 'audit.step.result', row.message, meta.module, row)
      return null
    }
  }

  async apiCheck(module, feature, method, pathPart, body, options = {}) {
    const target = `${this.args.baseUrl}${pathPart}`
    return await this.step({
      module,
      layer: 'api',
      feature,
      action: method,
      target: pathPart,
      http_method: method,
      http_url: target,
    }, async () => {
      const { response, payload, text } = await this.fetchJson(method, target, body, options)
      const okStatuses = options.okStatuses || [200]
      const ok = okStatuses.includes(response.status)
      return {
        value: payload,
        status: ok ? 'pass' : 'fail',
        severity: ok ? 'info' : response.status === 401 || response.status === 403 ? 'critical' : 'high',
        httpStatus: response.status,
        message: ok ? 'ok' : `HTTP ${response.status}: ${text.slice(0, 500)}`,
        errorType: ok ? '' : 'HttpError',
        details: { response: summarize(payload) },
      }
    })
  }

  async runApiAudit() {
    await this.recordScout('info', 'audit.run.start', 'Scout QA audit started', 'core', {
      frontend_url: this.args.frontendUrl || null,
      write_checks: this.args.writeChecks,
      include_dangerous: this.args.includeDangerous,
    })

    await this.apiCheck('core', 'backend health', 'GET', '/api/health', undefined, { noAuth: true })

    if (!this.args.apiKey) {
      await this.writeRow({
        module: 'auth',
        layer: 'api',
        feature: 'authenticated checks',
        action: 'skip',
        target: 'ALOS_API_KEY',
        status: 'skipped',
        severity: 'critical',
        message: 'No API key supplied. Set ALOS_API_KEY or pass --api-key.',
      })
      return
    }

    await this.apiCheck('auth', 'current user', 'GET', '/auth/me')
    await this.apiCheck('auth', 'bootstrap status', 'GET', '/auth/bootstrap/status')
    await this.apiCheck('core', 'setup status', 'GET', '/api/setup/status')
    await this.apiCheck('settings', 'settings load', 'GET', '/api/settings')
    await this.apiCheck('projects', 'list projects', 'GET', '/api/projects')
    await this.apiCheck('chat', 'list sessions', 'GET', '/api/sessions')
    await this.apiCheck('scout', 'list scout events', 'GET', '/api/scout/events?limit=25')

    await this.apiCheck('forge', 'health', 'GET', '/api/forge/health')
    await this.apiCheck('forge', 'status', 'GET', '/api/forge/status')

    await this.apiCheck('current', 'health', 'GET', '/api/current/health')
    await this.apiCheck('current', 'node catalog', 'GET', '/api/current/nodes')
    await this.apiCheck('current', 'list workflows', 'GET', '/api/current/workflows')
    await this.apiCheck('current', 'list executions', 'GET', '/api/current/executions')
    await this.apiCheck('current', 'list events', 'GET', '/api/current/events')
    await this.apiCheck('current', 'list tasks', 'GET', '/api/current/tasks')
    await this.apiCheck('current', 'swarm', 'GET', '/api/current/swarm')
    await this.apiCheck('current', 'audit log', 'GET', '/api/current/audit')

    await this.apiCheck('chamber', 'list chambers', 'GET', '/api/chamber/list')
    await this.apiCheck('chamber', 'list prewrite gates', 'GET', '/api/chamber/gates')
    await this.apiCheck('chamber', 'gate summary', 'GET', '/api/chamber/gates/summary')

    await this.apiCheck('atlas', 'health', 'GET', '/api/atlas/health')
    const repos = await this.apiCheck('atlas', 'list repositories', 'GET', '/api/atlas/repos')
    const firstRepo = Array.isArray(repos?.repositories) ? repos.repositories[0] : null
    const repoKey = firstRepo?.path || firstRepo?.repo_path || firstRepo?.id || firstRepo?.repo_id || ''
    if (repoKey) {
      const encodedRepo = encodeURIComponent(repoKey)
      await this.apiCheck('atlas', 'repo status', 'GET', `/api/atlas/status?repo=${encodedRepo}`)
      await this.apiCheck('atlas', 'search', 'GET', `/api/atlas/search?repo=${encodedRepo}&q=${encodeURIComponent('ALOS')}&limit=5`)
      await this.apiCheck('atlas', 'graph', 'GET', `/api/atlas/graph?repo=${encodedRepo}&limit=30`)
      await this.apiCheck('atlas', 'report', 'GET', `/api/atlas/report?repo=${encodedRepo}&type=auto`)
    } else {
      await this.writeRow({
        module: 'atlas',
        layer: 'api',
        feature: 'repo-dependent endpoints',
        action: 'skip',
        target: '/api/atlas/status/search/graph/report',
        status: 'skipped',
        severity: 'medium',
        message: 'No Atlas repositories are registered, so repo-dependent checks were skipped.',
      })
    }

    if (this.args.writeChecks) await this.runWriteChecks()
  }

  async runWriteChecks() {
    const suffix = this.runId.slice(-8)
    const project = await this.apiCheck('projects', 'create project', 'POST', '/api/projects', {
      name: `Scout Audit ${suffix}`,
      description: 'Temporary project created by scripts/scout_audit.mjs',
      color: '#10b981',
    })
    if (project?.id) {
      await this.apiCheck('projects', 'update project', 'PATCH', `/api/projects/${encodeURIComponent(project.id)}`, {
        description: 'Temporary project updated by Scout audit',
      })
      await this.apiCheck('projects', 'delete project', 'DELETE', `/api/projects/${encodeURIComponent(project.id)}`)
    }

    const session = await this.apiCheck('chat', 'create session', 'POST', '/api/sessions', {
      name: `Scout Audit ${suffix}`,
      project_id: null,
    })
    if (session?.id) {
      await this.apiCheck('chat', 'get session state', 'GET', `/api/sessions/${encodeURIComponent(session.id)}`)
      await this.apiCheck('chat', 'update session title', 'PUT', `/api/sessions/${encodeURIComponent(session.id)}`, {
        title: `Scout Audit ${suffix} updated`,
      })
      await this.apiCheck('chat', 'delete session', 'DELETE', `/api/sessions/${encodeURIComponent(session.id)}`)
    }

    const workflow = await this.apiCheck('current', 'create workflow', 'POST', '/api/current/workflows', {
      name: `Scout Audit ${suffix}`,
      description: 'Temporary workflow created by Scout audit',
      tags: ['scout-audit'],
    })
    const workflowId = workflow?.workflow?.id
    if (workflowId) {
      await this.apiCheck('current', 'validate workflow', 'POST', `/api/current/workflows/${encodeURIComponent(workflowId)}/validate`)
      await this.apiCheck('current', 'publish workflow', 'POST', `/api/current/workflows/${encodeURIComponent(workflowId)}/publish`)
      await this.apiCheck('current', 'workflow versions', 'GET', `/api/current/workflows/${encodeURIComponent(workflowId)}/versions`)
      await this.apiCheck('current', 'archive workflow', 'DELETE', `/api/current/workflows/${encodeURIComponent(workflowId)}`)
    }
  }

  async runUiAudit() {
    if (this.args.noUi || !this.args.frontendUrl) return
    const browser = new CdpBrowser(this.args, this)
    try {
      await browser.start()
      await browser.open(this.args.frontendUrl, this.args.apiKey)
      await browser.recordPageHealth('app load')

      for (const moduleName of MODULES) {
        const clicked = await browser.activateModule(moduleName) || await browser.clickByText(moduleName)
        if (!clicked) {
          let visibleActions = []
          let visibleActionsError = ''
          try {
            visibleActions = await browser.visibleActions(40)
          } catch (err) {
            visibleActionsError = err?.message || String(err)
          }
          await this.writeRow({
            module: moduleName.toLowerCase(),
            layer: 'ui',
            feature: 'module navigation',
            action: 'click',
            target: moduleName,
            status: 'skipped',
            severity: 'medium',
            message: 'Module navigation target was not visible in this frontend context.',
            details_json: summarize({ visible_actions: visibleActions, visible_actions_error: visibleActionsError }),
          })
          continue
        }
        await browser.recordPageHealth(`${moduleName} module open`)
        await browser.crawlVisibleActions(moduleName.toLowerCase(), moduleName)
      }
    } catch (err) {
      await this.writeRow({
        module: 'frontend',
        layer: 'ui',
        feature: 'browser crawl',
        action: 'run',
        target: this.args.frontendUrl,
        status: 'fail',
        severity: 'high',
        message: err?.message || String(err),
        error_type: err?.name || 'Error',
        details_json: summarize({ stack: err?.stack }),
      })
    } finally {
      await browser.stop()
    }
  }

  async finish() {
    const failureCount = this.rows.filter((row) => row.status === 'fail').length
    const warningCount = this.rows.filter((row) => row.status === 'warn').length
    const skippedCount = this.rows.filter((row) => row.status === 'skipped').length
    await this.recordScout(failureCount ? 'error' : warningCount ? 'warning' : 'info', 'audit.run.finish', 'Scout QA audit finished', 'core', {
      csv: this.csvPath,
      jsonl: this.jsonlPath || null,
      rows: this.rows.length,
      failures: failureCount,
      warnings: warningCount,
      skipped: skippedCount,
    })
    return { failureCount, warningCount, skippedCount }
  }
}

class CdpBrowser {
  constructor(args, runner) {
    this.args = args
    this.runner = runner
    this.browserWs = null
    this.pageWs = null
    this.nextId = 1
    this.pending = new Map()
    this.browserProcess = null
    this.userDataDir = ''
    this.consoleProblems = []
    this.requestUrls = new Map()
    this.port = args.chromeDebugPort || 0
  }

  async start() {
    if (this.args.chromeDebugPort) {
      this.port = this.args.chromeDebugPort
      return
    }
    this.port = await getFreePort()
    const chromePath = this.args.chromePath || findChrome()
    if (!chromePath) {
      throw new Error('Chrome was not found. Pass --chrome-path or use --no-ui.')
    }
    this.userDataDir = await mkdtemp(path.join(tmpdir(), 'alos-scout-audit-chrome-'))
    this.browserProcess = spawn(chromePath, [
      `--remote-debugging-port=${this.port}`,
      `--user-data-dir=${this.userDataDir}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-background-networking',
      '--window-size=1440,1000',
      'about:blank',
    ], { stdio: 'ignore' })
    await this.waitForDebugPort()
  }

  async waitForDebugPort() {
    const deadline = Date.now() + 10_000
    while (Date.now() < deadline) {
      try {
        const response = await fetch(`http://127.0.0.1:${this.port}/json/version`)
        if (response.ok) return
      } catch {
        // keep waiting
      }
      await sleep(200)
    }
    throw new Error(`Timed out waiting for Chrome debugging port ${this.port}`)
  }

  async stop() {
    if (this.pageWs) {
      try { this.pageWs.close() } catch {}
    }
    if (this.browserProcess && !this.args.keepBrowser) {
      try { this.browserProcess.kill() } catch {}
    }
    if (this.userDataDir && !this.args.keepBrowser) {
      await rm(this.userDataDir, { recursive: true, force: true }).catch(() => {})
    }
  }

  async open(frontendUrl, apiKey) {
    if (typeof WebSocket === 'undefined') {
      throw new Error('This Node runtime does not provide global WebSocket. Use Node 22+ or run API-only with --no-ui.')
    }
    const targetResponse = await fetch(`http://127.0.0.1:${this.port}/json/new?${encodeURIComponent('about:blank')}`, { method: 'PUT' })
    const target = await targetResponse.json()
    this.pageWs = new WebSocket(target.webSocketDebuggerUrl)
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Timed out opening CDP websocket')), 5_000)
      this.pageWs.addEventListener('open', () => {
        clearTimeout(timer)
        resolve()
      }, { once: true })
      this.pageWs.addEventListener('error', reject, { once: true })
    })
    this.pageWs.addEventListener('message', (event) => this.onMessage(event))

    await this.call('Runtime.enable')
    await this.call('Page.enable')
    await this.call('Log.enable')
    await this.call('Network.enable')
    await this.call('Emulation.setDeviceMetricsOverride', {
      width: 1440,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
    })
    await this.installEventListeners()

    if (apiKey) {
      await this.call('Page.addScriptToEvaluateOnNewDocument', {
        source: `
          try {
            localStorage.setItem('alos-auth', JSON.stringify({ state: { apiKey: ${JSON.stringify(apiKey)} }, version: 0 }));
          } catch (error) {
            console.error('[scout-audit] failed to seed auth', error);
          }
        `,
      })
    }

    const loadPromise = this.waitForLoad()
    await this.call('Page.navigate', { url: frontendUrl })
    await loadPromise
    await this.waitForAppReady()
    await sleep(1000)
  }

  onMessage(event) {
    const data = JSON.parse(event.data)
    if (data.id && this.pending.has(data.id)) {
      const { resolve, reject } = this.pending.get(data.id)
      this.pending.delete(data.id)
      if (data.error) reject(new Error(data.error.message || JSON.stringify(data.error)))
      else resolve(data.result)
      return
    }
    if (data.method === 'Runtime.exceptionThrown') {
      this.consoleProblems.push({
        level: 'error',
        type: 'exception',
        message: data.params?.exceptionDetails?.text || data.params?.exceptionDetails?.exception?.description || 'Runtime exception',
      })
    } else if (data.method === 'Runtime.consoleAPICalled') {
      const level = data.params?.type
      if (['error', 'warning', 'warn', 'assert'].includes(level)) {
        this.consoleProblems.push({
          level: level === 'warning' ? 'warn' : level,
          type: 'console',
          message: (data.params?.args || []).map((arg) => arg.value ?? arg.description ?? arg.type).join(' '),
        })
      }
    } else if (data.method === 'Log.entryAdded') {
      const entry = data.params?.entry
      if (entry && ['error', 'warning'].includes(entry.level)) {
        if (entry.url && /\/favicon\.ico(?:$|\?)/.test(entry.url)) return
        this.consoleProblems.push({
          level: entry.level === 'warning' ? 'warn' : entry.level,
          type: 'log',
          message: `${entry.text || ''} ${entry.url || ''}`.trim(),
        })
      }
    } else if (data.method === 'Network.requestWillBeSent') {
      if (data.params?.requestId) {
        this.requestUrls.set(data.params.requestId, {
          url: data.params?.request?.url || '',
          type: data.params?.type || '',
        })
      }
    } else if (data.method === 'Network.loadingFailed') {
      const errorText = data.params?.errorText || 'Network request failed'
      const canceled = Boolean(data.params?.canceled)
      const request = this.requestUrls.get(data.params?.requestId) || {}
      if (canceled && errorText === 'net::ERR_ABORTED') {
        return
      }
      this.consoleProblems.push({
        level: 'error',
        type: 'network',
        message: `${errorText} ${data.params?.blockedReason || ''} ${request.url || ''}`.trim(),
      })
    }
  }

  async call(method, params = {}, options = {}) {
    const id = this.nextId
    this.nextId += 1
    this.pageWs.send(JSON.stringify({ id, method, params }))
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`CDP call timed out: ${method}`))
      }, options.timeoutMs || this.args.timeoutMs)
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer)
          resolve(value)
        },
        reject: (err) => {
          clearTimeout(timer)
          reject(err)
        },
      })
    })
  }

  async evaluate(expression, options = {}) {
    const result = await this.call('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    }, options)
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Runtime.evaluate failed')
    return result.result?.value
  }

  async waitForLoad() {
    await Promise.race([
      new Promise((resolve) => {
        const listener = (event) => {
          const data = JSON.parse(event.data)
          if (data.method === 'Page.loadEventFired') {
            this.pageWs.removeEventListener('message', listener)
            resolve()
          }
        }
        this.pageWs.addEventListener('message', listener)
      }),
      sleep(8_000),
    ])
  }

  async waitForAppReady() {
    const deadline = Date.now() + Math.max(5_000, this.args.timeoutMs)
    while (Date.now() < deadline) {
      try {
        const ready = await this.evaluate(`(() => {
          const root = document.getElementById('root');
          const bodyText = document.body ? document.body.innerText.trim() : '';
          const interactiveCount = document.querySelectorAll('button,[role="button"],a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])').length;
          return Boolean(bodyText || interactiveCount || (root && root.childElementCount > 0));
        })()`, { timeoutMs: Math.min(1_500, this.args.timeoutMs) })
        if (ready) return true
      } catch {
        // Chrome can reject Runtime.evaluate while the target is navigating.
      }
      await sleep(250)
    }
    return false
  }

  async installEventListeners() {
    // Runtime/Log/Network events are handled in onMessage; this method is kept
    // as the explicit setup point for future UI audit telemetry.
  }

  drainProblems() {
    const problems = this.consoleProblems
    this.consoleProblems = []
    return problems
  }

  async recordPageHealth(feature) {
    const startedAt = Date.now()
    let info = null
    let healthError = null
    try {
      info = await this.evaluate(`(() => ({
        title: document.title,
        url: location.href,
        bodyText: document.body ? document.body.innerText.slice(0, 1000) : '',
        rootChildCount: document.getElementById('root')?.childElementCount || 0,
        buttons: document.querySelectorAll('button,[role="button"],a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])').length,
        actionLabels: Array.from(document.querySelectorAll('button,[role="button"],a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'))
          .slice(0, 40)
          .map((el) => ([el.innerText, el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('placeholder'), el.value, el.textContent, el.tagName]
            .map((value) => (value || '').trim())
            .find(Boolean) || '').replace(/\\s+/g, ' '))
      }))()`, { timeoutMs: Math.min(5_000, this.args.timeoutMs) })
    } catch (err) {
      healthError = {
        level: 'error',
        type: 'cdp',
        message: err?.message || String(err),
      }
      info = {
        title: '',
        url: this.args.frontendUrl,
        bodyText: '',
        rootChildCount: 0,
        buttons: 0,
      }
    }
    await sleep(250)
    const problems = this.drainProblems()
    if (healthError) problems.unshift(healthError)
    const rendered = Boolean(info?.bodyText?.trim() || info?.buttons || info?.rootChildCount)
    const hasError = problems.some((p) => p.level === 'error') || !rendered
    const hasWarning = problems.length > 0
    await this.runner.writeRow({
      module: 'frontend',
      layer: 'ui',
      feature,
      action: 'inspect',
      target: info?.url || this.args.frontendUrl,
      status: hasError ? 'fail' : hasWarning ? 'warn' : 'pass',
      severity: hasError ? 'high' : hasWarning ? 'medium' : 'info',
      duration_ms: Date.now() - startedAt,
      message: rendered ? problems[0]?.message || 'page loaded' : 'page did not render visible content',
      error_type: problems[0]?.type || '',
      details_json: summarize({ page: info, problems }),
    })
    await this.runner.recordScout(hasError ? 'error' : hasWarning ? 'warning' : 'info', 'audit.ui.page', feature, 'frontend', {
      page: info,
      problems,
    })
  }

  async clickByText(text) {
    const escaped = JSON.stringify(text)
    const result = await this.evaluate(`(() => {
      const wanted = ${escaped}.toLowerCase();
      const elements = Array.from(document.querySelectorAll('button,[role="button"],a[href],[aria-label],[title]'));
      const label = (el) => [el.innerText, el.getAttribute('aria-label'), el.getAttribute('title'), el.textContent]
        .map((value) => (value || '').trim())
        .find(Boolean) || '';
      const match = elements.find((el) => label(el).toLowerCase() === wanted)
        || elements.find((el) => label(el).toLowerCase().includes(wanted));
      if (!match) return false;
      match.click();
      return true;
    })()`)
    if (result) await sleep(800)
    return Boolean(result)
  }

  async activateModule(moduleName) {
    const moduleIdByName = {
      Forge: 'forge',
      Current: 'current',
      Atlas: 'atlas',
      Chamber: 'chamber',
      Chat: 'chat',
      Scout: 'scout',
      Settings: 'settings',
    }
    const moduleId = moduleIdByName[moduleName]
    if (!moduleId) return false
    const result = await this.evaluate(`(() => {
      localStorage.setItem('alos:active-module:v2', JSON.stringify({
        state: { activeId: ${JSON.stringify(moduleId)} },
        version: 0
      }));
      return true;
    })()`)
    if (result) {
      const loadPromise = this.waitForLoad()
      await this.call('Page.navigate', { url: this.args.frontendUrl })
      await loadPromise
      await this.waitForAppReady()
      await sleep(800)
    }
    return Boolean(result)
  }

  async visibleActions(maxActions) {
    return await this.evaluate(`(() => {
      const nodes = Array.from(document.querySelectorAll('button,[role="button"],a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'));
      const label = (el) => ([el.innerText, el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('placeholder'), el.value, el.textContent, el.tagName]
        .map((value) => (value || '').trim())
        .find(Boolean) || '').replace(/\\s+/g, ' ');
      return nodes.slice(0, ${Number(maxActions)}).map((el, index) => {
        const id = 'alos-audit-' + Date.now() + '-' + index;
        el.setAttribute('data-alos-audit-id', id);
        const rect = el.getBoundingClientRect();
        return {
          id,
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || '',
          type: el.getAttribute('type') || '',
          text: label(el).slice(0, 160),
          href: el.getAttribute('href') || '',
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        };
      });
    })()`)
  }

  async crawlVisibleActions(moduleId, featurePrefix) {
    const actions = await this.visibleActions(this.args.maxUiActions)
    const seen = new Set()
    for (const action of actions) {
      const label = action.text || `${action.tag}:${action.role}:${action.type}`
      const key = `${action.tag}:${label}:${action.x}:${action.y}`
      if (seen.has(key)) continue
      seen.add(key)

      if (MODULE_NAV_LABELS.has(label) || TELEMETRY_ROW_LABEL_RE.test(label)) {
        continue
      }

      if (!this.args.includeDangerous && DANGEROUS_LABEL_RE.test(label)) {
        await this.runner.writeRow({
          module: moduleId,
          layer: 'ui',
          feature: `${featurePrefix} visible action`,
          action: 'skip',
          target: label,
          status: 'skipped',
          severity: 'medium',
          message: 'Skipped destructive-looking UI action. Re-run with --include-dangerous to click it.',
          details_json: action,
        })
        continue
      }

      await this.runner.step({
        module: moduleId,
        layer: 'ui',
        feature: `${featurePrefix} visible action`,
        action: 'click',
        target: label,
      }, async () => {
        const clicked = await this.evaluate(`(() => {
          const el = document.querySelector('[data-alos-audit-id="${action.id}"]');
          if (!el) return { clicked: false, reason: 'element disappeared' };
          el.click();
          return { clicked: true, location: location.href };
        })()`)
        await sleep(700)
        const problems = this.drainProblems()
        const disappeared = !clicked?.clicked && clicked?.reason === 'element disappeared'
        const hasProblemError = problems.some((p) => p.level === 'error')
        return {
          status: hasProblemError ? 'fail' : disappeared ? 'skipped' : clicked?.clicked ? (problems.length ? 'warn' : 'pass') : 'warn',
          severity: hasProblemError ? 'high' : problems.length ? 'medium' : clicked?.clicked ? 'info' : 'medium',
          message: problems[0]?.message || (clicked?.clicked ? 'clicked' : clicked?.reason || 'not clicked'),
          errorType: problems[0]?.type || '',
          details: summarize({ action, clicked, problems }),
        }
      })
    }
  }
}

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean)
  return candidates.find((candidate) => existsSync(candidate)) || ''
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const runner = new AuditRunner(args)
  await runner.init()
  try {
    await runner.runApiAudit()
    await runner.runUiAudit()
    const summary = await runner.finish()
    console.log(`Scout audit complete: ${runner.csvPath}`)
    if (runner.jsonlPath) console.log(`JSONL: ${runner.jsonlPath}`)
    console.log(`Rows: ${runner.rows.length}; failures: ${summary.failureCount}; warnings: ${summary.warningCount}; skipped: ${summary.skippedCount}`)
    if (!args.apiKey) {
      console.log('Authenticated checks were skipped because no API key was supplied.')
    }
  } finally {
    runner.close()
  }
}

main().catch((err) => {
  console.error(err?.stack || err?.message || String(err))
  process.exit(1)
})
