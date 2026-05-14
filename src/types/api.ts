/**
 * Shared types for the ALOS backend API.
 * Mirrors what the FastAPI backend returns from /api/* endpoints.
 */

export interface Project {
  id: string
  name: string
  description: string
  color: string
  created_at: string
}

export interface Session {
  id: string
  name: string
  created_at: string
  updated_at?: string
  project_id?: string | null
  message_count?: number
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'agent'

export interface Message {
  id: string
  session_id: string
  role: MessageRole
  content: string
  created_at: string
  agent_name?: string
  tool_calls?: ToolCall[]
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: string
}

export interface User {
  user_id: string
  username: string
  role: 'admin' | 'user' | 'viewer' | 'auditor'
}

export interface OriginalAdminBootstrapStatus {
  users_exist: boolean
  active_admins: number
  can_bootstrap: boolean
  data_dir: string
}

export interface OriginalAdminBootstrapResult {
  api_key_id: string
  api_key: string
  user: User
}

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'down'
  version?: string
  uptime_seconds?: number
}

// ── Provider / setup ────────────────────────────────────
export type ProviderId =
  | 'nvidia'
  | 'openai'
  | 'anthropic'
  | 'ollama'
  | 'openai_compatible'

export interface ProviderConfigPayload {
  llm_provider: ProviderId
  api_key?: string
  model_name: string
  base_url?: string
  max_retries?: number
  timeout_seconds?: number
  temperature?: number
  top_p?: number
  top_k?: number | null
  max_output_tokens?: number
  context_window_tokens?: number
  max_input_tokens?: number | null
  reserved_context_tokens?: number
  presence_penalty?: number
  frequency_penalty?: number
  seed?: number | null
  max_agent_turns?: number
  chamber_gate_required?: boolean
  allow_chamber_override?: boolean
  autonomous_write_mode?: AutonomousWriteMode
}

export type AutonomousWriteMode =
  | 'manual_only'
  | 'propose_only'
  | 'chamber_gated'
  | 'autonomous'

export interface ProviderSettings {
  configured: boolean
  llm_provider: ProviderId
  model_name: string
  base_url: string
  max_retries: number
  timeout_seconds: number
  api_key_set: boolean
  temperature: number
  top_p: number
  top_k: number | null
  max_output_tokens: number
  context_window_tokens: number
  max_input_tokens: number | null
  reserved_context_tokens: number
  presence_penalty: number
  frequency_penalty: number
  seed: number | null
  max_agent_turns: number
  chamber_gate_required: boolean
  allow_chamber_override: boolean
  autonomous_write_mode: AutonomousWriteMode
}

export interface SettingsDiagnostics {
  status: string
  version: string
  data_dir: string
  logs_dir: string
  user_data_dir: string
  env_path: string
  backend_dir: string
  configured: boolean
  provider: string
  model: string
}

export interface AppSettings extends ProviderSettings {
  policy?: Record<string, unknown>
  setup?: SetupStatus
  diagnostics?: SettingsDiagnostics
}

export interface ProviderValidationResult {
  ok: boolean
  errors?: string[]
  provider: string
  model: string
  base_url: string
  api_key_set: boolean
  checked_network?: boolean
  status_code?: number | null
  message?: string
  validated_at?: string
}

export interface SetupCheck {
  name: string
  ok: boolean
  detail: string
}

// ── Preflight (Rust-side dependency check) ──────────────
export interface PreflightReport {
  ok: boolean
  python_ok: boolean
  python_path: string | null
  python_version: string | null
  python_error: string | null
  venv_path: string
  venv_exists: boolean
  missing_packages: string[]
  required_packages: string[]
  minimum_python: string
  backend_dir: string
}

export interface PreflightProgressEvent {
  phase: 'venv' | 'pip' | 'done' | string
  line: string
}

export interface SetupStatus {
  ready: boolean
  state: 'missing_config' | 'repair_needed' | 'provider_invalid' | 'ready'
  checks: SetupCheck[]
  next_action: string
  last_validation?: Partial<ProviderValidationResult>
}

// ── Chat / Swarm WebSocket contract ─────────────────────
//
// Mirrors backend/src/api/server.py — every type the websocket_hub or the
// run_swarm_background helper sends. Keep this file in lockstep with that
// switch, or the dispatcher in ChatView will silently drop frames.

