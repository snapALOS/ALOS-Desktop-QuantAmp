# ALOSAtlas — Overview

**Canonical name:** ALOSAtlas  
**Dead name:** RexNexus  
**Source:** `Upgrades From Rex/rexnexus/` *(or `/Volumes/DDrive/Rex'S Upgrades/rexnexus/`)*  
**Target location:** `modules/atlas/`  
**Tagline:** "A live map of your codebase. Agents grounded in facts, not guesses."

## What it is

A SQLite-backed code intelligence graph that indexes symbols, imports, call edges, and test relationships across a workspace. Exposes bounded query tools to agents over MCP so they can answer "what does this change break?" without guessing.

## Why it's in v0.2

Agents hallucinate less when they can look things up. Atlas is the lookup substrate for the entire agent fleet:

- Before a refactor: "Show me everywhere `UserService.authenticate` is called."
- Before a delete: "Is this dead code or referenced by tests?"
- Before approving a diff: "What's the blast radius of this change?"

This is the factual grounding layer. Without it, agents make confident wrong claims.

## Key capabilities (v0.2)

| Capability | Source status | v0.2 change |
|---|---|---|
| SQLite symbol/edge store | Works | Path rename to `~/.alos/atlas/atlas.sqlite` |
| Tree-sitter parsers (Python, TS, Rust minimum) | Works | None for the big three; audit others |
| MCP stdio server | Works | Rename; verify tool gates wire to ALOS capability system |
| Incremental re-index on file save | Works | Subscribe to `forge.file.saved` events |
| Tools: `impact`, `change_scope`, `recommend_tests`, `symbol_context`, `file_context` | Works | Rebrand tool names: `atlas_impact_symbol`, etc. |
| Query latency budget | Unknown | Measure + document; target <100ms p95 for bounded queries |

## Agent-facing tools (MCP)

All tools are `risk: "low"` (read-only) unless noted.

- `atlas_impact_symbol(symbol, file?)` — list callers/users of a symbol. Returns up to N results with file paths + line numbers.
- `atlas_change_scope(path)` — given a file, return files that depend on it (directly + transitively, capped).
- `atlas_recommend_tests(path_or_symbol)` — return tests most likely affected by a change.
- `atlas_symbol_context(symbol)` — return the defining file, signature, surrounding context.
- `atlas_file_context(path)` — return a structural summary of a file (top-level symbols, imports).
- `atlas_index_status()` — returns whether indexing is in progress and progress %.

## What is NOT in v0.2

- Cross-repo indexing (single workspace only).
- Language support beyond Python / TS / JS / Rust for v0.2. Others deferred.
- Semantic search / embedding-based retrieval. Atlas is structural only.
- Graph visualization UI. (Post-v1 marketing hook; for v0.2 Atlas is headless to users, agent-facing only.)

## Surfaces

### Frontend
- Mount point: `/atlas` route.
- v0.2 UI is minimal: workspace status, index progress, a symbol-lookup panel ("paste a symbol, see who references it"), and a re-index button.
- The agent-facing experience is the primary deliverable; the UI is diagnostic.

### Backend (Python)
- Package: `alos_atlas` at `modules/atlas/backend/src/alos_atlas/`.
- Routes under `/api/atlas/*` on the sidecar.
- MCP server at `modules/atlas/backend/src/alos_atlas/mcp_server.py` — stdio-attached child of the sidecar.
- SQLite at `~/.alos/atlas/atlas.sqlite`.

### Events emitted
- `atlas.index.started` (payload: root)
- `atlas.index.progress` (payload: root, pct, fileCount)
- `atlas.index.complete` (payload: root, symbolCount, durationMs)
- `atlas.index.error` (payload: root, error)

### Events consumed
- `forge.file.saved` → schedule incremental re-index of that file.
- `forge.workspace.opened` → full re-index of the new workspace (debounced).

## Dependencies on other modules

- **Forge** (optional): emits the events that drive incremental indexing. Atlas works with a manual re-index button if Forge is absent, but the auto-refresh experience requires Forge.
- **LSP** (optional): some queries are more accurate with LSP references than with tree-sitter alone. Atlas degrades gracefully if LSP unavailable.

## Risk & unknowns

- **Tree-sitter binaries** add install weight; confirm bundling strategy fits macOS + Windows + Linux.
- **First-time index** of a large monorepo could take minutes; ensure it's non-blocking and resumable.
- **SQLite write contention** with incremental re-index vs agent queries. Use WAL mode and reader/writer connection split.
