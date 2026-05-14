/**
 * Thin wrapper around Tauri's IPC primitives so the rest of the app can
 * stay ignorant of how we invoke commands / subscribe to events, and so
 * a plain-browser preview (outside the Tauri shell) degrades gracefully
 * instead of throwing a module-resolution error.
 */

interface TauriInternals {
  invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
}

function internals(): TauriInternals | null {
  const w = window as unknown as { __TAURI_INTERNALS__?: TauriInternals }
  return w.__TAURI_INTERNALS__ ?? null
}

export function isTauri(): boolean {
  return internals() !== null
}

export async function invoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  const i = internals()
  if (!i) throw new Error(`Tauri IPC unavailable (invoke ${cmd})`)
  return (await i.invoke(cmd, args)) as T
}

/**
 * Subscribe to a Tauri event. Returns an unsubscribe function. In non-Tauri
 * contexts this is a no-op that returns a noop disposer.
 */
export async function listen<T>(
  event: string,
  handler: (payload: T) => void,
): Promise<() => void> {
  if (!isTauri()) return () => {}
  // Dynamic import so the @tauri-apps/api package isn't required when
  // running the frontend standalone.
  const mod = await import('@tauri-apps/api/event')
  const unlisten = await mod.listen<T>(event, (e) => handler(e.payload))
  return unlisten
}
