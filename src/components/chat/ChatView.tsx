import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FolderOpen,
  FolderPlus,
  Loader2,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  PlugZap,
  Plus,
  RefreshCcw,
  Send,
  Square,
  Trash2,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { api } from '@/api'
import { ApiError } from '@/api/client'
import { registerModuleAgentContextProvider } from '@/shell/agent-context'
import { useAuth } from '@/store/auth'
import { cn } from '@/lib/utils'
import type {
  ChatWsClientFrame,
  ChatWsServerFrame,
  LangChainMessage,
  PlanStep,
  Project,
  RunPlan,
  Session,
  SessionStateResponse,
} from '@/types/api'

// ── Constants ─────────────────────────────────────────────────────────────────

const ACTIVE_SESSION_KEY = 'alos.chat.active-session'
const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_BASE_MS = 750
const RECONNECT_CAP_MS = 15_000

// ── Local types ───────────────────────────────────────────────────────────────

type ConnectionState =
  | { kind: 'idle' }
  | { kind: 'connecting' }
  | { kind: 'open' }
  | { kind: 'reconnecting'; attempt: number; nextDelayMs: number }
  | { kind: 'closed'; reason: string }
  | { kind: 'unauthorized'; reason: string }

type RunState =
  | { kind: 'idle' }
  | { kind: 'starting' }
  | { kind: 'running'; runId?: string; activeWorker?: string | null }

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'system_error' | 'tool'
  sender: string
  content: string
  ts: number
  fromHistory?: boolean
}

interface PendingApproval {
  approvalId: string
  plan: RunPlan
}

interface PendingActionApproval {
  approvalId: string
  kind: 'write' | 'patch'
  risk?: string
  title: string
  detail?: string
  diff?: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function clientId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return (crypto as Crypto).randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function langchainToChatMessage(m: LangChainMessage, idx: number): ChatMessage | null {
  const content = (m.data && typeof m.data.content === 'string' ? m.data.content : '').trim()
  if (!content) return null
  switch (m.type) {
    case 'human':
      return { id: `hist-${idx}-human`, role: 'user', sender: 'You', content, ts: 0, fromHistory: true }
    case 'ai': {
      const sender = (m.data?.additional_kwargs as Record<string, unknown> | undefined)?.['sender']
      return { id: `hist-${idx}-ai`, role: 'assistant', sender: typeof sender === 'string' && sender ? sender : 'ALOS', content, ts: 0, fromHistory: true }
    }
    case 'system':
      return { id: `hist-${idx}-system`, role: 'system', sender: 'System', content, ts: 0, fromHistory: true }
    default:
      return null
  }
}

function classifySender(sender: string): ChatMessage['role'] {
  const s = sender.toLowerCase()
  if (s === 'you' || s === 'user' || s === 'human') return 'user'
  if (s === 'system_error' || s.includes('error')) return 'system_error'
  if (s === 'system') return 'system'
  return 'assistant'
}

function planRiskTone(risk: string | undefined): { label: string; cls: string } {
  switch ((risk ?? '').toLowerCase()) {
    case 'high': return { label: 'High risk', cls: 'bg-red-500/15 text-red-400 border-red-500/40' }
    case 'medium': return { label: 'Medium risk', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/40' }
    case 'low': return { label: 'Low risk', cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40' }
    default: return { label: risk ? `Risk: ${risk}` : 'Plan', cls: 'bg-muted text-muted-foreground border-border' }
  }
}

function stepStatusTone(status: string | undefined): string {
  switch ((status ?? '').toLowerCase()) {
    case 'complete': case 'completed': return 'text-emerald-400'
    case 'running': case 'in_progress': return 'text-sky-400'
    case 'blocked': return 'text-amber-400'
    case 'failed': return 'text-red-400'
    case 'skipped': return 'text-muted-foreground/70'
    default: return 'text-muted-foreground'
  }
}

// ── Sidebar subcomponents ─────────────────────────────────────────────────────

const PROJECT_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#ef4444',
  '#f97316', '#eab308', '#22c55e', '#14b8a6', '#3b82f6',
]

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {PROJECT_COLORS.map((c) => (
        <button
          key={c}
          type="button"
          title={c}
          onClick={() => onChange(c)}
          className={cn(
            'h-5 w-5 rounded-full border-2 transition',
            value === c ? 'border-white scale-110' : 'border-transparent opacity-70 hover:opacity-100',
          )}
          style={{ backgroundColor: c }}
        />
      ))}
    </div>
  )
}

function ProjectForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<Project>
  onSave: (name: string, description: string, color: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [color, setColor] = useState(initial?.color ?? '#6366f1')

  return (
    <div className="space-y-2 rounded-md border border-border bg-card p-3 text-xs">
      <input
        autoFocus
        type="text"
        placeholder="Project name"
        value={name}
        maxLength={64}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs outline-none focus:border-primary"
      />
      <input
        type="text"
        placeholder="Description (optional)"
        value={description}
        maxLength={200}
        onChange={(e) => setDescription(e.target.value)}
        className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs outline-none focus:border-primary"
      />
      <ColorPicker value={color} onChange={setColor} />
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel} className="rounded border border-border px-2 py-1 hover:bg-muted">
          Cancel
        </button>
        <button
          type="button"
          disabled={!name.trim()}
          onClick={() => onSave(name.trim(), description, color)}
          className="rounded bg-primary px-2 py-1 text-primary-foreground disabled:opacity-40"
        >
          Save
        </button>
      </div>
    </div>
  )
}

function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
  projects,
  onAssignProject,
}: {
  session: Session
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
  projects: Project[]
  onAssignProject: (projectId: string | null) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const title = session.name || 'Untitled'

  return (
    <div
      className={cn(
        'group flex items-center gap-1 rounded-md px-2 py-1.5 text-xs cursor-pointer',
        isActive ? 'bg-primary/10 text-foreground' : 'hover:bg-muted/60 text-muted-foreground hover:text-foreground',
      )}
      onClick={onSelect}
    >
      <MessageSquare size={11} className="shrink-0 opacity-50" />
      <span className="min-w-0 flex-1 truncate">{title}</span>
      <div className="relative shrink-0">
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v) }}
          className="hidden rounded p-0.5 hover:bg-muted group-hover:flex"
        >
          <MoreHorizontal size={12} />
        </button>
        {menuOpen && (
          <div
            className="absolute right-0 top-5 z-50 min-w-[140px] rounded-md border border-border bg-popover shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="py-1 text-xs">
              <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">Move to project</div>
              <button
                type="button"
                onClick={() => { onAssignProject(null); setMenuOpen(false) }}
                className="w-full px-3 py-1.5 text-left hover:bg-muted"
              >
                No project
              </button>
              {projects.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => { onAssignProject(p.id); setMenuOpen(false) }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-muted"
                >
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
                  <span className="truncate">{p.name}</span>
                </button>
              ))}
              <div className="my-1 border-t border-border" />
              <button
                type="button"
                onClick={() => { onDelete(); setMenuOpen(false) }}
                className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-red-400 hover:bg-muted"
              >
                <Trash2 size={11} /> Delete
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ProjectGroup({
  project,
  sessions,
  activeSessionId,
  projects,
  onSelectSession,
  onDeleteSession,
  onAssignProject,
  onEditProject,
  onDeleteProject,
  onNewSession,
}: {
  project: Project | null
  sessions: Session[]
  activeSessionId: string | null
  projects: Project[]
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onAssignProject: (sessionId: string, projectId: string | null) => void
  onEditProject: (p: Project) => void
  onDeleteProject: (id: string) => void
  onNewSession: (projectId: string | null) => void
}) {
  const [open, setOpen] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const isInbox = project === null

  return (
    <div className="mb-1">
      {/* Group header */}
      <div className="group flex items-center gap-1 rounded-md px-1 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground">
        <button type="button" onClick={() => setOpen((v) => !v)} className="flex flex-1 items-center gap-1 min-w-0">
          {open ? <ChevronDown size={12} className="shrink-0" /> : <ChevronRight size={12} className="shrink-0" />}
          {isInbox ? (
            <span className="truncate">No Project</span>
          ) : (
            <>
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: project.color }} />
              <span className="truncate">{project.name}</span>
            </>
          )}
          <span className="ml-auto shrink-0 tabular-nums opacity-50">{sessions.length}</span>
        </button>
        <div className="relative shrink-0 flex items-center gap-0.5">
          <button
            type="button"
            title="New chat in this project"
            onClick={() => onNewSession(isInbox ? null : project!.id)}
            className="hidden rounded p-0.5 hover:bg-muted group-hover:flex"
          >
            <Plus size={11} />
          </button>
          {!isInbox && (
            <>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v) }}
                className="hidden rounded p-0.5 hover:bg-muted group-hover:flex"
              >
                <MoreHorizontal size={11} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-5 z-50 min-w-[130px] rounded-md border border-border bg-popover text-xs shadow-lg">
                  <div className="py-1">
                    <button
                      type="button"
                      onClick={() => { onEditProject(project!); setMenuOpen(false) }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-muted"
                    >
                      <Pencil size={11} /> Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => { onDeleteProject(project!.id); setMenuOpen(false) }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-red-400 hover:bg-muted"
                    >
                      <Trash2 size={11} /> Delete
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Sessions */}
      {open && (
        <div className="ml-3 space-y-0.5">
          {sessions.length === 0 ? (
            <div className="px-2 py-1 text-[11px] text-muted-foreground/50 italic">No chats yet</div>
          ) : (
            sessions.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                isActive={activeSessionId === s.id}
                onSelect={() => onSelectSession(s.id)}
                onDelete={() => onDeleteSession(s.id)}
                projects={projects}
                onAssignProject={(pid) => onAssignProject(s.id, pid)}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── Chat panel subcomponents ──────────────────────────────────────────────────

function ActionApprovalPanel({ approval, onApprove, onReject }: { approval: PendingActionApproval | null; onApprove: () => void; onReject: () => void }) {
  if (!approval) return null
  const tone = planRiskTone(approval.risk)
  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${tone.cls}`}>{tone.label}</span>
          <span className="font-medium text-amber-200">{approval.title}</span>
        </div>
        {approval.detail && <p className="break-words text-muted-foreground">{approval.detail}</p>}
        {approval.diff && <pre className="mt-2 max-h-40 overflow-auto rounded-md border border-border bg-black/40 p-2 text-[11px] text-foreground">{approval.diff}</pre>}
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={onReject} className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1 text-xs hover:bg-muted"><X size={14} /> Reject</button>
          <button type="button" onClick={onApprove} className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:bg-primary/90"><Check size={14} /> Approve</button>
        </div>
      </div>
    </div>
  )
}

function ConnectionPill({ state }: { state: ConnectionState }) {
  if (state.kind === 'open') return null
  let label = ''
  let icon = <Loader2 size={12} className="animate-spin" />
  let cls = 'bg-amber-500/15 text-amber-300 border-amber-500/30'
  if (state.kind === 'connecting') label = 'Connecting…'
  else if (state.kind === 'reconnecting') label = `Reconnecting (attempt ${state.attempt})…`
  else if (state.kind === 'closed') { label = `Disconnected: ${state.reason}`; icon = <PlugZap size={12} />; cls = 'bg-muted text-muted-foreground border-border' }
  else if (state.kind === 'unauthorized') { label = `Authentication required: ${state.reason}`; icon = <AlertTriangle size={12} />; cls = 'bg-red-500/15 text-red-300 border-red-500/40' }
  else { label = 'Idle'; icon = <PlugZap size={12} />; cls = 'bg-muted text-muted-foreground border-border' }
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] ${cls}`}>{icon}{label}</span>
}

function RunPill({ state }: { state: RunState }) {
  if (state.kind === 'idle') return null
  if (state.kind === 'starting') return <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-300"><Loader2 size={12} className="animate-spin" /> Preparing run…</span>
  return <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-300"><Loader2 size={12} className="animate-spin" />Running{state.activeWorker ? ` · ${state.activeWorker}` : ''}</span>
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false)
  const onCopy = async () => {
    try { await navigator.clipboard.writeText(message.content); setCopied(true); setTimeout(() => setCopied(false), 1200) } catch { /* ignore */ }
  }
  const tone = message.role === 'user' ? 'bg-primary/10 border-primary/30' : message.role === 'system_error' ? 'bg-red-500/10 border-red-500/40' : message.role === 'system' ? 'bg-muted/40 border-border' : 'bg-card border-border'
  const senderLabel = message.role === 'user' ? 'You' : message.sender || 'ALOS'
  return (
    <div className={`group rounded-xl border ${tone} px-4 py-3`}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          <span className="font-medium">{senderLabel}</span>
          {message.fromHistory && <span className="rounded border border-border bg-muted/30 px-1 text-[10px] normal-case">history</span>}
        </div>
        <button type="button" onClick={onCopy} aria-label="Copy message" className="opacity-0 transition group-hover:opacity-100 focus:opacity-100" title="Copy">
          {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} className="text-muted-foreground hover:text-foreground" />}
        </button>
      </div>
      <div className="prose prose-sm max-w-none break-words text-sm text-foreground prose-invert prose-pre:bg-black/40 prose-pre:text-xs prose-code:before:content-none prose-code:after:content-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
      </div>
    </div>
  )
}

function PlanPanel({ plan, pendingApproval, onApprove, onReject }: { plan: RunPlan | null; pendingApproval: PendingApproval | null; onApprove: () => void; onReject: () => void }) {
  if (!plan) return null
  const tone = planRiskTone(plan.risk)
  const steps: PlanStep[] = Array.isArray(plan.steps) ? plan.steps : []
  const isAwaitingApproval = !!pendingApproval
  return (
    <div className="mx-auto max-w-3xl border-b border-border bg-card/40 px-6 py-3 text-xs">
      <div className="mb-2 flex items-center gap-2">
        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${tone.cls}`}>{tone.label}</span>
        <span className="text-muted-foreground">{steps.length} step{steps.length === 1 ? '' : 's'}</span>
        {isAwaitingApproval && <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">Approval required</span>}
      </div>
      <ol className="space-y-1">
        {steps.map((s, i) => (
          <li key={s.id || i} className={`flex items-start gap-2 rounded-md px-2 py-1 ${plan.current_step_id === s.id ? 'bg-muted/40' : ''}`}>
            <span className="w-5 text-right tabular-nums text-muted-foreground">{i + 1}.</span>
            <span className={`flex-1 ${stepStatusTone(s.status)}`}>{s.title || s.id}{s.required_verification && <span className="ml-1 text-[10px] text-amber-400">[verify]</span>}</span>
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{s.status || 'pending'}</span>
          </li>
        ))}
      </ol>
      {isAwaitingApproval && (
        <div className="mt-3 flex items-center justify-end gap-2">
          <button type="button" onClick={onReject} className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1 text-xs hover:bg-muted"><X size={14} /> Reject</button>
          <button type="button" onClick={onApprove} className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:bg-primary/90"><Check size={14} /> Approve plan</button>
        </div>
      )}
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function ChatView() {
  const apiKey = useAuth((s) => s.apiKey)

  // ── Sidebar state ────────────────────────────────────────────────────────
  const [projects, setProjects] = useState<Project[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [sidebarLoading, setSidebarLoading] = useState(true)
  const [newProjectOpen, setNewProjectOpen] = useState(false)
  const [editingProject, setEditingProject] = useState<Project | null>(null)

  // ── Chat state ───────────────────────────────────────────────────────────
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const [bootstrapping, setBootstrapping] = useState(true)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionTitle, setSessionTitle] = useState<string>('New session')
  const [plan, setPlan] = useState<RunPlan | null>(null)
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null)
  const [pendingActionApproval, setPendingActionApproval] = useState<PendingActionApproval | null>(null)
  const [statusLine, setStatusLine] = useState<string | null>(null)
  const [setupRequired, setSetupRequired] = useState<string | null>(null)
  const [connection, setConnection] = useState<ConnectionState>({ kind: 'idle' })
  const [runState, setRunState] = useState<RunState>({ kind: 'idle' })

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<number | null>(null)
  const attemptRef = useRef(0)
  const wantOpenRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const planRef = useRef<RunPlan | null>(null)
  const openSocketRef = useRef<() => void>(() => {})

  useEffect(() => { planRef.current = plan }, [plan])

  // ── Sidebar data loading ─────────────────────────────────────────────────
  const loadSidebar = useCallback(async () => {
    setSidebarLoading(true)
    try {
      const [p, s] = await Promise.all([api.listProjects(), api.listSessions()])
      setProjects(p)
      setSessions(s)
    } catch {
      // non-fatal — sidebar just shows empty
    } finally {
      setSidebarLoading(false)
    }
  }, [])

  useEffect(() => { void loadSidebar() }, [loadSidebar])

  // ── Agent context ────────────────────────────────────────────────────────
  useEffect(() => {
    return registerModuleAgentContextProvider('chat', () => ({
      module_id: 'chat',
      module_name: 'Chat',
      captured_at: new Date().toISOString(),
      payload: {
        sessionId,
        sessionTitle,
        runState,
        messageCount: messages.length,
        latestMessages: messages.slice(-8).map((m) => ({ role: m.role, content: m.content.slice(0, 1000) })),
      },
    }))
  }, [sessionId, sessionTitle, runState, messages])

  // ── Session bootstrap ────────────────────────────────────────────────────
  const hydrateFromState = useCallback((id: string, state: SessionStateResponse, title: string) => {
    setSessionId(id)
    setSessionTitle(title)
    const hist: ChatMessage[] = []
    ;(state.messages || []).forEach((m, i) => { const cm = langchainToChatMessage(m, i); if (cm) hist.push(cm) })
    setMessages(hist)
    setPlan(state.run_plan ?? null)
    if (state.active_run && state.active_run.run) {
      setRunState({ kind: 'running', runId: state.active_run.run.id, activeWorker: state.active_run.run.active_worker ?? null })
    } else {
      setRunState({ kind: 'idle' })
    }
  }, [])

  const bootstrapSession = useCallback(async () => {
    setBootstrapping(true)
    setBootstrapError(null)
    setMessages([])
    setPlan(null)
    setPendingApproval(null)
    setPendingActionApproval(null)
    setStatusLine(null)
    setSetupRequired(null)
    try {
      const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(ACTIVE_SESSION_KEY) : null
      let chosen: { id: string; title: string } | null = null

      if (stored) {
        try {
          const state = await api.getSessionState(stored)
          chosen = { id: stored, title: 'Conversation' }
          hydrateFromState(stored, state, chosen.title)
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 404)) throw err
          localStorage.removeItem(ACTIVE_SESSION_KEY)
        }
      }

      if (!chosen) {
        const sessionList = await api.listSessions()
        if (sessionList.length > 0) {
          const latest = sessionList[0]
          chosen = { id: latest.id, title: latest.name || 'Conversation' }
          const state = await api.getSessionState(latest.id)
          hydrateFromState(latest.id, state, chosen.title)
        } else {
          const fresh = await api.createSession('New conversation')
          chosen = { id: fresh.id, title: fresh.name || 'New conversation' }
          setSessionId(fresh.id)
          setSessionTitle(chosen.title)
          setMessages([])
          // Refresh sidebar to show new session
          void loadSidebar()
        }
      }

      if (chosen) localStorage.setItem(ACTIVE_SESSION_KEY, chosen.id)
    } catch (err) {
      setBootstrapError(err instanceof Error ? err.message : String(err))
    } finally {
      setBootstrapping(false)
    }
  }, [hydrateFromState, loadSidebar])

  useEffect(() => { void bootstrapSession() }, [bootstrapSession])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, plan, runState])

  // ── WebSocket ────────────────────────────────────────────────────────────
  const sendFrame = useCallback((frame: ChatWsClientFrame) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(frame)); return true }
    return false
  }, [])

  const handleFrame = useCallback((frame: ChatWsServerFrame) => {
    switch (frame.type) {
      case 'chat_output': {
        const sender = (frame as { sender: string }).sender
        const content = (frame as { content: string }).content
        setMessages((prev) => [...prev, { id: clientId(), role: classifySender(sender), sender, content, ts: Date.now() }])
        break
      }
      case 'status': setStatusLine((frame as { message: string }).message || null); break
      case 'setup_required':
        setSetupRequired((frame as { message: string }).message || 'Provider setup is required before ALOS can run.')
        setRunState({ kind: 'idle' })
        break
      case 'run_started': setRunState({ kind: 'running', runId: (frame as { run_id: string }).run_id }); break
      case 'run_event': {
        const ev = (frame as { event: { active_worker?: string | null; event_type?: string; payload?: Record<string, unknown> } }).event
        if (ev && 'active_worker' in ev) setRunState((rs) => rs.kind === 'running' ? { ...rs, activeWorker: ev.active_worker ?? rs.activeWorker } : rs)
        if (ev?.event_type === 'run_completed' || ev?.event_type === 'run_cancelled' || ev?.event_type === 'run_failed') {
          setRunState({ kind: 'idle' })
          setPendingActionApproval(null)
          if (ev.event_type === 'run_failed') setStatusLine(typeof ev.payload?.reason === 'string' ? `Run failed: ${ev.payload.reason}` : 'Run failed.')
          else if (ev.event_type === 'run_cancelled') setStatusLine('Run cancelled.')
        }
        break
      }
      case 'run_resume': {
        const replay = (frame as { replay: { run?: { id?: string; active_worker?: string | null } } }).replay
        if (replay?.run) setRunState({ kind: 'running', runId: replay.run.id, activeWorker: replay.run.active_worker ?? null })
        break
      }
      case 'plan_update': {
        const next = (frame as { plan: RunPlan }).plan
        setPlan(next)
        if (next?.needs_approval && next.approval_id) setPendingApproval({ approvalId: next.approval_id, plan: next })
        else setPendingApproval(null)
        break
      }
      case 'plan_approval_request': case 'plan_request': {
        const f = frame as { approval_id: string; plan?: RunPlan }
        if (f.approval_id) { if (f.plan) setPlan(f.plan); setPendingApproval({ approvalId: f.approval_id, plan: f.plan ?? planRef.current ?? { steps: [] } }); setRunState({ kind: 'running', activeWorker: 'Awaiting approval' }); setStatusLine('Plan approval required.') }
        break
      }
      case 'auth_request': {
        const f = frame as { approval_id: string; file_path?: string; diff?: string; risk?: string }
        if (f.approval_id) setPendingActionApproval({ approvalId: f.approval_id, kind: 'write', risk: f.risk, title: 'Disk write approval required', detail: f.file_path ? `Requested file: ${f.file_path}` : undefined, diff: f.diff })
        break
      }
      case 'patch_request': {
        const f = frame as { approval_id: string; proposal?: { file?: unknown; diff?: unknown }; risk?: string }
        if (f.approval_id) setPendingActionApproval({ approvalId: f.approval_id, kind: 'patch', risk: f.risk, title: 'Patch approval required', detail: typeof f.proposal?.file === 'string' ? `Requested file: ${f.proposal.file}` : undefined, diff: typeof f.proposal?.diff === 'string' ? f.proposal.diff : undefined })
        break
      }
      case 'plan_rejected': {
        const msg = (frame as { message: string }).message
        if (msg) setMessages((prev) => [...prev, { id: clientId(), role: 'system', sender: 'System', content: msg, ts: Date.now() }])
        setPendingApproval(null)
        break
      }
      case 'execution_complete':
        setRunState({ kind: 'idle' }); setStatusLine(null); setPendingApproval(null); setPendingActionApproval(null)
        break
      case 'title_update': {
        const t = (frame as { title: string }).title
        if (t) { setSessionTitle(t); setSessions((prev) => prev.map((s) => s.id === sessionId ? { ...s, name: t } : s)) }
        break
      }
      default: break
    }
  }, [sessionId])

  const scheduleReconnect = useCallback((reason: string) => {
    if (!wantOpenRef.current) return
    if (attemptRef.current >= MAX_RECONNECT_ATTEMPTS) { setConnection({ kind: 'closed', reason: `${reason} (gave up after ${attemptRef.current} attempts)` }); return }
    attemptRef.current += 1
    const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, attemptRef.current - 1), RECONNECT_CAP_MS)
    setConnection({ kind: 'reconnecting', attempt: attemptRef.current, nextDelayMs: delay })
    reconnectTimer.current = window.setTimeout(() => { reconnectTimer.current = null; openSocketRef.current() }, delay)
  }, [])

  const openSocket = useCallback(() => {
    if (!sessionId || !apiKey) return
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return
    setConnection({ kind: 'connecting' })
    let ws: WebSocket
    try { ws = api.openSocket(sessionId) } catch (err) { scheduleReconnect(err instanceof Error ? err.message : String(err)); return }
    wsRef.current = ws
    ws.onopen = () => { attemptRef.current = 0; setConnection({ kind: 'open' }) }
    ws.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data as string)
        if (parsed && typeof parsed === 'object' && typeof parsed.type === 'string') handleFrame(parsed as ChatWsServerFrame)
      } catch { /* ignore */ }
    }
    ws.onerror = () => { /* close will follow */ }
    ws.onclose = (evt) => {
      wsRef.current = null
      if (evt.code === 4401) { wantOpenRef.current = false; setConnection({ kind: 'unauthorized', reason: evt.reason || 'API key rejected' }); return }
      if (wantOpenRef.current) scheduleReconnect(evt.reason || `closed (code ${evt.code})`)
      else setConnection({ kind: 'closed', reason: evt.reason || 'closed' })
    }
  }, [apiKey, handleFrame, scheduleReconnect, sessionId])

  useEffect(() => { openSocketRef.current = openSocket }, [openSocket])

  useEffect(() => {
    if (!sessionId || !apiKey) return
    wantOpenRef.current = true
    attemptRef.current = 0
    openSocket()
    return () => {
      wantOpenRef.current = false
      if (reconnectTimer.current !== null) { window.clearTimeout(reconnectTimer.current); reconnectTimer.current = null }
      try { wsRef.current?.close() } catch { /* ignore */ }
      wsRef.current = null
    }
  }, [sessionId, apiKey, openSocket])

  // ── Session switch ───────────────────────────────────────────────────────
  const switchToSession = useCallback(async (id: string) => {
    if (id === sessionId) return
    wantOpenRef.current = false
    try { wsRef.current?.close() } catch { /* ignore */ }
    wsRef.current = null
    setBootstrapping(true)
    setMessages([])
    setPlan(null)
    setPendingApproval(null)
    setPendingActionApproval(null)
    setStatusLine(null)
    setSetupRequired(null)
    try {
      const state = await api.getSessionState(id)
      const title = sessions.find((s) => s.id === id)?.name || 'Conversation'
      hydrateFromState(id, state, title)
      localStorage.setItem(ACTIVE_SESSION_KEY, id)
    } catch (err) {
      setBootstrapError(err instanceof Error ? err.message : String(err))
    } finally {
      setBootstrapping(false)
    }
  }, [sessionId, sessions, hydrateFromState])

  // ── User actions ─────────────────────────────────────────────────────────
  const onNewSession = async (projectId: string | null = null) => {
    try {
      wantOpenRef.current = false
      try { wsRef.current?.close() } catch { /* ignore */ }
      wsRef.current = null
      setBootstrapping(true)
      const fresh = await api.createSession('New conversation', projectId)
      localStorage.setItem(ACTIVE_SESSION_KEY, fresh.id)
      setSessionId(fresh.id)
      setSessionTitle(fresh.name || 'New conversation')
      setMessages([])
      setPlan(null)
      setPendingApproval(null)
      setPendingActionApproval(null)
      setRunState({ kind: 'idle' })
      setStatusLine(null)
      setSetupRequired(null)
      setSessions((prev) => [{ ...fresh, name: fresh.name || 'New conversation' }, ...prev])
    } catch (err) {
      setBootstrapError(`Could not create a new conversation: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBootstrapping(false)
    }
  }

  const onDeleteSession = async (id: string) => {
    try {
      await api.deleteSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
      if (id === sessionId) void bootstrapSession()
    } catch { /* ignore */ }
  }

  const onAssignProject = async (sid: string, projectId: string | null) => {
    try {
      await api.assignSessionProject(sid, projectId)
      setSessions((prev) => prev.map((s) => s.id === sid ? { ...s, project_id: projectId } : s))
    } catch { /* ignore */ }
  }

  const onCreateProject = async (name: string, description: string, color: string) => {
    try {
      const p = await api.createProject(name, description, color)
      setProjects((prev) => [...prev, p])
      setNewProjectOpen(false)
    } catch { /* ignore */ }
  }

  const onUpdateProject = async (id: string, name: string, description: string, color: string) => {
    try {
      await api.updateProject(id, { name, description, color })
      setProjects((prev) => prev.map((p) => p.id === id ? { ...p, name, description, color } : p))
      setEditingProject(null)
    } catch { /* ignore */ }
  }

  const onDeleteProject = async (id: string) => {
    try {
      await api.deleteProject(id)
      setProjects((prev) => prev.filter((p) => p.id !== id))
      setSessions((prev) => prev.map((s) => s.project_id === id ? { ...s, project_id: null } : s))
    } catch { /* ignore */ }
  }

  const onSubmit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || connection.kind !== 'open' || runState.kind !== 'idle') return
    setSetupRequired(null)
    setMessages((prev) => [...prev, { id: clientId(), role: 'user', sender: 'You', content: trimmed, ts: Date.now() }])
    if (sendFrame({ type: 'chat_input', text: trimmed })) {
      setRunState({ kind: 'starting' })
      setDraft('')
    } else {
      setMessages((prev) => [...prev, { id: clientId(), role: 'system_error', sender: 'System_Error', content: 'Could not send — the backend connection is not open. Reconnecting…', ts: Date.now() }])
    }
  }

  const onStop = () => {
    if (runState.kind === 'idle' && !pendingApproval && !pendingActionApproval) return
    setStatusLine('Stop requested. Cancelling run...')
    if (!sendFrame({ type: 'stop_execution' })) {
      setRunState({ kind: 'idle' })
      setStatusLine('Stop requested, but the backend connection is not open.')
    }
  }
  const onApprovePlan = () => { if (!pendingApproval) return; sendFrame({ type: 'plan_response', approval_id: pendingApproval.approvalId, approved: true }); setPendingApproval(null); setRunState({ kind: 'starting' }); setStatusLine('Plan approved. Starting run…') }
  const onRejectPlan = () => { if (!pendingApproval) return; sendFrame({ type: 'plan_response', approval_id: pendingApproval.approvalId, approved: false }); setPendingApproval(null); setRunState({ kind: 'idle' }) }
  const onApproveAction = () => { if (!pendingActionApproval) return; sendFrame({ type: 'auth_response', approval_id: pendingActionApproval.approvalId, approved: true }); setPendingActionApproval(null) }
  const onRejectAction = () => { if (!pendingActionApproval) return; sendFrame({ type: 'auth_response', approval_id: pendingActionApproval.approvalId, approved: false }); setPendingActionApproval(null) }
  const onForceReconnect = () => { if (reconnectTimer.current !== null) { window.clearTimeout(reconnectTimer.current); reconnectTimer.current = null }; attemptRef.current = 0; try { wsRef.current?.close() } catch { /* ignore */ }; wsRef.current = null; wantOpenRef.current = true; openSocket() }

  const draftDisabled = bootstrapping || runState.kind !== 'idle' || connection.kind !== 'open' || !!pendingApproval || !!pendingActionApproval

  const composerHint = useMemo(() => {
    if (bootstrapping) return 'Loading conversation…'
    if (connection.kind === 'unauthorized') return 'Sign in again from the login screen to continue.'
    if (connection.kind !== 'open') return 'Reconnecting to the swarm…'
    if (pendingApproval) return 'Approve or reject the plan above before sending more.'
    if (pendingActionApproval) return 'Approve or reject the requested action before sending more.'
    if (runState.kind !== 'idle') return 'A run is in progress — Stop it before sending again.'
    return 'Enter to send · Shift+Enter for newline'
  }, [bootstrapping, connection.kind, pendingActionApproval, pendingApproval, runState.kind])

  // Group sessions by project
  const sessionsByProject = useMemo(() => {
    const map = new Map<string | null, Session[]>()
    map.set(null, [])
    for (const p of projects) map.set(p.id, [])
    for (const s of sessions) {
      const pid = s.project_id ?? null
      if (!map.has(pid)) map.set(null, [...(map.get(null) ?? [])])
      map.set(pid, [...(map.get(pid) ?? []), s])
    }
    return map
  }, [sessions, projects])

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* ── Sidebar ── */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card/20">
        {/* Sidebar header */}
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-xs font-semibold text-foreground">Chats</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              title="New project"
              onClick={() => { setNewProjectOpen(true); setEditingProject(null) }}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <FolderPlus size={13} />
            </button>
            <button
              type="button"
              title="New chat"
              onClick={() => void onNewSession(null)}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Plus size={13} />
            </button>
          </div>
        </div>

        {/* New project form */}
        {newProjectOpen && (
          <div className="border-b border-border p-2">
            <ProjectForm
              onSave={onCreateProject}
              onCancel={() => setNewProjectOpen(false)}
            />
          </div>
        )}

        {/* Edit project form */}
        {editingProject && (
          <div className="border-b border-border p-2">
            <ProjectForm
              initial={editingProject}
              onSave={(name, description, color) => void onUpdateProject(editingProject.id, name, description, color)}
              onCancel={() => setEditingProject(null)}
            />
          </div>
        )}

        {/* Session list */}
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 text-xs">
          {sidebarLoading ? (
            <div className="flex items-center justify-center py-6 text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
            </div>
          ) : (
            <>
              {/* Projects */}
              {projects.map((p) => (
                <ProjectGroup
                  key={p.id}
                  project={p}
                  sessions={sessionsByProject.get(p.id) ?? []}
                  activeSessionId={sessionId}
                  projects={projects}
                  onSelectSession={(id) => void switchToSession(id)}
                  onDeleteSession={(id) => void onDeleteSession(id)}
                  onAssignProject={(sid, pid) => void onAssignProject(sid, pid)}
                  onEditProject={setEditingProject}
                  onDeleteProject={(id) => void onDeleteProject(id)}
                  onNewSession={(pid) => void onNewSession(pid)}
                />
              ))}

              {/* Inbox — sessions with no project */}
              <ProjectGroup
                project={null}
                sessions={sessionsByProject.get(null) ?? []}
                activeSessionId={sessionId}
                projects={projects}
                onSelectSession={(id) => void switchToSession(id)}
                onDeleteSession={(id) => void onDeleteSession(id)}
                onAssignProject={(sid, pid) => void onAssignProject(sid, pid)}
                onEditProject={setEditingProject}
                onDeleteProject={(id) => void onDeleteProject(id)}
                onNewSession={(pid) => void onNewSession(pid)}
              />
            </>
          )}
        </div>
      </aside>

      {/* ── Chat panel ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-border bg-card/30 px-4 py-2">
          <FolderOpen size={13} className="shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{sessionTitle}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2">
              <ConnectionPill state={connection} />
              <RunPill state={runState} />
              {statusLine && <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground">{statusLine}</span>}
            </div>
          </div>
          <div className="flex items-center gap-1">
            {(connection.kind === 'closed' || connection.kind === 'reconnecting' || connection.kind === 'unauthorized') && (
              <button type="button" onClick={onForceReconnect} title="Reconnect" className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted">
                <RefreshCcw size={12} /> Reconnect
              </button>
            )}
            <button type="button" onClick={() => void onNewSession(null)} title="Start a new conversation" className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted">
              <Plus size={12} /> New
            </button>
          </div>
        </div>

        <PlanPanel plan={plan} pendingApproval={pendingApproval} onApprove={onApprovePlan} onReject={onRejectPlan} />
        <ActionApprovalPanel approval={pendingActionApproval} onApprove={onApproveAction} onReject={onRejectAction} />

        {setupRequired && <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-300">{setupRequired} Open Settings to finish provider configuration.</div>}
        {bootstrapError && (
          <div className="flex items-start justify-between gap-2 border-b border-red-500/40 bg-red-500/10 px-4 py-2 text-xs text-red-300">
            <span className="break-words">{bootstrapError}</span>
            <button type="button" onClick={() => void bootstrapSession()} className="inline-flex items-center gap-1 rounded-md border border-red-500/40 bg-background px-2 py-0.5 text-xs hover:bg-muted"><RefreshCcw size={12} /> Retry</button>
          </div>
        )}

        {/* Messages */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-3 px-4 py-6">
            {bootstrapping && messages.length === 0 ? (
              <div className="flex items-center justify-center gap-2 rounded-xl border border-border bg-card/30 p-8 text-sm text-muted-foreground"><Loader2 size={16} className="animate-spin" /> Loading conversation…</div>
            ) : messages.length === 0 ? (
              <div className="rounded-xl border border-border bg-card/30 p-8 text-center">
                <h2 className="text-lg font-semibold tracking-tight">ALOS is ready.</h2>
                <p className="mt-2 text-sm text-muted-foreground">Ask a question, draft a plan, or assign a task. Plans flagged high-risk will pause for your approval before any agent acts.</p>
              </div>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-border bg-card/30">
          <div className="mx-auto max-w-3xl px-4 py-3">
            <form
              onSubmit={(e) => { e.preventDefault(); onSubmit(draft) }}
              className={cn(
                'flex items-end gap-2 rounded-xl border bg-background p-2 transition',
                draftDisabled ? 'border-border opacity-70' : 'border-border focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20',
              )}
            >
              <textarea
                value={draft}
                disabled={draftDisabled}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setDraft(e.target.value)}
                onKeyDown={(e: ReactKeyboardEvent<HTMLTextAreaElement>) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!draftDisabled) onSubmit(draft) } }}
                rows={1}
                placeholder={connection.kind === 'open' ? (runState.kind === 'idle' ? 'Message ALOS…' : 'Run in progress…') : 'Connecting…'}
                className="max-h-40 min-h-[32px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
              />
              {runState.kind !== 'idle' || pendingApproval || pendingActionApproval ? (
                <button type="button" onClick={onStop} title="Stop run" className="flex h-8 w-8 items-center justify-center rounded-md border border-red-500/40 bg-red-500/10 text-red-300 transition hover:bg-red-500/20"><Square size={14} /></button>
              ) : (
                <button type="submit" disabled={draftDisabled || !draft.trim()} className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground transition disabled:cursor-not-allowed disabled:opacity-40"><Send size={14} /></button>
              )}
            </form>
            <p className="mt-2 px-1 text-[11px] text-muted-foreground/70">{composerHint}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
