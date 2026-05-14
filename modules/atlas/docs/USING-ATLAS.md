# Using Atlas — Visual Dependency Intelligence

Atlas is the ALOS-native code-graph module. It indexes a repository, builds
an inspectable file/symbol/dependency graph, and exposes the same surface
to both humans (the AtlasView) and ALOS swarm agents (atlas_* tools).

---

## Three ways to drive Atlas

### 1. Desktop app (humans)

Open the app, click the **Atlas** module in the activity bar.

- Top-right repo selector lists every repo the local Atlas instance has
  indexed.
- Sidebar **Index a repository** field accepts an absolute path. Click
  *Index* to register-and-index in one shot.
- Search box queries by concept; results jump-select nodes in the graph.
- Right inspector shows the selected node and a **Run impact** button —
  one click computes the d=3 blast radius (callers, tests, verification
  steps) for the selected symbol.

### 2. Local CLI (humans, scripts, headless)

```bash
# From the repo root, with alos_atlas dependencies installed:
pip install tree-sitter walkdir tree_sitter_languages

# Make the CLI use the same Atlas home as the desktop sidecar:
export PYTHONPATH="$(pwd)/modules/atlas/backend/src:$PYTHONPATH"
export ALOS_ATLAS_HOME="$(pwd)/backend/atlas"

# Register this repo, then index it by name:
python -m alos_atlas.cli register "ALOS-Desktop + QuantAmp" .
python -m alos_atlas.cli index "ALOS-Desktop + QuantAmp"

# Search:
python -m alos_atlas.cli search "ALOS-Desktop + QuantAmp" "auth validation"

# Impact:
python -m alos_atlas.cli impact "ALOS-Desktop + QuantAmp" --target validate_api_key

# Status:
python -m alos_atlas.cli status "ALOS-Desktop + QuantAmp"
```

The CLI lives at `modules/atlas/backend/src/alos_atlas/cli.py`. In packaged
desktop runs, the sidecar stores Atlas under the ALOS user-data directory.
In local development, `backend/atlas` is the matching default because the
backend falls back to project-local user data.

To generate release-impact reports:

```bash
python -m alos_atlas.cli export-report "ALOS-Desktop + QuantAmp" --target ChatView
python -m alos_atlas.cli export-report "ALOS-Desktop + QuantAmp" --target ForgeView
python -m alos_atlas.cli export-report "ALOS-Desktop + QuantAmp" --target CurrentView
python -m alos_atlas.cli export-report "ALOS-Desktop + QuantAmp" --target AtlasView
```

### 3. ALOS agents (LLM swarm)

Six tools are wired into the swarm at the registry level — granted to the
Technical Architect, Code Refactor, File Map, Security Auditor,
StackTrace, Sanity Check, and Project Manager agents. They mirror the
visual surface byte-for-byte:

| Tool | What the agent does with it |
|------|------------------------------|
| `atlas_search` | Find candidate files/symbols by concept before reading |
| `atlas_context` | Resolve callers/callees for a symbol before refactoring |
| `atlas_file_context` | Discover what a file imports, defines, depends on |
| `atlas_impact` | Compute blast radius BEFORE proposing a patch |
| `atlas_status` | Verify the index is fresh before relying on it |
| `atlas_report` | Generate a release-grade dependency + impact report |

Tool definitions live in `backend/src/tools/atlas_tools.py`. They wrap
the same `alos_atlas.query.AlosAtlasQueries` API in-process — no HTTP
round-trip, so they're cheap to call inside a swarm turn.

---

## Backend wiring

The Atlas FastAPI router at
`modules/atlas/backend/src/api/router.py` is auto-mounted at
`/api/atlas/*` by the sidecar's `discover_and_mount_modules` pass. No
manual registration needed.

Endpoints exposed:

```
GET  /api/atlas/health
GET  /api/atlas/repos
GET  /api/atlas/status?repo=...
POST /api/atlas/index?repo=...
GET  /api/atlas/search?repo=...&q=...&limit=...
GET  /api/atlas/symbol?repo=...&name=...&limit=...
GET  /api/atlas/file?repo=...&path=...&limit=...
GET  /api/atlas/route?repo=...&route=...&limit=...
GET  /api/atlas/impact?repo=...&target=...&type=auto&depth=3&limit=50
GET  /api/atlas/change_scope?repo=...&files=...&use_git=false&limit=50
GET  /api/atlas/recommend_tests?repo=...&target=...&files=...&limit=20
GET  /api/atlas/graph?repo=...&limit=80
GET  /api/atlas/graph_overview?repo=...&limit=20
GET  /api/atlas/files?repo=...&limit=100&indexed_only=true
GET  /api/atlas/symbols?repo=...&limit=100&type=...
GET  /api/atlas/report?repo=...&target=...&type=auto
```

Every call requires a Bearer token (the standard ALOS auth middleware).

---

## Storage

Inside ALOS Desktop, Atlas writes its on-disk graph under the ALOS
user-data directory at `<ALOS_DATA_DIR>/atlas`. In local development that is
normally `backend/atlas`. The standalone Atlas CLI falls back to
`~/.alos/atlas/` unless `ALOS_ATLAS_HOME` or `--home` is provided.

Each registered repository gets a stable `repo_id` and a SQLite database
under that directory. To inspect a local development index:

```bash
ls -la backend/atlas/repos/
sqlite3 backend/atlas/repos/<repo_id>/index.sqlite "SELECT type, COUNT(*) FROM nodes GROUP BY type;"
```

---

## Packaging

Live indexing works in both dev and packaged builds. `tree-sitter` and
`tree-sitter-languages` are in `backend/requirements.txt`; the
PyInstaller spec (`backend/alos_backend.spec`) adds
`modules/atlas/backend/src` to `pathex`, pre-lists `alos_atlas`
submodules as hidden imports, and runs `collect_all` on
`tree_sitter_languages` so compiled grammar `.so`/`.dylib` files ship
inside `dist/alos-backend/_internal/`. No extra host-Python install
needed for the frozen sidecar.

---

## GitNexus parity and Atlas upgrades

Atlas is not intended to be a thin GitNexus clone. For v0.2 it now provides
the release-critical surface ALOS needs:

- Desktop indexing from the Atlas module with automatic repo registration.
- Interactive SVG graph rendering for indexed files, symbols, routes, and
  dependency edges.
- Concept/name/path search with jump selection.
- Direct and transitive impact inspection with risk, linked tests, and
  verification guidance.
- Agent-facing `atlas_*` tools registered through the core tool registry.
- Markdown dependency/impact reports for release-critical flows.

Known gaps against GitNexus that remain honest for v0.2:

- Atlas does not yet have GitNexus' full execution-flow database or process
  clustering.
- Atlas dependency extraction is parser and heuristic based; GitNexus still
  has richer call-flow confidence for some mixed-language paths.
- Atlas has no separate MCP resource server wired into Codex yet, although
  it does expose an internal MCP-compatible stdio server.
- Atlas graph layout is built into the desktop view and is intentionally
  bounded; very large repo views should use search plus focused impact
  reports instead of trying to render every node at once.

Proprietary Atlas upgrades already present:

- Uses the ALOS sidecar auth model and user-data storage.
- Shares one query surface between the desktop view, HTTP API, CLI, and
  agent tools.
- Produces release-ready verification steps and affected-test guidance from
  the same graph evidence the user can inspect visually.
