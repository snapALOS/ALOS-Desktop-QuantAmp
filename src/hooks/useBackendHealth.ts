import { useEffect, useState } from 'react'
import { api, ApiError } from '@/api'

export type BackendStatus = 'connecting' | 'online' | 'offline'

/**
 * Polls GET /health until the backend responds, then continues polling
 * at a lower cadence to surface offline state.
 *
 * Returns the current status plus a one-shot `retry()` for manual probes.
 */
export function useBackendHealth(intervalMs = 5000) {
  const [status, setStatus] = useState<BackendStatus>('connecting')
  const [lastCheck, setLastCheck] = useState<number>(0)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const probe = async () => {
      try {
        await api.health()
        if (!cancelled) {
          setStatus('online')
          setLastCheck(Date.now())
        }
      } catch (err) {
        if (!cancelled) {
          // Any network error or non-2xx → backend not ready yet
          const offline = err instanceof ApiError && err.status !== 0
          setStatus(offline ? 'offline' : 'connecting')
          setLastCheck(Date.now())
        }
      } finally {
        if (!cancelled) {
          const delay = status === 'online' ? intervalMs : 1000
          timer = setTimeout(probe, delay)
        }
      }
    }

    probe()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs])

  return { status, lastCheck }
}
