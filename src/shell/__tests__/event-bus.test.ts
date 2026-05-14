import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  subscribe,
  publish,
  clearSubscribers,
  getSubscriberCount,
} from '../event-bus'
import type { AlosEvent } from '@/contracts/events'

function makeEvent(
  overrides: Partial<AlosEvent> & { type: AlosEvent['type'] },
): AlosEvent {
  return { timestamp: Date.now(), ...overrides } as AlosEvent
}

describe('event-bus', () => {
  beforeEach(() => {
    clearSubscribers()
  })

  it('subscribe and receive event', () => {
    const received: AlosEvent[] = []
    subscribe('forge.file.saved', (e) => received.push(e))

    const event = makeEvent({ type: 'forge.file.saved', path: '/a.ts' })
    publish(event)

    expect(received).toHaveLength(1)
    expect(received[0]).toBe(event)
  })

  it('multiple subscribers all called', () => {
    const calls: number[] = []
    subscribe('forge.file.saved', () => calls.push(1))
    subscribe('forge.file.saved', () => calls.push(2))
    subscribe('forge.file.saved', () => calls.push(3))

    publish(makeEvent({ type: 'forge.file.saved', path: '/b.ts' }))

    expect(calls).toEqual([1, 2, 3])
  })

  it('different event types do not interfere', () => {
    const savedCalls: string[] = []
    const deletedCalls: string[] = []

    subscribe('forge.file.saved', (e) => savedCalls.push(e.path))
    subscribe('forge.file.deleted', (e) => deletedCalls.push(e.path))

    publish(makeEvent({ type: 'forge.file.saved', path: '/save.ts' }))
    publish(makeEvent({ type: 'forge.file.deleted', path: '/del.ts' }))

    expect(savedCalls).toEqual(['/save.ts'])
    expect(deletedCalls).toEqual(['/del.ts'])
  })

  it('unsubscribe stops delivery', () => {
    const calls: number[] = []
    const unsub = subscribe('forge.file.saved', () => calls.push(1))

    publish(makeEvent({ type: 'forge.file.saved', path: '/x.ts' }))
    expect(calls).toEqual([1])

    unsub()
    publish(makeEvent({ type: 'forge.file.saved', path: '/y.ts' }))
    expect(calls).toEqual([1]) // no second call
  })

  it('handler error does not break dispatch to peers', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const calls: number[] = []

    subscribe('forge.file.saved', () => {
      throw new Error('boom')
    })
    subscribe('forge.file.saved', () => calls.push(2))

    publish(makeEvent({ type: 'forge.file.saved', path: '/z.ts' }))

    expect(calls).toEqual([2])
    expect(consoleSpy).toHaveBeenCalledOnce()
    consoleSpy.mockRestore()
  })

  it('oversize payload throws at publish', () => {
    // Build a payload larger than 64 KB
    const bigPath = 'x'.repeat(70_000)
    const event = makeEvent({ type: 'forge.file.saved', path: bigPath })

    expect(() => publish(event)).toThrowError(/64 KB/)
  })

  it('reentrant publish is deferred', () => {
    const order: string[] = []

    subscribe('forge.file.saved', () => {
      order.push('saved-handler-start')
      // This reentrant publish should be deferred
      publish(makeEvent({ type: 'forge.file.created', path: '/new.ts' }))
      order.push('saved-handler-end')
    })

    subscribe('forge.file.created', () => {
      order.push('created-handler')
    })

    publish(makeEvent({ type: 'forge.file.saved', path: '/a.ts' }))

    // The created handler should run after the saved handler completes,
    // not interleaved during it
    expect(order).toEqual([
      'saved-handler-start',
      'saved-handler-end',
      'created-handler',
    ])
  })

  it('getSubscriberCount returns correct count', () => {
    expect(getSubscriberCount('forge.file.saved')).toBe(0)

    const unsub1 = subscribe('forge.file.saved', () => {})
    const unsub2 = subscribe('forge.file.saved', () => {})
    expect(getSubscriberCount('forge.file.saved')).toBe(2)

    unsub1()
    expect(getSubscriberCount('forge.file.saved')).toBe(1)

    unsub2()
    expect(getSubscriberCount('forge.file.saved')).toBe(0)
  })

  it('clearSubscribers removes all subscriptions', () => {
    subscribe('forge.file.saved', () => {})
    subscribe('forge.file.deleted', () => {})
    expect(getSubscriberCount('forge.file.saved')).toBe(1)
    expect(getSubscriberCount('forge.file.deleted')).toBe(1)

    clearSubscribers()

    expect(getSubscriberCount('forge.file.saved')).toBe(0)
    expect(getSubscriberCount('forge.file.deleted')).toBe(0)
  })
})
