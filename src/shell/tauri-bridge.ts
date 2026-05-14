/**
 * Tauri event bridge — single entry point for piping Rust/Python-originated
 * events into the frontend event-bus.
 *
 * Design decisions:
 *  - Idempotent: `startTauriEventBridge()` may be called any number of times;
 *    only the first call attaches a `listen('alos-event', ...)` subscription.
 *    This prevents duplicate delivery if RootShell re-mounts.
 *  - Defensive: payloads are validated via `isAlosEvent()` before being
 *    republished locally. Malformed frames are logged at ERROR and dropped.
 *  - Gracefully degrades: in a non-Tauri context (browser preview) this is a
 *    no-op that returns a noop disposer.
 *  - Outbound: `forwardToBackend(event)` sends a frontend-originated event
 *    to the Rust/Python side over the `forward_event_to_backend` IPC command.
 */

import { invoke, listen, isTauri } from '@/api/tauri'
import { publish } from '@/shell/event-bus'
import type { AlosEvent } from '@/contracts/events'

// ---------------------------------------------------------------------------
// Event shape guard
// ---------------------------------------------------------------------------

/**
 * Best-effort shape guard for payloads received over the `alos-event`
 * channel. We accept anything whose `type` is a string and `timestamp` is a
 * number; downstream subscribers apply their own discriminated-union narrowing.
 */
export function isAlosEvent(payload: unknown): payload is AlosEvent {
  if (typeof payload !== 'object' || payload === null) return false
  const obj = payload as Record<string, unknown>
  return typeof obj.type === 'string' && typeof obj.timestamp === 'number'
}

// ---------------------------------------------------------------------------
// Idempotent inbound subscription
// ---------------------------------------------------------------------------

let started = false
let unlisten: (() => void) | null = null
let startPromise: Promise<void> | null = null

/**
 * Attach the `alos-event` listener exactly once per process. Subsequent calls
 * are no-ops and return the same in-flight promise. Returns a disposer that
 * detaches the listener and allows a future start (useful in tests).
 */
export async function startTauriEventBridge(): Promise<() => void> {
  if (!isTauri()) {
    return () => {}
  }

  if (started) {
    await startPromise
    return stopTauriEventBridge
  }

  started = true
  startPromise = (async () => {
    unlisten = await listen<string>('alos-event', (payload) => {
      let parsed: unknown
      try {
        parsed = typeof payload === 'string' ? JSON.parse(payload) : payload
      } catch (err) {
        console.error('[tauri-bridge] Malformed event payload (JSON parse failed):', err)
        return
      }

      if (!isAlosEvent(parsed)) {
        console.error('[tauri-bridge] Rejected non-AlosEvent payload:', parsed)
        return
      }

      try {
        publish(parsed)
      } catch (err) {
        console.error(`[tauri-bridge] publish("${parsed.type}") failed:`, err)
      }
    })
  })()

  await startPromise
  return stopTauriEventBridge
}

function stopTauriEventBridge(): void {
  if (unlisten) {
    try {
      unlisten()
    } catch (err) {
      console.error('[tauri-bridge] unlisten failed:', err)
    }
  }
  unlisten = null
  started = false
  startPromise = null
}

// ---------------------------------------------------------------------------
// Outbound: frontend → backend
// ---------------------------------------------------------------------------

/**
 * Forward a frontend-originated event to the Python backend event bus (via
 * the Rust shell). Silently no-ops outside Tauri.
 */
export async function forwardToBackend(event: AlosEvent): Promise<void> {
  if (!isTauri()) return
  try {
    const json = JSON.stringify(event)
    await invoke<void>('forward_event_to_backend', { eventJson: json })
  } catch (err) {
    console.error(`[tauri-bridge] forwardToBackend("${event.type}") failed:`, err)
  }
}
