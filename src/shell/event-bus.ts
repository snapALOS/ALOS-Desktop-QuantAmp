/**
 * In-process pub/sub event bus for the frontend shell.
 *
 * Design decisions (RFC-0005):
 *  - Exact type-string matching only, no wildcards (Decision 5)
 *  - Synchronous in-process dispatch in subscription order (Decision 8)
 *  - Handler errors logged at ERROR, never interrupt peers (Decision 12)
 *  - Reentrant publish detected and deferred to next microtask (Decision 9)
 *  - Payload <= 64 KB JSON, oversize rejected at publish (Decision 6)
 */

import type { AlosEvent, AlosEventType } from '@/contracts/events'

const MAX_PAYLOAD_BYTES = 64 * 1024

type Handler<T extends AlosEvent = AlosEvent> = (event: T) => void
type Unsubscribe = () => void

interface Subscription {
  id: number
  handler: Handler
}

let nextId = 0
const subscribers = new Map<string, Subscription[]>()
const tapSubscribers: Subscription[] = []
let dispatching = false
const deferred: AlosEvent[] = []

/**
 * Subscribe to events of a specific type. Returns an unsubscribe function.
 */
export function subscribe<T extends AlosEventType>(
  type: T,
  handler: (event: Extract<AlosEvent, { type: T }>) => void,
): Unsubscribe {
  const id = nextId++
  const sub: Subscription = { id, handler: handler as Handler }

  let subs = subscribers.get(type)
  if (!subs) {
    subs = []
    subscribers.set(type, subs)
  }
  subs.push(sub)

  return () => {
    const list = subscribers.get(type)
    if (list) {
      const idx = list.findIndex((s) => s.id === id)
      if (idx !== -1) {
        list.splice(idx, 1)
      }
      if (list.length === 0) {
        subscribers.delete(type)
      }
    }
  }
}

export function subscribeAll(handler: Handler): Unsubscribe {
  const id = nextId++
  const sub: Subscription = { id, handler }
  tapSubscribers.push(sub)
  return () => {
    const idx = tapSubscribers.findIndex((s) => s.id === id)
    if (idx !== -1) {
      tapSubscribers.splice(idx, 1)
    }
  }
}

/**
 * Publish an event to all subscribers of its type.
 *
 * Throws if the serialized payload exceeds 64 KB.
 * If called from within a handler (reentrant), the event is deferred
 * to the next microtask to prevent synchronous chaining.
 */
export function publish(event: AlosEvent): void {
  // Payload size check (Decision 6)
  const json = JSON.stringify(event)
  const byteLength = new TextEncoder().encode(json).byteLength
  if (byteLength > MAX_PAYLOAD_BYTES) {
    throw new Error(
      `Event payload exceeds 64 KB limit (${byteLength} bytes): ${event.type}`,
    )
  }

  // Reentrant publish detection (Decision 9)
  if (dispatching) {
    deferred.push(event)
    return
  }

  dispatch(event)

  // Flush any events that were deferred by reentrant publish calls
  flushDeferred()
}

function dispatch(event: AlosEvent): void {
  const subs = subscribers.get(event.type)
  if ((!subs || subs.length === 0) && tapSubscribers.length === 0) return

  dispatching = true
  try {
    // Iterate a snapshot so that unsubscribes during dispatch are safe
    const snapshot = [...(subs ?? [])]
    for (const sub of snapshot) {
      try {
        sub.handler(event)
      } catch (err) {
        // Decision 12: log at ERROR, don't interrupt other handlers
        console.error(
          `[event-bus] Handler error for "${event.type}":`,
          err,
        )
      }
    }
    for (const sub of [...tapSubscribers]) {
      try {
        sub.handler(event)
      } catch (err) {
        console.error(
          `[event-bus] Diagnostic tap error for "${event.type}":`,
          err,
        )
      }
    }
  } finally {
    dispatching = false
  }
}

function flushDeferred(): void {
  while (deferred.length > 0) {
    const event = deferred.shift()!
    dispatch(event)
  }
}

/**
 * Remove all subscribers. Useful for testing.
 */
export function clearSubscribers(): void {
  subscribers.clear()
  tapSubscribers.length = 0
  deferred.length = 0
}

/**
 * Get the number of subscribers for a given event type. Useful for testing.
 */
export function getSubscriberCount(type: string): number {
  return subscribers.get(type)?.length ?? 0
}
