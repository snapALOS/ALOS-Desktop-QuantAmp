import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import { invoke, listen } from '@/api/tauri'
import logo from '@/assets/logo-alos.svg'
import type { PreflightProgressEvent, PreflightReport } from '@/types/api'

interface Props {
  report: PreflightReport
  onResolved: () => void
}

/**
 * Blocks app startup while dependencies are missing. Two failure modes:
 *
 *   1. Python itself is missing or too old — we can't fix that from inside
 *      the app (macOS without admin/brew, Windows without installer). Show
 *      a link to the canonical installer and a "Recheck" button.
 *
 *   2. The venv or requirement packages are missing — we CAN fix that.
 *      Ask for explicit consent, then stream `pip install` output into a
 *      log pane. On success we call `launch_backend` and hand off.
 */
export function PreflightGate({ report, onResolved }: Props) {
  const [current, setCurrent] = useState<PreflightReport>(report)
  const [installing, setInstalling] = useState(false)
  const [lines, setLines] = useState<PreflightProgressEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  // Auto-scroll the log pane as new lines arrive.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [lines])

  // Subscribe to progress events while installing.
  useEffect(() => {
    if (!installing) return
    let unlisten: (() => void) | null = null
    ;(async () => {
      unlisten = await listen<PreflightProgressEvent>(
        'preflight-progress',
        (evt) => setLines((prev) => [...prev, evt]),
      )
    })()
    return () => {
      if (unlisten) unlisten()
    }
  }, [installing])

  async function recheck() {
    setError(null)
    try {
      const next = await invoke<PreflightReport>('preflight_check')
      setCurrent(next)
      if (next.ok) {
        await invoke('launch_backend')
        onResolved()
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function install() {
    setError(null)
    setLines([])
    setInstalling(true)
    try {
      const next = await invoke<PreflightReport>('preflight_install')
      setCurrent(next)
      if (next.ok) {
        await invoke('launch_backend')
        onResolved()
      } else {
        setError(
          'Install finished but some dependencies are still missing. See log for details.',
        )
      }
    } catch (e) {
      setError((e as Error).message || 'Install failed.')
    } finally {
      setInstalling(false)
    }
  }

  const pythonBlocking = !current.python_ok && !current.venv_exists
  const missingCount = current.missing_packages.length
  const needsAction =
    pythonBlocking || !current.venv_exists || missingCount > 0

  return (
    <div className="flex h-full w-full items-center justify-center overflow-y-auto bg-background p-8">
      <div className="w-full max-w-2xl">
        <div className="flex items-center gap-3">
          <img src={logo} alt="ALOS" className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Preparing ALOS
            </h1>
            <p className="text-xs text-muted-foreground">
              One-time setup — we're checking your Python environment.
            </p>
          </div>
        </div>

        <div className="mt-6 space-y-3 rounded-xl border border-border bg-card p-6 shadow-lg">
          <CheckRow
            ok={current.python_ok}
            label={
              current.python_ok
                ? `Python ${current.python_version ?? ''}`.trim()
                : `Python ${current.minimum_python}+ required`
            }
            detail={
              current.python_ok
                ? current.python_path ?? undefined
                : current.python_error ?? undefined
            }
          />
          <CheckRow
            ok={current.venv_exists}
            label={
              current.venv_exists
                ? 'Isolated ALOS environment ready'
                : 'Isolated ALOS environment not yet created'
            }
            detail={current.venv_path}
          />
          <CheckRow
            ok={current.venv_exists && missingCount === 0}
            label={
              missingCount === 0 && current.venv_exists
                ? `All ${current.required_packages.length} dependencies installed`
                : `${missingCount || current.required_packages.length} ${
                    missingCount > 0 ? 'missing' : 'pending'
                  } dependencies`
            }
            detail={
              missingCount > 0
                ? current.missing_packages.slice(0, 8).join(', ') +
                  (missingCount > 8 ? ` (+${missingCount - 8} more)` : '')
                : undefined
            }
          />

          {pythonBlocking && !installing && (
            <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
              <p className="font-semibold text-amber-300">
                Python {current.minimum_python}+ is required.
              </p>
              <p className="mt-1 text-amber-200/80">
                ALOS can't install Python for you — it needs admin-level access
                to your system. Install it once and we'll take care of the rest.
              </p>
              <div className="mt-2 flex gap-2">
                <a
                  href="https://www.python.org/downloads/"
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-md border border-amber-400/50 bg-amber-400/20 px-3 py-1.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-400/30"
                >
                  Get Python
                </a>
                <button
                  type="button"
                  onClick={recheck}
                  className="rounded-md border border-border bg-background px-3 py-1.5 text-[11px] font-semibold text-foreground"
                >
                  Recheck
                </button>
              </div>
            </div>
          )}

          {!pythonBlocking && needsAction && !installing && (
            <div className="mt-4 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-xs">
              <p className="font-semibold text-primary">
                Install {missingCount || current.required_packages.length}{' '}
                dependencies?
              </p>
              <p className="mt-1 text-muted-foreground">
                We'll create an isolated environment at{' '}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
                  {current.venv_path}
                </code>{' '}
                and install only what ALOS needs. Nothing touches your system
                Python.
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={install}
                  className="rounded-md bg-primary px-3 py-1.5 text-[11px] font-semibold text-primary-foreground hover:brightness-110"
                >
                  Install dependencies
                </button>
                <button
                  type="button"
                  onClick={recheck}
                  className="rounded-md border border-border bg-background px-3 py-1.5 text-[11px] font-semibold text-foreground"
                >
                  Recheck
                </button>
              </div>
            </div>
          )}

          {installing && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Installing… this usually takes 1-3 minutes.
              </div>
              <div
                ref={logRef}
                className="h-48 overflow-y-auto rounded-md border border-border bg-black/40 p-2 font-mono text-[10px] leading-snug text-muted-foreground"
              >
                {lines.length === 0 ? (
                  <span className="opacity-50">Starting…</span>
                ) : (
                  lines.map((l, i) => (
                    <div key={i}>
                      <span className="text-primary/60">[{l.phase}]</span>{' '}
                      {l.line}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>

        <p className="mt-4 text-[11px] text-muted-foreground/70">
          This only happens once. Future launches will skip straight to ALOS.
        </p>
      </div>
    </div>
  )
}

function CheckRow({
  ok,
  label,
  detail,
}: {
  ok: boolean
  label: string
  detail?: string
}) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border bg-background/40 px-3 py-2">
      {ok ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      ) : (
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
      )}
      <div className="min-w-0">
        <div className="text-xs font-medium">{label}</div>
        {detail && (
          <div className="truncate text-[10px] text-muted-foreground">
            {detail}
          </div>
        )}
      </div>
    </div>
  )
}
