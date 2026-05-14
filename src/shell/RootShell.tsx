/**
 * RootShell — top-level shell layout.
 *
 * Owns three responsibilities (RFC-0001):
 *   1. Load the module registry from Rust on mount.
 *   2. Validate the persisted activeId against the live registry and
 *      fall back to 'chat' if the module is hidden, unavailable, or gone.
 *   3. Start the Tauri event bridge exactly once.
 *
 * App.tsx handles preflight/backend/setup/auth and mounts RootShell once
 * the user is fully authenticated. RootShell does NOT deal with auth state.
 */

import { useEffect, useState } from 'react'
import { ActivityBar } from '@/shell/ActivityBar'
import { ModuleShell } from '@/shell/ModuleShell'
import { loadRegistry, type ModuleEntry } from '@/shell/module-registry'
import { useActiveModule } from '@/store/active-module'
import { startTauriEventBridge } from '@/shell/tauri-bridge'
import { installScoutCapture } from '@/scout/capture'
import { Splash } from '@/components/layout/Splash'
import type { BackendStatus } from '@/hooks/useBackendHealth'

interface RootShellProps {
  backendStatus: BackendStatus
}

export function RootShell({ backendStatus }: RootShellProps) {
  const [registry, setRegistry] = useState<ModuleEntry[] | null>(null)
  const activeId = useActiveModule((s) => s.activeId)
  const setActive = useActiveModule((s) => s.setActive)

  // 1. Load registry once on mount.
  useEffect(() => {
    let cancelled = false
    loadRegistry()
      .then((entries) => {
        if (!cancelled) setRegistry(entries)
      })
      .catch((err) => {
        console.error('[RootShell] loadRegistry failed:', err)
        if (!cancelled) setRegistry([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 2. Validate persisted activeId against live registry.
  useEffect(() => {
    if (!registry || registry.length === 0) return
    const entry = registry.find((m) => m.id === activeId)
    if (!entry || !entry.available || entry.hidden) {
      const first = registry.find((m) => !m.hidden && m.available)
      setActive(first ? first.id : 'chat')
    }
  }, [registry, activeId, setActive])

  // 3. Start the Tauri event bridge (idempotent).
  useEffect(() => {
    let disposer: (() => void) | null = null
    let cancelled = false
    startTauriEventBridge()
      .then((stop) => {
        if (cancelled) stop()
        else disposer = stop
      })
      .catch((err) => {
        console.error('[RootShell] startTauriEventBridge failed:', err)
      })
    return () => {
      cancelled = true
      if (disposer) disposer()
    }
  }, [])

  useEffect(() => {
    const dispose = installScoutCapture()
    return () => dispose()
  }, [])

  if (!registry) {
    return <Splash message="Loading modules…" />
  }

  return (
    <div className="flex h-screen w-screen bg-background text-foreground overflow-hidden">
      <ActivityBar registry={registry} />
      <div className="flex-1 min-w-0">
        <ModuleShell backendStatus={backendStatus} registry={registry} />
      </div>
    </div>
  )
}
