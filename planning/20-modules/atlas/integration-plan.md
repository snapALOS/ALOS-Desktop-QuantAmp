# ALOSAtlas — Integration Plan

**Strategy:** Atlas is small and self-contained in the source. Fold-in is mostly rename + wire events + bundle tree-sitter.

**Estimated effort:** 2–3 days of focused work.

## Phases

### Phase 1 — Vendor + inventory (0.25 day)

1. Copy `Upgrades From Rex/rexnexus/` → `modules/atlas/_vendor/`.
2. Produce `INVENTORY.md`.

**Task file:** `tasks/0050-atlas-vendor-inventory.md`

---

### Phase 2 — Scaffold (0.25 day)

1. `modules/atlas/` layout per boundaries doc.
2. `MODULE.toml`.
3. Stub contracts.
4. Placeholder `/atlas` route + activity-bar entry.

**Task file:** `tasks/0051-atlas-scaffold.md`

---

### Phase 3 — Backend fold-in (1 day)

1. Move Python source → `modules/atlas/backend/src/alos_atlas/`.
2. Rename package `rexnexus` → `alos_atlas`.
3. DB path: `~/.rexnexus/` → `~/.alos/atlas/`.
4. Mount HTTP API under `/api/atlas/*` of sidecar.
5. Keep MCP stdio server as a child process — no changes needed beyond rename.
6. Rename MCP tools with `atlas_` prefix.
7. Verify tree-sitter parsers for Python / TS / JS / Rust are vendored or installable. Add bundling to `scripts/build_backend.py`.

**Acceptance:**
- `python -m alos_atlas.index /path/to/workspace` builds a SQLite graph.
- `atlas_impact_symbol` called via MCP returns correct results for a known reference.
- Zero references to `rexnexus` in `modules/atlas/backend/`.

**Task files:** `tasks/0052-atlas-backend-fold.md`, `tasks/0053-atlas-mcp-rename.md`, `tasks/0054-atlas-tree-sitter-bundle.md`

---

### Phase 4 — Event wiring (0.5 day)

1. Subscribe Atlas to `forge.file.saved` and `forge.workspace.opened`.
2. Debounce bursts; coalesce saves within 500ms.
3. Emit `atlas.index.*` events per the contract.

**Acceptance:** saving a file in Forge produces a debounced re-index; monitor tab in Current shows the `atlas.index.complete` event within expected latency.

**Task file:** `tasks/0055-atlas-event-wiring.md`

---

### Phase 5 — Minimal diagnostic UI (0.5 day)

1. `/atlas` route renders: index status, last completion time, symbol count, re-index button, symbol-lookup text field.
2. No graph visualization (deferred post-v1).

**Acceptance:** UI loads; re-index button triggers a full index; lookup field returns references.

**Task file:** `tasks/0056-atlas-diagnostic-ui.md`

---

### Phase 6 — Cleanup (0.25 day)

1. Delete `_vendor/`.
2. Drift grep clean.
3. Roadmap update.

**Task file:** `tasks/0057-atlas-cleanup.md`

---

## Dependencies & ordering

- Phase 2 blocks 3–6.
- Phase 3 blocks 4, 5.
- Phase 4 depends on Forge Phase 3 being done enough to emit `forge.file.saved`. If Forge is behind, Phase 4 can use synthetic events.

## Risks

- Tree-sitter cross-platform bundling is historically finicky. Budget 0.5 day contingency.
- First index of a large workspace could block the sidecar startup. Ensure indexing runs in a background thread from the start.
