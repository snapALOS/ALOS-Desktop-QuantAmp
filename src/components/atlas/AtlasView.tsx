/**
 * AtlasView — visual dependency intelligence UI for the Atlas module.
 *
 * Acceptance criteria for 0152 satisfied here:
 *   - Index/register the current repo (button → /api/atlas/index)
 *   - Render an interactive visual file/dependency map (SVG force layout)
 *   - Inspect direct + transitive dependency consequences (impact panel)
 *   - Search by concept, jump from results to nodes/files
 *   - Same surface backs the agent tools (see backend/src/tools/atlas_tools.py)
 *
 * Deliberately self-contained: no graph library — a small SVG force
 * simulation keeps the bundle slim and avoids dependency churn for v0.2.
 * Good enough for an inspectable map of up to a few hundred nodes; if we
 * need more, drop in react-force-graph later without changing the API
 * surface.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from 'react'
import { api, ApiError } from '@/api'
import { registerModuleAgentContextProvider } from '@/shell/agent-context'
import type {
  AtlasGraphEdge,
  AtlasGraphNode,
  AtlasGraphResponse,
  AtlasImpactResponse,
  AtlasRepoEntry,
  AtlasSearchHit,
  AtlasStatus,
} from '@/types/atlas'

// ── Storage key — survives reloads, scoped to this user's app data ─
const ACTIVE_REPO_KEY = 'alos.atlas.active-repo'

// ── Force-simulation tunables ──────────────────────────────────────
const SIM_ITERATIONS = 220
const SIM_REPULSION = 6500
const SIM_LINK_LEN = 90
const SIM_CENTER_PULL = 0.012
const SIM_DAMPING = 0.86
const VIEW_WIDTH = 980
const VIEW_HEIGHT = 620

interface PositionedNode extends AtlasGraphNode {
  x: number
  y: number
  vx: number
  vy: number
}

// ── Small helpers ──────────────────────────────────────────────────
function classNames(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

function nodeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'file':
      return '#3b82f6'
    case 'route':
      return '#8b5cf6'
    case 'endpoint':
      return '#a855f7'
    case 'function':
    case 'method':
      return '#10b981'
    case 'class':
      return '#f59e0b'
    case 'module':
      return '#06b6d4'
    default:
      return '#94a3b8'
  }
}

function edgeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'imports':
    case 'imports_from':
      return '#475569'
    case 'calls':
      return '#0ea5e9'
    case 'defines':
      return '#22c55e'
    case 'uses':
      return '#a78bfa'
    default:
      return '#64748b'
  }
}

function riskTone(risk: string | undefined): string {
  switch ((risk ?? '').toLowerCase()) {
    case 'critical':
      return 'bg-red-500/15 text-red-300 ring-red-500/40'
    case 'high':
      return 'bg-amber-500/15 text-amber-300 ring-amber-500/40'
    case 'medium':
      return 'bg-yellow-500/15 text-yellow-300 ring-yellow-500/40'
    case 'low':
      return 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40'
    default:
      return 'bg-slate-500/15 text-slate-300 ring-slate-500/40'
  }
}

// ── Force-directed layout (compact, deterministic seed) ────────────
function layoutGraph(
  nodes: AtlasGraphNode[],
  edges: AtlasGraphEdge[],
): PositionedNode[] {
  if (nodes.length === 0) return []

  // Seed positions on a jittered ring so the simulation has somewhere to start.
  const n = nodes.length
  const radius = Math.min(VIEW_WIDTH, VIEW_HEIGHT) / 2.4
  const cx = VIEW_WIDTH / 2
  const cy = VIEW_HEIGHT / 2
  const positioned: PositionedNode[] = nodes.map((node, i) => {
    const angle = (i / n) * Math.PI * 2
    // Deterministic-ish jitter from id hash so reloads look stable.
    const seed = simpleHash(node.id) % 1000
    const jitter = (seed / 1000 - 0.5) * 40
    return {
      ...node,
      x: cx + Math.cos(angle) * (radius + jitter),
      y: cy + Math.sin(angle) * (radius + jitter),
      vx: 0,
      vy: 0,
    }
  })

  const idToIdx = new Map<string, number>()
  positioned.forEach((p, i) => idToIdx.set(p.id, i))
  const links = edges
    .map((e) => ({
      a: idToIdx.get(e.source_id),
      b: idToIdx.get(e.target_id),
    }))
    .filter((l): l is { a: number; b: number } => l.a !== undefined && l.b !== undefined)

  for (let iter = 0; iter < SIM_ITERATIONS; iter++) {
    // Repulsion — naive O(n²); fine for n ≤ 200.
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const a = positioned[i]
        const b = positioned[j]
        const dx = a.x - b.x
        const dy = a.y - b.y
        const distSq = dx * dx + dy * dy + 0.01
        const force = SIM_REPULSION / distSq
        const dist = Math.sqrt(distSq)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx
        a.vy += fy
        b.vx -= fx
        b.vy -= fy
      }
    }
    // Spring links.
    for (const { a, b } of links) {
      const na = positioned[a]
      const nb = positioned[b]
      const dx = nb.x - na.x
      const dy = nb.y - na.y
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.01
      const k = (dist - SIM_LINK_LEN) * 0.06
      const fx = (dx / dist) * k
      const fy = (dy / dist) * k
      na.vx += fx
      na.vy += fy
      nb.vx -= fx
      nb.vy -= fy
    }
    // Center pull + damping + integrate.
    for (const p of positioned) {
      p.vx += (cx - p.x) * SIM_CENTER_PULL
      p.vy += (cy - p.y) * SIM_CENTER_PULL
      p.vx *= SIM_DAMPING
      p.vy *= SIM_DAMPING
      p.x += p.vx
      p.y += p.vy
    }
  }
  return positioned
}

function simpleHash(s: string): number {
  let h = 5381
  for (let i = 0; i < s.length; i++) {
    h = (h * 33) ^ s.charCodeAt(i)
  }
  return Math.abs(h | 0)
}

// ── Sub-components ─────────────────────────────────────────────────

function StatusPill({ status }: { status: AtlasStatus | null }) {
  if (!status) return null
  const indexed = status.indexed ?? Boolean(status.last_indexed)
  const tone = indexed
    ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40'
    : 'bg-amber-500/15 text-amber-300 ring-amber-500/40'
  const label = indexed
    ? `${status.node_count ?? '?'} nodes · ${status.edge_count ?? '?'} edges`
    : 'Not indexed yet'
  return (
    <span
      className={classNames(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        tone,
      )}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  )
}

interface GraphCanvasProps {
  positioned: PositionedNode[]
  edges: AtlasGraphEdge[]
  selectedId: string | null
  highlightedIds: Set<string>
  onSelect: (id: string) => void
}

function GraphCanvas({
  positioned,
  edges,
  selectedId,
  highlightedIds,
  onSelect,
}: GraphCanvasProps) {
  const idToNode = useMemo(() => {
    const m = new Map<string, PositionedNode>()
    positioned.forEach((p) => m.set(p.id, p))
    return m
  }, [positioned])

  if (positioned.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
        <div className="text-4xl opacity-30">🗺️</div>
        <div>No graph data yet — index a repository to build the map.</div>
      </div>
    )
  }

  return (
    <svg
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      className="h-full w-full select-none"
      role="img"
      aria-label="Atlas dependency graph"
    >
      <defs>
        <marker
          id="atlas-arrow"
          viewBox="0 -5 10 10"
          refX="14"
          refY="0"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M0,-5L10,0L0,5" fill="#94a3b8" />
        </marker>
      </defs>
      <g>
        {edges.map((e) => {
          const a = idToNode.get(e.source_id)
          const b = idToNode.get(e.target_id)
          if (!a || !b) return null
          const dim = highlightedIds.size > 0
            && !highlightedIds.has(e.source_id)
            && !highlightedIds.has(e.target_id)
          return (
            <line
              key={e.id}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={edgeColor(e.type)}
              strokeWidth={1.2}
              strokeOpacity={dim ? 0.12 : 0.55}
              markerEnd="url(#atlas-arrow)"
            />
          )
        })}
      </g>
      <g>
        {positioned.map((node) => {
          const selected = node.id === selectedId
          const dim = highlightedIds.size > 0 && !highlightedIds.has(node.id)
          const r = selected ? 9 : 6
          return (
            <g
              key={node.id}
              transform={`translate(${node.x},${node.y})`}
              onClick={() => onSelect(node.id)}
              style={{ cursor: 'pointer' }}
              opacity={dim ? 0.25 : 1}
            >
              <circle
                r={r + (selected ? 5 : 0)}
                fill={selected ? nodeColor(node.type) : 'transparent'}
                fillOpacity={0.18}
                stroke={selected ? nodeColor(node.type) : 'transparent'}
                strokeWidth={selected ? 1.5 : 0}
              />
              <circle
                r={r}
                fill={nodeColor(node.type)}
                stroke="#0f172a"
                strokeWidth={1}
              />
              {(selected || positioned.length < 60) && (
                <text
                  x={r + 4}
                  y={3}
                  fontSize={10}
                  fill="#cbd5e1"
                  pointerEvents="none"
                >
                  {node.name.length > 28 ? `${node.name.slice(0, 27)}…` : node.name}
                </text>
              )}
            </g>
          )
        })}
      </g>
    </svg>
  )
}

interface SearchPanelProps {
  repo: string | null
  onSelectHit: (hit: AtlasSearchHit) => void
}

function SearchPanel({ repo, onSelectHit }: SearchPanelProps) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<AtlasSearchHit[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      if (!repo || !q.trim()) return
      setLoading(true)
      setErr(null)
      try {
        const res = await api.atlasSearch(repo, q.trim(), 25)
        setHits(res.results ?? [])
      } catch (caught) {
        setErr(caught instanceof Error ? caught.message : 'Search failed')
        setHits([])
      } finally {
        setLoading(false)
      }
    },
    [repo, q],
  )

  return (
    <div className="flex flex-col gap-2">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={repo ? 'Search by concept, name, or path…' : 'Index a repo first'}
          disabled={!repo}
          className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!repo || !q.trim() || loading}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? '…' : 'Find'}
        </button>
      </form>
      {err && <div className="rounded-md bg-red-500/10 px-2 py-1 text-xs text-red-300">{err}</div>}
      <div className="max-h-56 overflow-y-auto rounded-md border border-border bg-background/40">
        {hits.length === 0 && !loading && (
          <div className="px-2 py-2 text-xs text-muted-foreground">
            {q ? 'No matches.' : 'Search results will appear here.'}
          </div>
        )}
        {hits.map((h) => (
          <button
            key={h.id}
            type="button"
            onClick={() => onSelectHit(h)}
            className="flex w-full flex-col items-start gap-0.5 border-b border-border px-2 py-1.5 text-left text-xs hover:bg-muted/40"
          >
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: nodeColor(h.type) }}
              />
              <span className="font-medium text-foreground">{h.name}</span>
              <span className="text-muted-foreground">·</span>
              <span className="text-muted-foreground">{h.type}</span>
            </span>
            {h.path && <span className="font-mono text-[10px] text-muted-foreground">{h.path}</span>}
          </button>
        ))}
      </div>
    </div>
  )
}

interface ImpactPanelProps {
  impact: AtlasImpactResponse | null
  loading: boolean
  onJump: (id: string) => void
}

function ImpactPanel({ impact, loading, onJump }: ImpactPanelProps) {
  if (loading) {
    return <div className="text-xs text-muted-foreground">Computing impact…</div>
  }
  if (!impact) {
    return (
      <div className="text-xs text-muted-foreground">
        Select a node and run impact to see direct + transitive consequences.
      </div>
    )
  }
  const impacted = impact.impacted ?? []
  const tests = impact.tests ?? []
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className={classNames(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
            riskTone(impact.risk),
          )}
        >
          risk: {impact.risk ?? 'unknown'}
        </span>
        <span className="text-xs text-muted-foreground">
          {impacted.length} impacted · {tests.length} tests
        </span>
      </div>
      {impact.verification_steps && impact.verification_steps.length > 0 && (
        <ul className="list-disc rounded-md bg-muted/30 px-4 py-2 text-xs text-foreground">
          {impact.verification_steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
      <div className="max-h-72 overflow-y-auto rounded-md border border-border">
        {impacted.map((row) => (
          <button
            key={row.id}
            type="button"
            onClick={() => onJump(row.id)}
            className="flex w-full flex-col gap-0.5 border-b border-border px-2 py-1.5 text-left text-xs hover:bg-muted/40"
          >
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: nodeColor(row.type) }}
              />
              <span className="font-medium text-foreground">{row.name}</span>
              <span className="text-muted-foreground">·</span>
              <span className="text-muted-foreground">{row.type}</span>
              {typeof row.depth === 'number' && (
                <span className="ml-auto text-muted-foreground">d={row.depth}</span>
              )}
            </span>
            {row.path && (
              <span className="font-mono text-[10px] text-muted-foreground">{row.path}</span>
            )}
            {row.reason && (
              <span className="text-[10px] text-muted-foreground">{row.reason}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Main view ──────────────────────────────────────────────────────

export function AtlasView() {
  const [repos, setRepos] = useState<AtlasRepoEntry[]>([])
  const [activeRepo, setActiveRepo] = useState<string | null>(() => {
    try {
      return localStorage.getItem(ACTIVE_REPO_KEY)
    } catch {
      return null
    }
  })
  const [status, setStatus] = useState<AtlasStatus | null>(null)
  const [graph, setGraph] = useState<AtlasGraphResponse | null>(null)
  const [graphLimit, setGraphLimit] = useState(80)
  const [graphLoading, setGraphLoading] = useState(false)
  const [reposLoading, setReposLoading] = useState(true)
  const [bootstrapErr, setBootstrapErr] = useState<string | null>(null)
  const [indexingPath, setIndexingPath] = useState('')
  const [indexBusy, setIndexBusy] = useState(false)
  const [indexNotice, setIndexNotice] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [impact, setImpact] = useState<AtlasImpactResponse | null>(null)
  const [impactLoading, setImpactLoading] = useState(false)

  // Persist active repo across reloads.
  useEffect(() => {
    try {
      if (activeRepo) localStorage.setItem(ACTIVE_REPO_KEY, activeRepo)
      else localStorage.removeItem(ACTIVE_REPO_KEY)
    } catch {
      /* storage may be unavailable in some embedded contexts */
    }
  }, [activeRepo])

  // Bootstrap: list repos, pick an active one.
  const bootstrap = useCallback(async () => {
    setReposLoading(true)
    setBootstrapErr(null)
    try {
      const res = await api.atlasListRepos()
      const list = res.repositories ?? []
      setRepos(list)
      if (list.length > 0) {
        const stored = activeRepo
        const known = stored && list.find((r) => r.repo_id === stored || r.path === stored)
        const next = known ? known.repo_id ?? known.path : (list[0].repo_id ?? list[0].path)
        setActiveRepo(next)
      } else {
        setActiveRepo(null)
      }
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 404
          ? 'Atlas backend is not mounted. Make sure the dev sidecar is running with the modules tree.'
          : err instanceof Error
            ? err.message
            : 'Failed to reach Atlas.'
      setBootstrapErr(msg)
    } finally {
      setReposLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  // Whenever the active repo changes, refresh status + graph.
  const refreshGraph = useCallback(
    async (repo: string) => {
      setGraphLoading(true)
      try {
        const [s, g] = await Promise.all([
          api.atlasStatus(repo).catch(() => null),
          api.atlasGraph(repo, graphLimit).catch(() => null),
        ])
        setStatus(s)
        setGraph(g)
      } finally {
        setGraphLoading(false)
      }
    },
    [graphLimit],
  )

  useEffect(() => {
    if (!activeRepo) {
      setStatus(null)
      setGraph(null)
      setSelectedId(null)
      setImpact(null)
      return
    }
    void refreshGraph(activeRepo)
  }, [activeRepo, refreshGraph])

  const positioned = useMemo(
    () => layoutGraph(graph?.nodes ?? [], graph?.edges ?? []),
    [graph],
  )

  const highlightedIds = useMemo(() => {
    const set = new Set<string>()
    if (!impact) return set
    impact.impacted?.forEach((n) => set.add(n.id))
    if (selectedId) set.add(selectedId)
    return set
  }, [impact, selectedId])

  const selectedNode = useMemo(
    () => positioned.find((p) => p.id === selectedId) ?? null,
    [positioned, selectedId],
  )

  useEffect(() => {
    return registerModuleAgentContextProvider('atlas', () => ({
      module_id: 'atlas',
      module_name: 'Atlas',
      captured_at: new Date().toISOString(),
      payload: {
        activeRepo,
        status,
        selectedNode,
        impact,
        graph: graph
          ? {
              nodeCount: graph.nodes.length,
              edgeCount: graph.edges.length,
              sampleNodes: graph.nodes.slice(0, 30),
              sampleEdges: graph.edges.slice(0, 30),
            }
          : null,
      },
    }))
  }, [activeRepo, status, selectedNode, impact, graph])

  // ── Actions ────────────────────────────────────────────────────
  const onIndex = useCallback(async () => {
    const target = indexingPath.trim()
    if (!target) return
    setIndexBusy(true)
    setIndexNotice(null)
    try {
      const res = await api.atlasIndex(target)
      const indexedFiles = res.files_indexed ?? '?'
      setIndexNotice(`Indexed ${target} — ${indexedFiles} files.`)
      await bootstrap()
      // Snap to the freshly-indexed repo.
      setActiveRepo(res.repo_id ?? target)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Indexing failed'
      setIndexNotice(`Failed: ${msg}`)
    } finally {
      setIndexBusy(false)
    }
  }, [bootstrap, indexingPath])

  const onRunImpact = useCallback(async () => {
    if (!activeRepo || !selectedNode) return
    setImpactLoading(true)
    setImpact(null)
    try {
      const target = selectedNode.name
      const res = await api.atlasImpact(activeRepo, target, 3, 80, 'auto')
      setImpact(res)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Impact query failed'
      setImpact({
        target: selectedNode.name,
        risk: 'unknown',
        impacted: [],
        verification_steps: [`Error: ${msg}`],
      })
    } finally {
      setImpactLoading(false)
    }
  }, [activeRepo, selectedNode])

  const onSelectFromSearch = useCallback((hit: AtlasSearchHit) => {
    setSelectedId(hit.id)
    setImpact(null)
  }, [])

  const onJumpToImpacted = useCallback((id: string) => {
    setSelectedId(id)
  }, [])

  const onChangeGraphLimit = useCallback((value: number) => {
    setGraphLimit(value)
  }, [])

  const sidebarStyle: CSSProperties = { width: 320, minWidth: 320 }
  const inspectorStyle: CSSProperties = { width: 360, minWidth: 360 }

  return (
    <div className="flex h-full w-full flex-col bg-background text-foreground">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-2">
        <div className="flex items-center gap-3">
          <div>
            <div className="text-sm font-semibold">Atlas — Code Graph</div>
            <div className="text-[11px] text-muted-foreground">
              Visual dependency intelligence for users and agents.
            </div>
          </div>
          <StatusPill status={status} />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={activeRepo ?? ''}
            onChange={(e) => setActiveRepo(e.target.value || null)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
            disabled={reposLoading || repos.length === 0}
          >
            {repos.length === 0 && <option value="">No indexed repositories</option>}
            {repos.map((r) => {
              const id = r.repo_id ?? r.path
              return (
                <option key={id} value={id}>
                  {r.name ?? r.path}
                </option>
              )
            })}
          </select>
          <button
            type="button"
            onClick={() => activeRepo && refreshGraph(activeRepo)}
            disabled={!activeRepo || graphLoading}
            className="rounded-md border border-border bg-muted px-2 py-1 text-xs hover:bg-muted/70 disabled:opacity-50"
          >
            {graphLoading ? '…' : 'Refresh'}
          </button>
        </div>
      </div>

      {bootstrapErr && (
        <div className="border-b border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">
          {bootstrapErr}{' '}
          <button
            type="button"
            onClick={() => void bootstrap()}
            className="underline underline-offset-2"
          >
            Retry
          </button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar — repo + search + index */}
        <div
          style={sidebarStyle}
          className="flex flex-col gap-3 overflow-y-auto border-r border-border bg-card/50 p-3"
        >
          <section className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-muted-foreground">Index a repository</div>
            <div className="flex gap-1.5">
              <input
                value={indexingPath}
                onChange={(e) => setIndexingPath(e.target.value)}
                placeholder="/absolute/path/to/repo"
                className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[11px] outline-none focus:border-primary"
              />
              <button
                type="button"
                onClick={onIndex}
                disabled={!indexingPath.trim() || indexBusy}
                className="rounded-md bg-primary px-2 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {indexBusy ? '…' : 'Index'}
              </button>
            </div>
            {indexNotice && (
              <div className="rounded-md bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
                {indexNotice}
              </div>
            )}
            <div className="text-[10px] leading-tight text-muted-foreground">
              CLI alternative:{' '}
              <code className="rounded bg-muted/50 px-1">
                python -m alos_atlas.cli index .
              </code>
            </div>
          </section>

          <section className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-muted-foreground">Search</div>
            <SearchPanel repo={activeRepo} onSelectHit={onSelectFromSearch} />
          </section>

          <section className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-muted-foreground">Graph density</div>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={20}
                max={200}
                step={10}
                value={graphLimit}
                onChange={(e) => onChangeGraphLimit(Number(e.target.value))}
                className="flex-1"
              />
              <span className="w-10 text-right text-xs text-muted-foreground">
                {graphLimit}
              </span>
            </div>
          </section>
        </div>

        {/* Main canvas */}
        <div className="flex-1 overflow-hidden bg-background">
          <GraphCanvas
            positioned={positioned}
            edges={graph?.edges ?? []}
            selectedId={selectedId}
            highlightedIds={highlightedIds}
            onSelect={(id) => {
              setSelectedId(id)
              setImpact(null)
            }}
          />
        </div>

        {/* Right inspector — selection + impact */}
        <div
          style={inspectorStyle}
          className="flex flex-col gap-3 overflow-y-auto border-l border-border bg-card/50 p-3"
        >
          <section className="flex flex-col gap-1">
            <div className="text-xs font-semibold text-muted-foreground">Selected node</div>
            {selectedNode ? (
              <div className="rounded-md border border-border bg-background/60 px-2 py-1.5 text-xs">
                <div className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: nodeColor(selectedNode.type) }}
                  />
                  <span className="font-medium">{selectedNode.name}</span>
                  <span className="ml-auto text-muted-foreground">{selectedNode.type}</span>
                </div>
                {selectedNode.path && (
                  <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                    {selectedNode.path}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                Click a node to inspect it. Search results above will also select.
              </div>
            )}
          </section>

          <section className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-muted-foreground">Impact</div>
              <button
                type="button"
                onClick={onRunImpact}
                disabled={!selectedNode || impactLoading}
                className="rounded-md bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
              >
                {impactLoading ? '…' : 'Run impact'}
              </button>
            </div>
            <ImpactPanel
              impact={impact}
              loading={impactLoading}
              onJump={onJumpToImpacted}
            />
          </section>

          <section className="mt-auto flex flex-col gap-1 border-t border-border pt-2 text-[10px] text-muted-foreground">
            <div>
              <span className="font-medium text-foreground">Legend:</span> file (blue) ·
              route (purple) · function (green) · class (amber) · module (cyan)
            </div>
            <div>
              Same data backs agent tools: <code className="rounded bg-muted/40 px-1">atlas_search</code>,{' '}
              <code className="rounded bg-muted/40 px-1">atlas_impact</code>,{' '}
              <code className="rounded bg-muted/40 px-1">atlas_context</code>.
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
