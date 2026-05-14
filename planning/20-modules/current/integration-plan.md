# ALOSCurrent — Integration Plan

**Strategy:** vendor the source, strip RexHub coupling, wrap executors for async agent calls, embed SPA under `/current`.

**Estimated effort:** 5–7 days of focused work.

## Phases

### Phase 1 — Vendor + inventory (0.5 day)

1. Copy `Upgrades From Rex/rexflow-workflow-orchestrator/` → `modules/current/_vendor/`.
2. Produce `modules/current/_vendor/INVENTORY.md`: every file, keep/drop/rewrite decision.
3. Critical decisions to document in the inventory:
   - Which files hardcode RexHub or RexBot swarm model.
   - Which files import external packages (should be zero; flag any that do).
   - Which frontend files assume `/dist` vs dev-server mount.

**Acceptance:** inventory file exists, decisions captured.

**Task file:** `tasks/0030-current-vendor-inventory.md`

---

### Phase 2 — Scaffolding (0.5 day)

1. Create `modules/current/` layout per boundaries doc.
2. Write `modules/current/MODULE.toml`.
3. Stub contracts in `modules/current/contracts/`.
4. Wire placeholder `/current` route.
5. Add activity-bar entry.

**Acceptance:** activity bar shows Current; placeholder page renders.

**Task file:** `tasks/0031-current-scaffold.md`

---

### Phase 3 — Backend fold-in (1.5–2 days)

1. Move `_vendor/rexflow-server/` Python source → `modules/current/backend/src/alos_current/`.
2. Rename package: `rexflow_server` → `alos_current`. Update all imports.
3. Change SQLite default path: `~/.rexflow/rexflow.sqlite` → `~/.alos/current/current.sqlite`.
4. Delete RexHub integration code (`rexhub_adapter.py` or similar). Replace with a thin ALOS event-bus subscriber.
5. **Replace swarm nodes:**
   - `assign_department_head` → `invoke_agent` with `agent_id="supervisor"`
   - `assign_sub_agent` → `invoke_agent` with `agent_id=<specified>`
   - `escalation_gate` → keep as-is but wire to ALOS approval UI instead of RexBot one
6. Wrap `_run_node` so `invoke_agent` calls happen in a `concurrent.futures.ThreadPoolExecutor` to not block the workflow engine's main loop.
7. Mount the Current HTTP API under `/api/current/*` of the ALOS sidecar (replace standalone `http.server` with registration into the core FastAPI/Flask/stdlib router — whichever the sidecar uses).

**Acceptance:**
- Creating and running the sample workflow (`current/backend/samples/hello.json`) works end-to-end via the ALOS sidecar.
- SQLite file lands at `~/.alos/current/current.sqlite`.
- Zero references to `rexflow` / `RexFlow` / `rexhub` in `modules/current/backend/`.

**Task files:** `tasks/0032-current-backend-fold.md`, `tasks/0033-current-agent-node.md`, `tasks/0034-current-http-mount.md`

---

### Phase 4 — Frontend fold-in (1–1.5 days)

1. Move `_vendor/frontend/` → `modules/current/frontend/`.
2. Rebrand: strip the "RexFlow" wordmark, swap colors to ALOS palette, rename routes.
3. Swap the standalone bootstrap (`main.tsx` mounting to `#root`) for a **mounted-module bootstrap** that exports a React component consumed by the shell's `/current` route.
4. Point API client at `/api/current/*` (same-origin; no port 8770 anymore).
5. Swap the Settings → API token field for a disabled "auth disabled in v0.2" notice.

**Acceptance:**
- Clicking Current in the activity bar shows the Designer tab.
- Creating a workflow in the designer persists to the correct SQLite path.
- Monitor tab streams events from the sidecar SSE endpoint.

**Task files:** `tasks/0035-current-frontend-mount.md`, `tasks/0036-current-frontend-rebrand.md`, `tasks/0037-current-frontend-api.md`

---

### Phase 5 — Event-bus triggers (1 day)

1. Implement `alos_event` trigger node type in the executor.
2. Subscribe `alos_current` to the shell event bus (via Tauri events or a Python-side tap on the same channel).
3. Match event payloads against workflow triggers; fire matching workflows.
4. Test: configure a workflow with "on `forge.file.saved` where path endsWith '.py'" trigger; save a `.py` file in Forge; verify the workflow runs.

**Acceptance:** the integration test above passes.

**Task file:** `tasks/0038-current-event-triggers.md`

---

### Phase 6 — Agent MCP tools (0.5 day)

1. Implement `current_list_workflows`, `current_trigger_workflow`, `current_get_run_status`.
2. Wire capability gates.
3. Add `risk: "medium"` on `current_trigger_workflow`.

**Acceptance:** agent asked "run the daily-summary workflow" produces a run id and that run appears in the Monitor tab.

**Task file:** `tasks/0039-current-mcp-tools.md`

---

### Phase 7 — Cleanup (0.5 day)

1. Delete `modules/current/_vendor/`.
2. Run drift grep; zero matches.
3. Update roadmap.

**Acceptance:** cleanup complete; all Current tasks closed.

**Task file:** `tasks/0040-current-cleanup.md`

---

## Dependencies & ordering

- Phase 2 blocks 3–7.
- Phase 3 blocks 4, 5, 6.
- Phase 4, 5, 6 are parallelizable across multiple agents.
- Phase 7 blocks release.

## Interaction with Forge fold-in

- Forge vendor/scaffold (Phase 1–2) and Current vendor/scaffold (Phase 1–2) can run in parallel — they touch different directories.
- LSP work on the Forge side does not interact with Current.
- Event-bus work on the Current side (Phase 5) benefits from Forge being at least to Phase 3 (so `forge.file.saved` events fire), but can be tested with synthetic events if needed.
