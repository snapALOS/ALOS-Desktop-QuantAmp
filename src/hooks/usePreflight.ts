import { useCallback, useEffect, useState } from 'react'
import { invoke, isTauri } from '@/api/tauri'
import type { PreflightReport } from '@/types/api'

export type PreflightPhase = 'unavailable' | 'loading' | 'blocked' | 'ready'

/**
 * Queries the Rust-side preflight once at mount. When not running inside
 * Tauri (e.g. plain `bun run dev` in a browser), preflight is considered
 * `unavailable` and the caller should assume the user is managing Python
 * themselves — we skip the gate and trust `useBackendHealth` to surface
 * any resulting errors.
 */
export function usePreflight() {
  const [phase, setPhase] = useState<PreflightPhase>(
    isTauri() ? 'loading' : 'unavailable',
  )
  const [report, setReport] = useState<PreflightReport | null>(null)

  const refresh = useCallback(async () => {
    if (!isTauri()) {
      setPhase('unavailable')
      return
    }
    try {
      const r = await invoke<PreflightReport>('preflight_check')
      setReport(r)
      setPhase(r.ok ? 'ready' : 'blocked')
    } catch {
      setPhase('unavailable')
    }
  }, [])

  useEffect(() => {
    void Promise.resolve().then(refresh)
  }, [refresh])

  return { phase, report, refresh }
}
