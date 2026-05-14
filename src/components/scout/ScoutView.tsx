import { useEffect, useMemo, useState } from 'react'
import { api } from '@/api'
import type { ScoutEvent, ScoutWsFrame } from '@/types/api'
import { cn } from '@/lib/utils'

const LEVEL_CLASS: Record<string, string> = {
  error: 'border-red-500/40 bg-red-500/10 text-red-300',
  warning: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  debug: 'border-border bg-muted/40 text-muted-foreground',
}

export function ScoutView() {
  const [events, setEvents] = useState<ScoutEvent[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState('all')
  const [live, setLive] = useState(true)
  const [status, setStatus] = useState<'connecting' | 'live' | 'offline'>('connecting')

  useEffect(() => {
    let cancelled = false
    api.listScoutEvents({ limit: 500 }).then(({ events }) => {
      if (!cancelled) setEvents(events)
    }).catch(() => {
      if (!cancelled) setStatus('offline')
    })

    const socket = api.openScoutSocket()
    socket.onopen = () => setStatus('live')
    socket.onclose = () => setStatus('offline')
    socket.onerror = () => setStatus('offline')
    socket.onmessage = (message) => {
      let frame: ScoutWsFrame
      try {
        frame = JSON.parse(message.data) as ScoutWsFrame
      } catch {
        return
      }
      if (frame.type === 'scout_snapshot') {
        const snapshot = Array.isArray(frame.events) ? frame.events as ScoutEvent[] : []
        setEvents(snapshot)
      }
      if (frame.type === 'scout_event' && live) {
        const event = frame.event as ScoutEvent | undefined
        if (event) setEvents((items) => [event, ...items].slice(0, 1_000))
      }
    }
    return () => {
      cancelled = true
      socket.close()
    }
  }, [live])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return events.filter((event) => {
      if (level !== 'all' && event.level !== level) return false
      if (!q) return true
      return [
        event.source,
        event.level,
        event.event_type,
        event.message,
        event.module ?? '',
        event.run_id ?? '',
        event.session_id ?? '',
      ].some((value) => value.toLowerCase().includes(q))
    })
  }, [events, level, query])

  const selected = filtered.find((event) => event.id === selectedId) ?? filtered[0] ?? null
  const counts = useMemo(() => {
    return events.reduce<Record<string, number>>((acc, event) => {
      acc[event.level] = (acc[event.level] ?? 0) + 1
      return acc
    }, {})
  }, [events])

  return (
    <div className="grid h-full min-h-0 bg-background text-foreground" style={{ gridTemplateRows: 'auto 1fr' }}>
      <header className="border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold">Scout</h1>
            <p className="mt-1 text-sm text-muted-foreground">Live diagnostics across ALOS.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={cn(
              'rounded-md border px-2 py-1',
              status === 'live' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-border bg-muted text-muted-foreground',
            )}>
              {status}
            </span>
            <button
              type="button"
              className="rounded-md border border-border px-2 py-1 hover:bg-muted"
              onClick={() => setLive((value) => !value)}
            >
              {live ? 'Pause' : 'Resume'}
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            className="h-9 w-[min(420px,100%)] rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-primary"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search source, message, run, session..."
          />
          <select
            className="h-9 rounded-md border border-border bg-background px-2 text-sm"
            value={level}
            onChange={(event) => setLevel(event.target.value)}
          >
            <option value="all">All levels</option>
            <option value="error">Errors</option>
            <option value="warning">Warnings</option>
            <option value="info">Info</option>
            <option value="debug">Debug</option>
          </select>
          <span className="text-xs text-muted-foreground">
            {filtered.length} visible · {counts.error ?? 0} errors · {(counts.warning ?? 0) + (counts.warn ?? 0)} warnings
          </span>
        </div>
      </header>
      <div className="grid min-h-0 grid-cols-[minmax(320px,0.9fr)_minmax(360px,1.1fr)] max-md:grid-cols-1">
        <div className="min-h-0 overflow-auto border-r border-border max-md:max-h-[40vh] max-md:border-b max-md:border-r-0">
          {filtered.map((event) => (
            <button
              key={event.id}
              type="button"
              onClick={() => setSelectedId(event.id)}
              className={cn(
                'block w-full border-b border-border px-4 py-3 text-left hover:bg-muted/50',
                selected?.id === event.id && 'bg-muted',
              )}
            >
              <div className="flex items-center gap-2">
                <span className={cn('rounded-md border px-1.5 py-0.5 text-[10px] uppercase', LEVEL_CLASS[event.level] ?? LEVEL_CLASS.info)}>
                  {event.level}
                </span>
                <span className="truncate text-xs text-muted-foreground">{event.source}</span>
              </div>
              <div className="mt-1 truncate text-sm font-medium">{event.event_type}</div>
              <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{event.message || 'No message'}</div>
            </button>
          ))}
        </div>
        <div className="min-h-0 overflow-auto p-5">
          {selected ? (
            <div className="space-y-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn('rounded-md border px-2 py-1 text-xs uppercase', LEVEL_CLASS[selected.level] ?? LEVEL_CLASS.info)}>
                    {selected.level}
                  </span>
                  <span className="text-sm text-muted-foreground">{selected.created_at ?? 'live'}</span>
                </div>
                <h2 className="mt-3 break-words text-xl font-semibold">{selected.event_type}</h2>
                <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-muted-foreground">{selected.message || 'No message'}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs max-sm:grid-cols-1">
                <Meta label="Source" value={selected.source} />
                <Meta label="Module" value={selected.module ?? '-'} />
                <Meta label="Run" value={selected.run_id ?? '-'} />
                <Meta label="Session" value={selected.session_id ?? '-'} />
              </div>
              <pre className="max-h-[52vh] overflow-auto rounded-md border border-border bg-black/30 p-3 text-xs leading-relaxed">
                {JSON.stringify(selected.payload ?? {}, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              No Scout events match the current filters.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card/40 p-2">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-foreground">{value}</div>
    </div>
  )
}
