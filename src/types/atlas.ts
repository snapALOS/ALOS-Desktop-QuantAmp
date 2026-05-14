/**
 * Atlas API response shapes.
 *
 * Mirrors `modules/atlas/backend/src/api/router.py`, which itself wraps
 * `alos_atlas.query.AlosAtlasQueries`. Keep this file in lockstep — the
 * router's docstrings describe the canonical shape; this is the typed
 * surface the React AtlasView consumes.
 */

export interface AtlasRepoEntry {
  repo_id: string
  path: string
  name?: string
  last_indexed?: string | null
  status?: string
  [key: string]: unknown
}

export interface AtlasReposResponse {
  repositories: AtlasRepoEntry[]
}

export interface AtlasStatus {
  repo_id?: string
  path?: string
  indexed?: boolean
  last_indexed?: string | null
  node_count?: number
  edge_count?: number
  stale_reasons?: string[]
  [key: string]: unknown
}

export interface AtlasSearchHit {
  id: string
  type: string
  name: string
  path?: string
  confidence?: number
  snippet?: string
  [key: string]: unknown
}

export interface AtlasSearchResponse {
  query: string
  results: AtlasSearchHit[]
  [key: string]: unknown
}

export interface AtlasContextEntry {
  id: string
  type: string
  name: string
  path?: string
  relation?: string
  confidence?: number
  [key: string]: unknown
}

export interface AtlasContextResponse {
  target?: AtlasSearchHit | null
  callers?: AtlasContextEntry[]
  callees?: AtlasContextEntry[]
  references?: AtlasContextEntry[]
  files?: AtlasContextEntry[]
  symbols?: AtlasContextEntry[]
  routes?: AtlasContextEntry[]
  [key: string]: unknown
}

export interface AtlasImpactedNode {
  id: string
  type: string
  name: string
  path?: string
  depth?: number
  confidence?: number
  reason?: string
  [key: string]: unknown
}

export interface AtlasImpactResponse {
  target: string
  target_type?: string
  risk?: string
  impacted: AtlasImpactedNode[]
  tests?: AtlasImpactedNode[]
  verification_steps?: string[]
  [key: string]: unknown
}

export interface AtlasGraphNode {
  id: string
  type: string
  name: string
  path?: string
  confidence?: number
}

export interface AtlasGraphEdge {
  id: string
  source_id: string
  target_id: string
  type: string
  confidence?: number
  reason?: string
}

export interface AtlasGraphResponse {
  status?: AtlasStatus
  nodes: AtlasGraphNode[]
  edges: AtlasGraphEdge[]
}

export interface AtlasIndexResult {
  repo_id: string
  path: string
  files_indexed?: number
  symbols?: number
  edges?: number
  duration_seconds?: number
  status?: string
  [key: string]: unknown
}

export interface AtlasReportResponse {
  target?: string | null
  generated_at?: string
  risk?: string
  summary?: string
  impacted?: AtlasImpactedNode[]
  tests?: AtlasImpactedNode[]
  [key: string]: unknown
}
