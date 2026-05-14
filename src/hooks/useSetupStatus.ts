import { useCallback, useEffect, useState } from 'react'
import { api } from '@/api'
import type { SetupStatus } from '@/types/api'

export type SetupPhase = 'loading' | 'needs_setup' | 'ready' | 'error'

/**
 * Tracks the backend's /api/setup/status and derives a phase for routing.
 *
 * `needs_setup` covers missing_config, provider_invalid, and repair_needed —
 * any state where the SetupWizard should be shown.
 * `ready` means the provider is configured and validated.
 */
export function useSetupStatus(enabled: boolean) {
  const [phase, setPhase] = useState<SetupPhase>('loading')
  const [status, setStatus] = useState<SetupStatus | null>(null)

  const refresh = useCallback(async () => {
    if (!enabled) return
    try {
      const s = await api.getSetupStatus()
      setStatus(s)
      setPhase(s.ready ? 'ready' : 'needs_setup')
    } catch {
      setPhase('error')
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) return
    void Promise.resolve().then(refresh)
  }, [enabled, refresh])

  return { phase: enabled ? phase : 'loading', status, refresh }
}
