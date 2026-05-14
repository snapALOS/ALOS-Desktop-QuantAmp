import { useState } from 'react'
import { Plus, Settings, LogOut, Shield, Activity, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/store/auth'
import logo from '@/assets/logo-alos.svg'
import { type BackendStatus } from '@/hooks/useBackendHealth'

type View = 'chat' | 'sessions' | 'admin' | 'settings'

interface AppShellProps {
  backendStatus: BackendStatus
  children?: React.ReactNode
}

/**
 * Two-column shell: fixed-width left rail + main content.
 * Uses CSS grid with explicit sizing so nothing overflows the viewport —
 * no absolute positioning tricks, no overflow-chain surprises.
 */
export function AppShell({ backendStatus, children }: AppShellProps) {
  const [view, setView] = useState<View>('chat')
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)

  return (
    <div
      className="grid h-full w-full bg-background text-foreground"
      style={{ gridTemplateColumns: '64px 1fr' }}
    >
      {/* Left rail */}
      <aside className="flex flex-col items-center border-r border-border bg-card/40 py-3">
        <div className="flex h-10 w-10 items-center justify-center">
          <img src={logo} alt="ALOS" className="h-8 w-8" />
        </div>

        <div className="mt-4 flex flex-1 flex-col items-center gap-1">
          <RailButton icon={<MessageSquare size={18} />} label="Chat" active={view === 'chat'} onClick={() => setView('chat')} />
          <RailButton icon={<Activity size={18} />} label="Runs" active={view === 'sessions'} onClick={() => setView('sessions')} />
          <RailButton icon={<Shield size={18} />} label="Admin" active={view === 'admin'} onClick={() => setView('admin')} />
        </div>

        <div className="flex flex-col items-center gap-1 pb-1">
          <RailButton icon={<Settings size={18} />} label="Settings" active={view === 'settings'} onClick={() => setView('settings')} />
          <RailButton icon={<LogOut size={18} />} label="Sign out" onClick={logout} />
        </div>
      </aside>

      {/* Main column */}
      <div className="grid h-full min-h-0" style={{ gridTemplateRows: '40px 1fr' }}>
        <header className="flex items-center justify-between border-b border-border bg-card/30 px-4 text-xs">
          <div className="flex items-center gap-3">
            <span className="font-semibold tracking-tight text-foreground">ALOS</span>
            <span className="text-muted-foreground">·</span>
            <span className="capitalize text-muted-foreground">{view}</span>
          </div>
          <div className="flex items-center gap-3">
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

        <main className="min-h-0 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}

function RailButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  active?: boolean
  onClick?: () => void
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={cn(
        'flex h-10 w-10 items-center justify-center rounded-lg transition',
        'text-muted-foreground hover:bg-muted hover:text-foreground',
        active && 'bg-primary/15 text-primary hover:bg-primary/20'
      )}
    >
      {icon}
    </button>
  )
}

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

// Exported for future use
export function NewSessionButton() {
  return (
    <button className="mx-2 mt-2 flex items-center justify-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs font-medium hover:border-primary/50 hover:text-primary">
      <Plus size={14} />
      New chat
    </button>
  )
}
