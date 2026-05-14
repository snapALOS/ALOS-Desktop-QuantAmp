import { useEffect, useState } from 'react'
import { api } from '../../../../src/api'
import { registerModuleAgentContextProvider } from '../../../../src/shell/agent-context'
import type { ChamberGate, ChamberSession } from '../../../../src/types/chamber'

function statusTone(status: string): string {
  switch (status) {
    case 'running':
      return 'text-sky-300'
    case 'passed':
    case 'written':
      return 'text-emerald-300'
    case 'failed':
    case 'blocked':
      return 'text-red-300'
    case 'overridden':
      return 'text-amber-300'
    default:
      return 'text-muted-foreground'
  }
}

export function ChamberView() {
  const [sessions, setSessions] = useState<ChamberSession[]>([])
  const [gates, setGates] = useState<ChamberGate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchState = async () => {
      try {
        setError(null)
        const [sessionData, gateData] = await Promise.all([
          api.chamberList(),
          api.chamberGates(),
        ])
        setSessions(sessionData.chambers || [])
        setGates(gateData.gates || [])
      } catch (error) {
        console.error('Failed to fetch chamber sessions:', error)
        setError(error instanceof Error ? error.message : 'Failed to fetch Chamber state')
      } finally {
        setLoading(false)
      }
    }

    fetchState()
    const timer = setInterval(fetchState, 5000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    return registerModuleAgentContextProvider('chamber', () => ({
      module_id: 'chamber',
      module_name: 'Chamber',
      captured_at: new Date().toISOString(),
      payload: {
        sessions: sessions.slice(0, 20),
        gates: gates.slice(0, 20),
        counts: gates.reduce<Record<string, number>>((acc, gate) => {
          acc[gate.status] = (acc[gate.status] || 0) + 1
          return acc
        }, {}),
      },
    }))
  }, [sessions, gates])

  return (
    <div className="flex h-full flex-col bg-card/10 p-6 overflow-auto">
      <header className="mb-8">
        <h2 className="text-2xl font-bold tracking-tight">ALOSChamber</h2>
        <p className="text-muted-foreground">Pre-write build, test, evidence, and approval gates.</p>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <div className="col-span-full">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Pre-write gates</h3>
          {loading && gates.length === 0 ? (
            <div className="animate-pulse rounded-md bg-card p-8 text-center text-muted-foreground">
              Loading Chamber gates...
            </div>
          ) : gates.length === 0 ? (
            <div className="rounded-md border border-dashed border-border bg-card/5 p-8 text-center text-muted-foreground">
              <p className="text-sm">No staged writes yet. Agent patches will appear here before they can touch disk.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {gates.map((gate) => {
                const lastEvidence = gate.evidence?.[gate.evidence.length - 1]
                return (
                  <div key={gate.id} className="rounded-md border border-border/50 bg-card p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-mono text-sm font-semibold">{gate.file}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {gate.id} · patch {gate.patch_id} · risk {gate.risk || 'unknown'}
                        </div>
                      </div>
                      <span className={`text-xs font-semibold uppercase ${statusTone(gate.status)}`}>
                        {gate.status}
                      </span>
                    </div>
                    {gate.commands.length > 0 && (
                      <div className="mt-3 flex flex-col gap-1">
                        {gate.commands.map((command) => (
                          <code key={command} className="rounded bg-background/80 px-2 py-1 text-[11px] text-muted-foreground">
                            {command}
                          </code>
                        ))}
                      </div>
                    )}
                    {lastEvidence && (
                      <div className="mt-3 rounded-md bg-background/60 p-2 text-xs">
                        <div className="flex justify-between gap-2">
                          <span className={statusTone(lastEvidence.status)}>{lastEvidence.status}</span>
                          <span className="text-muted-foreground">exit {lastEvidence.exit_code ?? '-'}</span>
                        </div>
                        {(lastEvidence.stderr || lastEvidence.stdout) && (
                          <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[10px] text-muted-foreground">
                            {(lastEvidence.stderr || lastEvidence.stdout || '').slice(-1000)}
                          </pre>
                        )}
                      </div>
                    )}
                    {gate.override && (
                      <div className="mt-2 text-xs text-amber-300">
                        Override approved by {gate.override.actor || 'unknown'}.
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="col-span-full">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">Active Sessions</h3>
          {loading && sessions.length === 0 ? (
            <div className="animate-pulse rounded-lg bg-card p-8 text-center text-muted-foreground">
              Initializing Chamber telemetry...
            </div>
          ) : sessions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-12 text-center text-muted-foreground bg-card/5">
              <p className="text-sm">No active chambers. Start a development task to initialize an isolated environment.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {sessions.map((session) => (
                <div key={session.id} className="flex items-center justify-between rounded-lg bg-card p-4 border border-border/50">
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                      {session.stack.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="font-mono text-sm font-semibold">{session.id}</div>
                      <div className="text-xs text-muted-foreground">Stack: {session.stack} · Active for {session.age_seconds}s</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1.5 text-xs font-medium text-[color:var(--color-success)]">
                      <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-success)]" />
                      Isolated
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg bg-card p-6 border border-border/50">
          <h4 className="font-semibold mb-2">Commit Strategy</h4>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Agent patches are staged, tested, and recorded before the mutation gate writes to disk.
          </p>
        </div>

        <div className="rounded-lg bg-card p-6 border border-border/50">
          <h4 className="font-semibold mb-2">Resource Limits</h4>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Failed gates block writes by default.<br />
            Overrides require explicit approval.<br />
            Evidence stays attached to each patch.
          </p>
        </div>

        <div className="rounded-lg bg-card p-6 border border-border/50">
          <h4 className="font-semibold mb-2">Lifespan (TTL)</h4>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Gate records remain visible after completion so failed, approved, and overridden writes can be recovered.
          </p>
        </div>
      </div>

      <div className="mt-auto pt-8 flex items-center justify-between text-[10px] text-muted-foreground font-mono uppercase tracking-widest opacity-40">
        <span>[ STATUS: GATED ]</span>
        <span>[ WRITES: STAGED ]</span>
        <span>[ VERSION: 0.2.0 ]</span>
      </div>
    </div>
  )
}