/** LangChain message dict shape, as persisted in session state. */
export interface LangChainMessage {
  type: 'human' | 'ai' | 'system' | 'tool' | 'function' | string
  data: {
    content: string
    additional_kwargs?: Record<string, unknown>
    response_metadata?: Record<string, unknown>
    type?: string
    name?: string | null
    id?: string | null
    tool_calls?: unknown[]
    [key: string]: unknown
  }
}

export interface PlanStep {
  id: string
  title: string
  status:
    | 'pending'
    | 'running'
    | 'blocked'
    | 'failed'
    | 'complete'
    | 'in_progress'
    | 'completed'
    | 'skipped'
    | string
  required_verification?: boolean
  description?: string
  [key: string]: unknown
}

export interface RunPlan {
  steps: PlanStep[]
  current_step_id?: string | null
  risk?: string
  needs_approval?: boolean
  approval_id?: string
  status?: string
  [key: string]: unknown
}

export interface RunSummary {
  id: string
  session_id?: string
  status?: string
  created_at?: string
  completed_at?: string | null
  active_worker?: string | null
  [key: string]: unknown
}

export interface RunEvent {
  id?: string
  run_id?: string
  session_id?: string
  event_type?: string
  type?: string
  node?: string
  active_worker?: string | null
  ts?: string
  created_at?: string | null
  payload?: Record<string, unknown>
  data?: Record<string, unknown>
  [key: string]: unknown
}

export interface ActiveRunReplay {
  run?: RunSummary | null
  events?: RunEvent[]
  checkpoints?: Array<Record<string, unknown>>
  last_event?: RunEvent | null
  [key: string]: unknown
}

export interface ScoutEvent {
  id: string
  source: string
  level: string
  event_type: string
  message: string
  module?: string | null
  run_id?: string | null
  session_id?: string | null
  payload: Record<string, unknown>
  created_at: string | null
}

export interface ScoutEventInput {
  source: string
  level?: string
  event_type: string
  message?: string
  module?: string | null
  run_id?: string | null
  session_id?: string | null
  payload?: Record<string, unknown>
}

export type ScoutWsFrame =
  | { type: 'scout_snapshot'; events: ScoutEvent[] }
  | { type: 'scout_event'; event: ScoutEvent }
  | { type: string; [key: string]: unknown }

export interface SessionStateResponse {
  messages: LangChainMessage[]
  cumulative_tokens?: { total_tokens?: number; [key: string]: unknown }
  runs?: RunSummary[]
  active_run?: ActiveRunReplay | null
  run_plan?: RunPlan | null
  current_plan_step?: string | null
  module_context?: Record<string, unknown> | null
  logic_trace?: Array<Record<string, unknown>>
  logic_cycle_count?: number
  stuck_reason?: string
}

/**
 * Discriminated union of every server-to-client websocket frame.
 * Keep order/keys in lockstep with backend/src/api/server.py.
 */
export type ChatWsServerFrame =
  | { type: 'system_log'; content: string }
  | { type: 'token_update'; total: number }
  | { type: 'title_update'; title: string }
  | { type: 'status'; message: string }
  | { type: 'setup_required'; message: string }
  | { type: 'chat_output'; sender: string; content: string }
  | { type: 'run_started'; run_id: string }
  | { type: 'run_event'; event: RunEvent }
  | { type: 'run_resume'; replay: ActiveRunReplay }
  | { type: 'plan_update'; plan: RunPlan }
  | { type: 'plan_rejected'; message: string }
  | { type: 'execution_complete' }
  | { type: 'swarm_update'; node: string; active_worker?: string | null }
  | { type: 'auth_request'; approval_id: string; [key: string]: unknown }
  | { type: 'patch_request'; approval_id: string; proposal?: Record<string, unknown>; [key: string]: unknown }
  | { type: 'plan_approval_request'; approval_id: string; plan?: RunPlan; risk?: string; [key: string]: unknown }
  | { type: 'plan_request'; approval_id: string; plan?: RunPlan; [key: string]: unknown }
  // Forward-compatible fallback for any new frame the backend introduces.
  | { type: string; [key: string]: unknown }

/** Discriminated union of every client-to-server websocket frame. */
export type ChatWsClientFrame =
  | { type: 'chat_input'; text: string; module_context?: Record<string, unknown> }
  | { type: 'stop_execution' }
  | { type: 'auth_response'; approval_id: string; approved: boolean }
  | { type: 'plan_response'; approval_id: string; approved: boolean }
