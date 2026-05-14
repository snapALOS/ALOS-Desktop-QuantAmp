import { useState, useEffect } from 'react'
import { loadRegistry, type ModuleEntry } from '@/shell/module-registry'

export function useModuleRegistry(authenticated: boolean) {
  const [registry, setRegistry] = useState<ModuleEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!authenticated) return

    let cancelled = false

    void Promise.resolve().then(async () => {
      if (cancelled) return
      setLoading(true)
      setError(null)
      try {
        const entries = await loadRegistry()
        if (cancelled) return
        setRegistry(entries)
      } catch (err) {
        if (!cancelled) {
          console.error('[useModuleRegistry] Failed to load:', err)
          setError(err instanceof Error ? err : new Error(String(err)))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [authenticated])

  return { registry: authenticated ? registry : [], loading: authenticated && loading, error }
}
