/**
 * ModuleShell — hosts the active module's view.
 *
 * This component is intentionally dumb: it draws the header and hands
 * content rendering to `defaultRenderFor()` in `module-views.tsx`. To add a
 * new module view, edit module-views.tsx — NOT this file.
 */

import type { BackendStatus } from '@/hooks/useBackendHealth'
import type { ModuleEntry } from '@/shell/module-registry'
import { ModuleErrorBoundary } from '@/shell/ModuleErrorBoundary'
import { defaultRenderFor } from '@/shell/module-views'
import { getModuleAgentContext } from '@/shell/agent-context'
import { useActiveModule } from '@/store/active-module'
import { useAuth } from '@/store/auth'
import { api } from '@/api'
import { cn } from '@/lib/utils'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { ChatWsServerFrame, ChatWsClientFrame } from '@/types/api'

interface ModuleShellProps {
  backendStatus: BackendStatus
  registry: ModuleEntry[]
}

export function ModuleShell({ backendStatus, registry }: ModuleShellProps) {
  const activeId = useActiveModule((s) => s.activeId)
  const user = useAuth((s) => s.user)
  const apiKey = useAuth((s) => s.apiKey)
  const [assistOpen, setAssistOpen] = useState(false)

  const activeModule = registry.find((m) => m.id === activeId)
  const displayName = activeModule?.displayName ?? activeId

  return (
    <div className="relative grid h-full min-h-0" style={{ gridTemplateRows: '40px 1fr' }}>
      {/* Header bar */}
      <header className="flex items-center justify-between border-b border-border bg-card/30 px-4 text-xs">
        <div className="flex items-center gap-3">
          <span className="font-semibold tracking-tight text-foreground">ALOS</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">{displayName}</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-muted disabled:opacity-50"
            disabled={!apiKey || backendStatus !== 'online'}
            onClick={() => setAssistOpen((value) => !value)}
          >
            ALOS Assist
          </button>
          {user && (
            <span className="text-muted-foreground">
              {user.username}
              <span className="mx-1 opacity-40">·</span>
              <span className="uppercase tracking-wider">{user.role}</span>
            </span>
          )}
          <StatusDot status={backendStatus} />
        </div>
      </header>

      {/* Module content */}
      <main className="min-h-0 overflow-hidden">
        <ModuleErrorBoundary moduleId={activeId} moduleName={displayName}>
          {defaultRenderFor(activeId)}
        </ModuleErrorBoundary>
      </main>
      {assistOpen && (
        <AssistDrawer
          moduleId={activeId}
          moduleName={displayName}
          onClose={() => setAssistOpen(false)}
        />
      )}
    </div>
  )
}

interface AssistMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

interface PendingAssistApproval {
  approvalId: string
  title: string
  kind: 'plan' | 'auth'
}

