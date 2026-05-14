---
id: 0157
title: Packaged backend must mount module routers
area: core
status: done
assigned_to: codex
created: 2026-04-19
updated: 2026-04-19
effort: s
blocks: [0143, 0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0157 — Packaged Backend Must Mount Module Routers

## Context

Scout/live logs showed the frozen backend starting successfully but warning that the `modules` root was missing. As a result, module-owned APIs such as Current, Atlas, and Chamber returned `404` in the packaged/dev-bundled layout even though their source routers existed.

## Scope

Fix module backend discovery for source and PyInstaller one-dir layouts, and ensure the backend build includes module router/support files.

**In scope:**
- Teach backend module discovery to check both source and frozen `_internal/modules` layouts.
- Bundle `modules/*/backend/src/**` into the frozen backend resource tree.
- Verify the source app mounts Current, Atlas, Chamber, and Forge module APIs.

**Out of scope:**
- Rebuilding or restarting the currently live app process.
- Refactoring module API implementations.
- Resolving the broader `bugs_report.csv` architecture backlog.

## Files touched

- `backend/src/api/server.py` — module root discovery now supports source and frozen layouts.
- `backend/alos_backend.spec` — PyInstaller now stages module backend routers/support packages.
- `planning/40-tracking/tasks/0157-packaged-module-router-discovery.md` — task record.
- `planning/40-tracking/board.md` — task status.
- `planning/40-tracking/PATH-TO-COMPLETION.md` — status rollup.

## Acceptance criteria

- [x] Source import of `src.api.server:app` reports `/api/current/health`.
- [x] Source import of `src.api.server:app` reports `/api/atlas/repos`.
- [x] Source import of `src.api.server:app` reports `/api/chamber/list`.
- [x] Source import of `src.api.server:app` reports `/api/chamber/gates`.
- [x] `backend/alos_backend.spec` includes `modules/*/backend/src` data.
- [x] `python3.11 -m py_compile backend/src/api/server.py backend/alos_backend.spec` passes.

## Implementation notes

The running Tauri dev app uses `src-tauri/target/debug/resources/backend/alos-backend`, so source changes do not alter the already-live process. Rebuild the backend sidecar before expecting packaged Current/Atlas/Chamber APIs to respond.

## Verification commands

```bash
python3.11 -m py_compile backend/src/api/server.py backend/alos_backend.spec
cd backend && python3.11 - <<'PY'
from src.api.server import app
paths = {getattr(route, 'path', '') for route in app.routes}
for path in ['/api/current/health', '/api/atlas/repos', '/api/chamber/list', '/api/chamber/gates']:
    print(path, path in paths)
PY
```

## Status updates

- 2026-04-19 (codex): created and completed after live logs showed missing module root and repeated module API `404`s.
