/**
 * ALOS backend client.
 *
 * Handles:
 *   - Base URL resolution (defaults to http://localhost:8000)
 *   - Bearer token auth from the store
 *   - JSON request/response handling
 *   - Typed error surface
 */

import type {
  AppSettings,
  HealthStatus,
  OriginalAdminBootstrapResult,
  OriginalAdminBootstrapStatus,
  Project,
  ProviderConfigPayload,
  ProviderValidationResult,
  ScoutEvent,
  ScoutEventInput,
  Session,
  SessionStateResponse,
  SetupStatus,
  User,
} from '@/types/api'
import type {
  AtlasContextResponse,
  AtlasGraphResponse,
  AtlasImpactResponse,
  AtlasIndexResult,
  AtlasReportResponse,
  AtlasReposResponse,
  AtlasSearchResponse,
  AtlasStatus,
} from '@/types/atlas'
import type {
  ChamberGatesResponse,
  ChamberGateSummary,
  ChamberListResponse,
} from '@/types/chamber'

const DEFAULT_BASE_URL = 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  body?: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

interface ClientOptions {
  baseUrl?: string
  getApiKey?: () => string | null
}

export class AlosClient {
  private baseUrl: string
  private getApiKey: () => string | null

  constructor(opts: ClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? DEFAULT_BASE_URL
    this.getApiKey = opts.getApiKey ?? (() => null)
  }

  setBaseUrl(url: string) {
    this.baseUrl = url
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers)
    if (!headers.has('Content-Type') && init.body) {
      headers.set('Content-Type', 'application/json')
    }
    const key = this.getApiKey()
    if (key) headers.set('Authorization', `Bearer ${key}`)

    let res: Response
    try {
      res = await fetch(`${this.baseUrl}${path}`, { ...init, headers })
    } catch (err) {
      throw new ApiError(0, `Network error: ${(err as Error).message}`)
    }

    const text = await res.text()
    const body = text ? safeJsonParse(text) : null

