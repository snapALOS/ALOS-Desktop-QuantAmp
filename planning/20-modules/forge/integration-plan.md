# ALOSForge — Integration Plan

**Strategy:** Option A (fold-in). Pull the RexCode tree into `modules/forge/`, rebrand, strip HubAdapter, wire into shell, preserve behavior.

**Estimated effort:** 2–3 weeks of focused work across 1–2 agents.

## Phases

### Phase 1 — Vendor the source (1 day)

1. Copy `Upgrades From Rex/rexcode proprietary-ide/` → `modules/forge/_vendor/` (temporary staging).
2. Produce a file-by-file inventory (`modules/forge/_vendor/INVENTORY.md`):
   - Path, size, language, "keep / drop / rewrite" decision, owning contract.
3. **No code runs yet.** This is read-only stocktaking.

**Acceptance:** `modules/forge/_vendor/INVENTORY.md` exists and lists every file with a decision. No other changes to the repo.

**Task file:** `tasks/0010-forge-vendor-inventory.md`

---

### Phase 2 — Scaffolding (1–2 days)

1. Create `modules/forge/` layout per [module-boundaries.md](../../10-architecture/module-boundaries.md).
2. Write `modules/forge/MODULE.toml` with locked metadata.
3. Create empty `modules/forge/contracts/{events.ts,commands.ts,python.py,mcp.py}`.
4. Add workspace entry to `package.json` and `pyproject.toml`.
5. Wire a placeholder `/forge` route that renders "ALOSForge — under construction."
6. Wire an activity bar entry driven by `MODULE.toml`.

**Acceptance:**
- `bun run dev` shows ALOS with a Forge entry in the activity bar.
- Clicking it shows the placeholder page.
- `modules/forge/` passes its own `package.json` install and `pyproject.toml` install standalone.

**Task file:** `tasks/0011-forge-scaffold.md`

---

### Phase 3 — Move editor + terminal (4–6 days)

1. Promote vendored Monaco integration from `_vendor/` into `modules/forge/frontend/src/editor/`.
2. Promote vendored xterm integration into `modules/forge/frontend/src/terminal/`.
3. Rename files: `rex*` → `alos*` (or drop the prefix entirely where appropriate).
4. Replace `TauriAdapter` imports with direct `@tauri-apps/api` imports — no adapter layer needed once HubAdapter is gone.
5. Delete HubAdapter code entirely. Delete `isAgentObserving` stubs; reimplement against ALOS agent runtime in Phase 5.
6. Move Rust pty code into `src-tauri/src/forge/pty.rs` (it's Tauri-core, not module-isolated).

**Acceptance:**
- Opening a file from the workspace shows it in Monaco with syntax highlighting.
- Opening a terminal runs a local shell and echoes input correctly on macOS (primary) and Linux.
- Zero references to `rex*` / `Rex*` / `RexBot` / `RexCode` in `modules/forge/` outside `_vendor/`.
- All v0.1 tests still pass.

**Task files:** `tasks/0012-forge-editor.md`, `tasks/0013-forge-terminal.md`, `tasks/0014-forge-rebrand.md`

---

### Phase 4 — LSP (3–4 days)

Implement per [lsp-integration.md](../../10-architecture/lsp-integration.md).

1. Rust supervisor in `src-tauri/src/lsp/` (spawn/health/restart).
2. `~/.alos/lsp.toml` loader with seed defaults.
3. Bundle pyright, typescript-language-server, rust-analyzer into `src-tauri/resources/lsp/`.
4. Update `scripts/build_backend.py` (or add `scripts/build_lsp.py`) to stage binaries into the bundle.
5. Frontend: wire `monaco-languageclient` to the supervisor.

**Acceptance:** all four acceptance criteria in `lsp-integration.md`.

**Task files:** `tasks/0015-lsp-supervisor.md`, `tasks/0016-lsp-bundling.md`, `tasks/0017-lsp-frontend-client.md`

---

### Phase 5 — Agent bridge (4–5 days)

1. Implement MCP tools: `forge_open_file`, `forge_apply_diff`, `forge_read_file`, `forge_run_command`, `forge_get_selection`.
2. Diff acceptance UI: when agent proposes a diff, show inline diff with Accept / Reject buttons. Nothing lands until user clicks.
3. Observed-pty: `forge_run_command` creates a pty whose stdout/stderr stream is mirrored to the agent's context buffer.
4. Capability gate entries in `backend/src/agents/capabilities.py` for each new tool.

**Acceptance:**
- Agent asked to "open `src/foo.py`" successfully opens it in the editor.
- Agent asked to "change line 42 to X" produces a diff card the user can accept or reject.
- Rejecting leaves the buffer untouched.
- Agent asked to "run `pytest`" creates a terminal tab, runs, and the agent can see the output.

**Task files:** `tasks/0018-forge-mcp-tools.md`, `tasks/0019-forge-diff-acceptance.md`, `tasks/0020-forge-observed-pty.md`

---

### Phase 6 — Cleanup (1–2 days)

1. Delete `modules/forge/_vendor/`.
2. Extensions panel: preserve hardcoded demo data; add a banner "Extensions API coming in v0.3."
3. Run the drift grep (see [naming.md](../../00-overview/naming.md)); must return zero matches.
4. Update `planning/00-overview/roadmap.md` to check off Forge items.

**Acceptance:** rebrand grep clean; `_vendor/` gone; all Forge tasks closed.

**Task file:** `tasks/0021-forge-cleanup.md`

---

## Dependencies & ordering

- Phase 2 blocks 3–6.
- Phase 3 blocks 4 and 5 (LSP and agent bridge need a working editor).
- Phase 4 and 5 are **parallelizable** across two agents.
- Phase 6 blocks release.

## Rollback

If Phase 3 fails to produce a working editor within 2x estimate, abandon Option A and revisit Option B (cherry-pick only Monaco integration, leave the rest). Rollback is clean because nothing outside `modules/forge/` and `src-tauri/src/forge/` changes until Phase 5.
