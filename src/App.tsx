import { useEffect } from 'react'
import { api, ApiError } from '@/api'
import { useAuth } from '@/store/auth'
import { useBackendHealth } from '@/hooks/useBackendHealth'
import { useSetupStatus } from '@/hooks/useSetupStatus'
import { useTauriBackendStatus } from '@/hooks/useTauriBackendStatus'
import { usePreflight } from '@/hooks/usePreflight'
import { Splash } from '@/components/layout/Splash'
import { LoginGate } from '@/components/layout/LoginGate'
import { SetupWizard } from '@/components/setup/SetupWizard'
import { PreflightGate } from '@/components/preflight/PreflightGate'
import { RootShell } from '@/shell/RootShell'

/**
 * Top-level state machine:
 *
 *   0. Preflight blocked    → PreflightGate (install Python deps)
 *   1. Backend down         → Splash("Starting ALOS…")
 *   2. Backend up, not configured → SetupWizard
 *   3. Configured, no key   → LoginGate
 *   4. Configured, key, user unknown → Splash("Authenticating…")
 *   5. Fully authenticated → RootShell (owns registry + activeId + event bridge)
 *
 * App.tsx deliberately stops at auth. RootShell handles everything below it.
 */
export default function App() {
  const { phase: preflight, report: preflightReport, refresh: refreshPreflight } = usePreflight()
  const { status: backend } = useBackendHealth()
  const tauri = useTauriBackendStatus(
    2000,
    backend !== 'online' && preflight !== 'blocked' && preflight !== 'loading',
  )
  const { phase: setupPhase, refresh: refreshSetup } = useSetupStatus(
    backend === 'online',
  )
  const apiKey = useAuth((s) => s.apiKey)
  const user = useAuth((s) => s.user)
  const setUser = useAuth((s) => s.setUser)
  const setApiKey = useAuth((s) => s.setApiKey)

  // Hydrate the user whenever the API key exists but user isn't loaded yet.
  useEffect(() => {
    if (backend !== 'online' || setupPhase !== 'ready' || !apiKey || user) return

    let cancelled = false
    ;(async () => {
      try {
        const me = await api.me()
        if (!cancelled) setUser(me)
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          setApiKey(null)
          setUser(null)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [backend, setupPhase, apiKey, user, setUser, setApiKey])

  // 0. Preflight must clear before we probe the backend at all.
  if (preflight === 'loading') {
    return <Splash message="Checking environment…" />
  }
  if (preflight === 'blocked' && preflightReport) {
    return (
      <PreflightGate
        report={preflightReport}
        onResolved={() => refreshPreflight()}
      />
    )
  }

  // 1. Backend reachability.
  if (backend !== 'online') {
    const spawnErr = tauri?.last_error
    const connecting = backend === 'connecting' && !spawnErr
    return (
      <Splash
        message={
          spawnErr
            ? 'Backend failed to start'
            : connecting
              ? 'Starting ALOS…'
              : 'Backend offline'
        }
        subtext={
          spawnErr
            ? spawnErr
            : connecting
              ? 'Waiting for the backend to respond.'
              : 'Cannot reach localhost:8000 — is the ALOS backend running?'
        }
      />
    )
  }

  if (setupPhase === 'loading') {
    return <Splash message="Checking configuration…" />
  }

  if (setupPhase === 'needs_setup') {
    return <SetupWizard onComplete={refreshSetup} />
  }

  if (setupPhase === 'error') {
    return (
      <Splash
        message="Configuration error"
        subtext="ALOS could not read its setup status. Check the backend logs."
      />
    )
  }

  // setupPhase === 'ready'
  if (!apiKey || !user) {
    if (apiKey && !user) return <Splash message="Authenticating…" />
    return <LoginGate />
  }

  // Fully authenticated — hand off to the shell.
  return <RootShell backendStatus={backend} />
}
