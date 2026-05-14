import { api } from '@/api'
import { subscribeAll } from '@/shell/event-bus'

let installed = false
let muted = false

function stringifyArg(value: unknown): string {
  if (value instanceof Error) return `${value.name}: ${value.message}\n${value.stack ?? ''}`.trim()
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function sendScoutEvent(
  level: 'info' | 'warning' | 'error',
  eventType: string,
  message: string,
  payload: Record<string, unknown> = {},
) {
  if (muted) return
  muted = true
  api.recordScoutEvent({
    source: 'frontend.renderer',
    level,
    event_type: eventType,
    message,
    module: window.location.hash || window.location.pathname || 'shell',
    payload,
  }).catch(() => {}).finally(() => {
    muted = false
  })
}

export function installScoutCapture(): () => void {
  if (installed) return () => {}
  installed = true

  const originalError = console.error
  const originalWarn = console.warn

  console.error = (...args: unknown[]) => {
    originalError(...args)
    sendScoutEvent('error', 'console.error', args.map(stringifyArg).join(' '), { args: args.map(stringifyArg) })
  }
  console.warn = (...args: unknown[]) => {
    originalWarn(...args)
    sendScoutEvent('warning', 'console.warn', args.map(stringifyArg).join(' '), { args: args.map(stringifyArg) })
  }

  const onError = (event: ErrorEvent) => {
    sendScoutEvent('error', 'window.error', event.message, {
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      error: event.error ? stringifyArg(event.error) : null,
    })
  }
  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    sendScoutEvent('error', 'window.unhandledrejection', stringifyArg(event.reason), {
      reason: stringifyArg(event.reason),
    })
  }

  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onUnhandledRejection)
  const unsubscribeEvents = subscribeAll((event) => {
    sendScoutEvent('info', `event_bus.${event.type}`, event.type, { event })
  })

  return () => {
    console.error = originalError
    console.warn = originalWarn
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onUnhandledRejection)
    unsubscribeEvents()
    installed = false
  }
}