function AssistDrawer({
  moduleId,
  moduleName,
  onClose,
}: {
  moduleId: string
  moduleName: string
  onClose: () => void
}) {
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<AssistMessage[]>([
    { role: 'system', content: `Ready to help inside ${moduleName}.` },
  ])
  const [status, setStatus] = useState<'idle' | 'connecting' | 'open' | 'error'>('idle')
  const [pending, setPending] = useState<PendingAssistApproval | null>(null)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    return () => {
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [])

  async function ensureSocket(): Promise<WebSocket> {
    const existing = socketRef.current
    if (existing && existing.readyState === WebSocket.OPEN) return existing
    setStatus('connecting')
    const session = await api.createSession(`${moduleName} assist`)
    const socket = api.openSocket(session.id)
    return await new Promise((resolve, reject) => {
      socket.onopen = () => {
        socketRef.current = socket
        setStatus('open')
        resolve(socket)
      }
      socket.onerror = () => {
        setStatus('error')
        reject(new Error('ALOS Assist connection failed.'))
      }
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        setStatus((current) => (current === 'open' ? 'idle' : current))
      }
      socket.onmessage = (event) => handleFrame(event.data)
    })
  }

  function handleFrame(raw: string) {
    let frame: ChatWsServerFrame
    try {
      frame = JSON.parse(raw) as ChatWsServerFrame
    } catch {
      appendMessage({ role: 'system', content: raw })
      return
    }
    if (frame.type === 'chat_output') {
      appendMessage({ role: 'assistant', content: String(frame.content ?? '') })
    } else if (frame.type === 'status' || frame.type === 'system_log' || frame.type === 'setup_required') {
      const content = 'message' in frame ? frame.message : frame.content
      appendMessage({ role: 'system', content: String(content ?? '') })
    } else if (frame.type === 'plan_approval_request' || frame.type === 'plan_request') {
      setPending({ approvalId: String(frame.approval_id), title: 'Plan approval required', kind: 'plan' })
    } else if (frame.type === 'auth_request' || frame.type === 'patch_request') {
      setPending({ approvalId: String(frame.approval_id), title: 'Action approval required', kind: 'auth' })
    } else if (frame.type === 'execution_complete') {
      appendMessage({ role: 'system', content: 'Run complete.' })
    }
  }

  function appendMessage(message: AssistMessage) {
    setMessages((items) => [...items, message].slice(-80))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text) return
    try {
      const socket = await ensureSocket()
      const context = await getModuleAgentContext(moduleId, moduleName, api)
      const framedText = [
        `${moduleName} module assistance request.`,
        '',
        `User request: ${text}`,
      ].join('\n')
      socket.send(JSON.stringify({
        type: 'chat_input',
        text: framedText,
        module_context: { ...context },
      } satisfies ChatWsClientFrame))
      appendMessage({ role: 'user', content: text })
      setDraft('')
    } catch (error) {
      setStatus('error')
      appendMessage({ role: 'system', content: error instanceof Error ? error.message : String(error) })
    }
  }

  function resolvePending(approved: boolean) {
    if (!pending) return
    const frame: ChatWsClientFrame =
      pending.kind === 'plan'
        ? { type: 'plan_response', approval_id: pending.approvalId, approved }
        : { type: 'auth_response', approval_id: pending.approvalId, approved }
    socketRef.current?.send(JSON.stringify(frame))
    setPending(null)
  }

  return (
    <aside className="absolute right-3 top-12 z-50 flex h-[min(680px,calc(100%-4rem))] w-[min(420px,calc(100%-1.5rem))] flex-col rounded-md border border-border bg-background shadow-xl">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <div>
          <div className="text-sm font-semibold">ALOS Assist</div>
          <div className="text-[11px] text-muted-foreground">{moduleName} · {status}</div>
        </div>
        <button type="button" className="rounded-md px-2 py-1 text-xs hover:bg-muted" onClick={onClose}>
          Close
        </button>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-auto p-3 text-sm">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={cn(
              'rounded-md border border-border/60 p-2',
              message.role === 'user' ? 'bg-primary/10' : message.role === 'assistant' ? 'bg-card' : 'bg-muted/30 text-muted-foreground',
            )}
          >
            <div className="mb-1 text-[10px] uppercase tracking-wide opacity-70">{message.role}</div>
            <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>
          </div>
        ))}
      </div>
      {pending && (
        <div className="border-t border-border p-3 text-xs">
          <div className="mb-2 font-semibold">{pending.title}</div>
          <div className="flex gap-2">
            <button type="button" className="rounded-md bg-primary px-2 py-1 text-primary-foreground" onClick={() => resolvePending(true)}>
              Approve
            </button>
            <button type="button" className="rounded-md border border-border px-2 py-1" onClick={() => resolvePending(false)}>
              Reject
            </button>
          </div>
        </div>
      )}
      <form onSubmit={submit} className="flex gap-2 border-t border-border p-3">
        <textarea
          className="min-h-16 flex-1 resize-none rounded-md border border-border bg-background p-2 text-sm outline-none focus:border-primary"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={`Ask ALOS about ${moduleName}...`}
        />
        <button
          type="submit"
          disabled={!draft.trim() || status === 'connecting' || !!pending}
          className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </aside>
  )
}

// ---------------------------------------------------------------------------
// Status dot
// ---------------------------------------------------------------------------

function StatusDot({ status }: { status: BackendStatus }) {
  const { color, label } =
    status === 'online'
      ? { color: 'bg-[color:var(--color-success)]', label: 'Connected' }
      : status === 'connecting'
        ? { color: 'bg-[color:var(--color-warning)] animate-pulse', label: 'Connecting…' }
        : { color: 'bg-[color:var(--color-destructive)]', label: 'Offline' }

  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <span className={cn('h-2 w-2 rounded-full', color)} />
      <span>{label}</span>
    </div>
  )
}
