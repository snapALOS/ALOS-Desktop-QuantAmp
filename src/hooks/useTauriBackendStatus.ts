import { useEffect, useState } from 'react'

export interface TauriBackendStatus {
  port: number
  running: boolean
  last_error: string | null
}

/**
 * Reads the Rust sidecar's view of the Python backend:
 *   - `running` — whether the child process is currently alive.
 *   - `last_error` — the last spawn error, if any.
 *
 * Only works inside the Tauri shell; outside (e.g. plain `npm run dev` in
 * a browser) we return `null` so callers can gracefully fall back to
 * "Backend offline" without a crash.
 */
export function useTauriBackendStatus(pollMs = 2000, enabled = true) {
  const [status, setStatus] = useState<TauriBackendStatus | null>(null)

  useEffect(() => {
    if (!enabled) return
    // Tauri injects `window.__TAURI_INTERNALS__` — use that to avoid a static import
    // of `@tauri-apps/api` which would fail in a plain-browser preview.
    const internals = (
      window as unknown as { __TAURI_INTERNALS__?: { invoke: (cmd: string) => Promise<unknown> } }
    ).__TAURI_INTERNALS__
    if (!internals?.invoke) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const probe = async () => {
      try {
        const s = (await internals.invoke('backend_status')) as TauriBackendStatus
        if (!cancelled) setStatus(s)
      } catch {
        if (!cancelled) setStatus(null)
      } finally {
        if (!cancelled) timer = setTimeout(probe, pollMs)
      }
    }

    probe()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [pollMs, enabled])

  return status
}