    if (!res.ok) {
      let detail: string = res.statusText || 'Request failed'
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = String((body as { detail: unknown }).detail)
      }
      throw new ApiError(res.status, detail, body)
    }

    return body as T
  }

  // ── Health ──────────────────────────────────────────────
  health() {
    return this.request<HealthStatus>('/api/health')
  }

  // ── Auth ────────────────────────────────────────────────
  validateKey(apiKey: string) {
    return this.request<{ valid: true; user: User }>('/auth/validate', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    })
  }

  getOriginalAdminBootstrapStatus() {
    return this.request<OriginalAdminBootstrapStatus>('/auth/bootstrap/status')
  }

  createOriginalAdmin(username = 'admin') {
    return this.request<OriginalAdminBootstrapResult>('/auth/bootstrap/original-admin', {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  }

  me() {
    return this.request<User>('/auth/me')
  }

  // ── Setup / Provider config ─────────────────────────────
  getSetupStatus() {
    return this.request<SetupStatus>('/api/setup/status')
  }

  validateProvider(payload: ProviderConfigPayload) {
    return this.request<ProviderValidationResult>('/api/setup/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  getSettings() {
    return this.request<AppSettings>('/api/settings')
  }

  saveProviderConfig(payload: ProviderConfigPayload) {
    return this.request<AppSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  }

  clearProviderSettings() {
    return this.request<AppSettings>('/api/settings/provider', {
      method: 'DELETE',
    })
  }

  // ── Projects ────────────────────────────────────────────
  listProjects() {
    return this.request<Project[]>('/api/projects')
  }

  createProject(name: string, description = '', color = '#6366f1') {
    return this.request<Project>('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ name, description, color }),
    })
  }

  updateProject(id: string, patch: Partial<Pick<Project, 'name' | 'description' | 'color'>>) {
    return this.request<{ status: string }>(`/api/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  }

  deleteProject(id: string) {
    return this.request<{ status: string }>(`/api/projects/${id}`, {
      method: 'DELETE',
    })
  }

  // ── Sessions ────────────────────────────────────────────
  listSessions() {
    return this.request<Session[]>('/api/sessions')
  }

  createSession(name?: string, projectId?: string | null) {
    return this.request<Session>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ name: name ?? 'New session', project_id: projectId ?? null }),
    })
  }

  assignSessionProject(sessionId: string, projectId: string | null) {
    return this.request<{ status: string }>(`/api/sessions/${sessionId}/project`, {
      method: 'PATCH',
      body: JSON.stringify({ project_id: projectId }),
    })
  }

  deleteSession(id: string) {
    return this.request<{ success: boolean }>(`/api/sessions/${id}`, {
      method: 'DELETE',
    })
  }

  /**
   * Fetch the full session state — messages, runs, active run, and the
   * current run plan. Used on Chat mount to rehydrate visible history.
   *
   * The backend stores chat history inside session state as a list of
   * LangChain message dicts; there is no separate `/messages` endpoint.
   */
  getSessionState(sessionId: string) {
    return this.request<SessionStateResponse>(`/api/sessions/${sessionId}`)
  }

  /**
   * Update a session's title. Used after the first user message of a
   * conversation, mirroring what the websocket hub emits via
   * `title_update`. Safe to call even when no title change is needed.
   */
  updateSessionTitle(sessionId: string, title: string) {
    return this.request<{ status: string; title: string }>(
      `/api/sessions/${sessionId}`,
      {
        method: 'PUT',
        body: JSON.stringify({ title }),
      },
    )
  }

  // ── Atlas (code graph) ──────────────────────────────────
  //
  // Wraps modules/atlas/backend/src/api/router.py, auto-mounted at
  // /api/atlas/* by the sidecar's discover_and_mount_modules pass.
  // Every call requires `repo` — the absolute filesystem path of an
  // indexed repository (also the registration key).
  atlasListRepos() {
    return this.request<AtlasReposResponse>('/api/atlas/repos')
  }
  atlasStatus(repo: string) {
    return this.request<AtlasStatus>(`/api/atlas/status?repo=${encodeURIComponent(repo)}`)
  }
  atlasIndex(repo: string) {
    return this.request<AtlasIndexResult>(
      `/api/atlas/index?repo=${encodeURIComponent(repo)}`,
      { method: 'POST' },
    )
  }
  atlasSearch(repo: string, q: string, limit = 10) {
    const qs = new URLSearchParams({ repo, q, limit: String(limit) })
    return this.request<AtlasSearchResponse>(`/api/atlas/search?${qs.toString()}`)
  }
  atlasSymbol(repo: string, name: string, limit = 20) {
    const qs = new URLSearchParams({ repo, name, limit: String(limit) })
    return this.request<AtlasContextResponse>(`/api/atlas/symbol?${qs.toString()}`)
  }
  atlasFile(repo: string, path: string, limit = 20) {
    const qs = new URLSearchParams({ repo, path, limit: String(limit) })
    return this.request<AtlasContextResponse>(`/api/atlas/file?${qs.toString()}`)
  }
  atlasImpact(repo: string, target: string, depth = 3, limit = 50, type = 'auto') {
    const qs = new URLSearchParams({
      repo, target, type, depth: String(depth), limit: String(limit),
    })
    return this.request<AtlasImpactResponse>(`/api/atlas/impact?${qs.toString()}`)
  }
  atlasGraph(repo: string, limit = 80) {
    const qs = new URLSearchParams({ repo, limit: String(limit) })
    return this.request<AtlasGraphResponse>(`/api/atlas/graph?${qs.toString()}`)
  }
  atlasReport(repo: string, target?: string, type = 'auto') {
    const qs = new URLSearchParams({ repo, type })
    if (target) qs.set('target', target)
    return this.request<AtlasReportResponse>(`/api/atlas/report?${qs.toString()}`)
  }

  // ── Chamber (pre-write gates) ───────────────────────────
  chamberList() {
    return this.request<ChamberListResponse>('/api/chamber/list')
  }
  chamberGates(status?: string) {
    const qs = new URLSearchParams()
    if (status) qs.set('status', status)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return this.request<ChamberGatesResponse>(`/api/chamber/gates${suffix}`)
  }
  chamberGateSummary() {
    return this.request<ChamberGateSummary>('/api/chamber/gates/summary')
  }

  // ── Scout diagnostics ─────────────────────────────────
  listScoutEvents(params: {
    limit?: number
    source?: string
    level?: string
    module?: string
    run_id?: string
    session_id?: string
    q?: string
  } = {}) {
    const qs = new URLSearchParams()
    if (params.limit) qs.set('limit', String(params.limit))
    if (params.source) qs.set('source', params.source)
    if (params.level) qs.set('level', params.level)
    if (params.module) qs.set('module', params.module)
    if (params.run_id) qs.set('run_id', params.run_id)
    if (params.session_id) qs.set('session_id', params.session_id)
    if (params.q) qs.set('q', params.q)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return this.request<{ events: ScoutEvent[] }>(`/api/scout/events${suffix}`)
  }

  recordScoutEvent(payload: ScoutEventInput) {
    return this.request<ScoutEvent>('/api/scout/events', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  // ── WebSocket ───────────────────────────────────────────
  openSocket(sessionId: string): WebSocket {
    const wsBase = this.baseUrl.replace(/^http/, 'ws')
    const key = this.getApiKey()
    const qs = key ? `?api_key=${encodeURIComponent(key)}` : ''
    return new WebSocket(`${wsBase}/ws/${sessionId}${qs}`)
  }

  openScoutSocket(): WebSocket {
    const wsBase = this.baseUrl.replace(/^http/, 'ws')
    const key = this.getApiKey()
    const qs = key ? `?api_key=${encodeURIComponent(key)}` : ''
    return new WebSocket(`${wsBase}/ws/scout${qs}`)
  }
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}
