# PATH-TO-COMPLETION — v0.2

**Last updated:** 2026-04-19
**Applies to:** ALOS-Desktop + QuantAmp (this tree)
**Current state:** 0140 (Post-Antigravity remediation) landed. Shell
architecture, Rust core, Python QA-SIR, and planning hygiene are all
clean. The app is close, but v0.2 must not be rushed. Packaging and
smoke tests are necessary, not sufficient; the final gate is a full
release-readiness pass.

This file is the **single source of truth** for "what do I pick up
next." Other agents and the user should read this before starting work
so no one accidentally jumps ahead of a dependency.

---

## TL;DR

Work the remaining tasks in dependency-aware order. Fix product/runtime blockers
first, but all required release packaging must pass before 0147 can declare a
release candidate.

| # | Task ID | Title | Effort | Who blocks? | Status |
|---|---------|-------|--------|-------------|--------|
| 1 | ~~0141~~ | Install frontend deps required by vendored module code | s | blocks 0142, 0143 | ✅ done 2026-04-17 |
| 2 | ~~0142~~ | Fix verbatimModuleSyntax + implicit-any in vendored module code | m | blocks 0143 | ✅ done 2026-04-17 |
| 3 | ~~0144~~ | Tauri release-bundle dry run | s | surfaced 0145 + 0146 | ✅ done 2026-04-17 (with caveats — see notes) |
| 4 | ~~0145~~ | Packaged `.app` doesn't spawn frozen Python sidecar | s | blocks v0.2 ship | ✅ done 2026-04-18 |
| 5 | ~~0148~~ | Original-admin first-run setup without terminal bootstrap | s | blocks 0147 | ✅ done 2026-04-18 |
| 6 | ~~0149~~ | Frontier-grade authenticated Chat | m | blocks 0147 | ✅ done 2026-04-18 |
| 7 | ~~0150~~ | Forge solo/assisted/autonomous programming | m | blocks 0147 | ✅ done 2026-04-18 |
| 8 | ~~0151~~ | Current solo/assisted/autonomous workflow orchestration | l | blocks 0147 | ✅ done 2026-04-18 |
| 9 | **0152** | Atlas visual dependency intelligence for users and agents | l | blocks 0147 | 🔜 ready |
| 10 | **0153** | Chamber pre-write build/test gate | l | blocks 0147 | 🔜 ready |
| 11 | **0154** | Robust settings interface | m | blocks 0147 | 🔜 ready |
| 12 | **0146** | `bundle_dmg.sh` fails after `.app` is produced | xs | blocks release candidate | 🔜 ready |
| 13 | **0143** | End-to-end Tauri smoke test (dev-mode walkthrough) | s | blocks 0147 | ⛔ blocked by 0152-0154 |
| 14 | **0147** | Full v0.2 production readiness gate | m | final release decision | ⛔ blocked by 0143 + 0146 + 0152-0154 |

Additional hardening added after Scout came online:

| Task ID | Title | Status |
|---------|-------|--------|
| ~~0156~~ | Scout runtime observability | ✅ done 2026-04-18 |
| ~~0157~~ | Packaged backend must mount module routers | ✅ done 2026-04-19 |
| ~~0158~~ | Scout-driven systematic QA audit harness | ✅ done 2026-04-19 |

When 0152 through 0154 are fixed, 0143 passes, and 0146 produces a valid DMG,
ALOS may become an integration candidate. It is not a release candidate until
0147 passes against [`RELEASE-READINESS.md`](RELEASE-READINESS.md).

---

## Why this order

- **0141 must go first** because Vite lets missing packages slide at
  dev-server time, but `tsc -b` (run by `npm run build`) fails them.
  Until the packages are installed, 0142's type-only fixes can't be
  verified — too much noise in the `tsc` output.
- **0142 must go second** because `npm run build` still fails after
  0141 (via `verbatimModuleSyntax` violations + implicit-any params).
  A green build is a prerequisite for a meaningful smoke test.
- **0143 must go last** because it depends on `npm run build` being
  green (release-like build pipeline inside `npm run tauri dev`), on
  all Rust panics from 0140 being fixed, and on the full module surface
  mounting cleanly.

Running the early build/type tasks out of order wastes time — you re-discover
the same errors in a different shape. For the remaining tasks, prefer fixing
high-risk product/runtime failures first. Chat, Forge, Current, Atlas, Chamber,
and Settings must be real before the final smoke. Then close DMG packaging
before the final 0147 release decision. Passing a launch or packaging task does
not waive product-readiness gates.

---

## Step-by-step

### Step 1 — Task 0141: Install vendored module deps

**File:** `planning/40-tracking/tasks/0141-install-vendored-module-deps.md`

1. Open a shell in the project root:
   `cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp"`
2. Add these to `package.json` dependencies (MUI 6 for React 19):
   - `@mui/material`
   - `@mui/icons-material`
   - `@emotion/react`, `@emotion/styled` (MUI peers)
   - `@monaco-editor/react`
   - `xterm`, `xterm-addon-fit`
3. Run `npm install`.
4. Verify:
   ```bash
   npx tsc -b --noEmit 2>&1 | grep -E 'TS2307.*(@mui|@monaco|xterm)' | wc -l  # expect 0
   ```
5. Commit `package.json` + `package-lock.json`.
6. Flip the task's frontmatter to `status: done` and add a status
   update line with verification evidence.
7. Move the row from Ready to Done in `board.md`.

**Do NOT** touch module source code in this step. Dep installation
only.

### Step 2 — Task 0142: verbatimModuleSyntax + implicit-any cleanup

**File:** `planning/40-tracking/tasks/0142-vendored-verbatim-module-syntax.md`

1. Start with a clean tsc output:
   `npx tsc -b --noEmit 2>&1 | grep '^modules/' > /tmp/vendored-errs.txt`
2. Walk the list. For each violation:
   - **`import { Foo }` where `Foo` is only a type** → `import type { Foo }`.
   - **implicit-any callback param** → add `(e: ChangeEvent<HTMLInputElement>) =>`
     or the correct specific type. Avoid `any`.
   - **unused import (noUnusedLocals)** → remove.
3. Fix the `@/services/api` → `@/api` alias mismatch in
   `modules/chamber/frontend/src/ChamberView.tsx`.
4. Re-run:
   ```bash
   npx tsc -b --noEmit                                          # exit 0
   npx tsc -b --noEmit 2>&1 | grep -c '^modules/'                # expect 0
   npm run build                                                  # succeeds
   ```
5. **Do NOT** delete or rewrite any vendored file's logic. This is a
   pure type-annotation + import pass. If you find a real bug,
   open a new task (0144+) instead of fixing inline.
6. Flip frontmatter and board row as in Step 1.

### Step 3 — Task 0148: Original-admin first-run setup

**File:** `planning/40-tracking/tasks/0148-packaged-first-run-auth-bootstrap-ux.md`

1. Build the in-app original-admin creation/unlock path for fresh installs.
2. Keep terminal bootstrap only as a clearly scoped developer/recovery path.
3. Verify generated credentials target the packaged app data directory, not the
   dev database.
4. Verify login reaches the authenticated shell from the packaged app without
   terminal use.
5. Update release docs with the macOS auth-state location.

### Step 4 — Task 0149: Frontier-grade Chat

**File:** `planning/40-tracking/tasks/0149-chat-real-agent-interaction.md`

1. Wire `ChatView` to the existing session APIs in `src/api/client.ts`.
2. Open the authenticated backend WebSocket for the active session.
3. Render backend messages, run events, plan updates, approval prompts, stop
   state, reconnect/error state, and history reload.
4. Restore or exceed the prior browser/web-app chat experience: streaming,
   history, rich messages, reconnect/error recovery, run/plan visibility,
   approval controls, and stop controls.
5. Verify a simple prompt streams assistant output and a high-risk prompt gates
   on user approval before execution.

**Status:** done 2026-04-18. Verified with an isolated live backend contract
test (`python3.11 scripts/verify_0149_chat_live.py`), `npx tsc -b --noEmit`,
`npx vitest run --exclude "scratch/**"`, backend pytest, and `npm run build`.

### Step 5 — Task 0150: Forge programming environment

**File:** `planning/40-tracking/tasks/0150-forge-ide-release-hardening.md`

1. Verify solo programming: folder picker, file tree, open/edit/save, search,
   source control, and terminal flows.
2. Wire agent-assisted programming: agent context, proposed changes, review, and
   user approval.
3. Wire autonomous programming through Chamber's pre-write build/test gate.
4. File specific follow-up tasks for any remaining Forge failures.

**Status:** done 2026-04-18. Forge now supports selected workspace roots in
the Tauri filesystem sandbox, visible file/search/source-control/save/terminal
failure states, solo editing, an authenticated in-Forge Agent panel, and
structured context for file, source-control, and observed terminal state.
Patch/write approval from Forge remains blocked until 0153 supplies the
Chamber build/test gate.

### Step 6 — Task 0151: Current workflow orchestration

**File:** `planning/40-tracking/tasks/0151-current-agentic-workflow-orchestration.md`

1. Verify solo workflow authoring: create, edit, save, publish, execute, stop,
   approve, and audit.
2. Wire agent-assisted workflow making through the ALOS agent runtime.
3. Wire autonomous workflow orchestration with approval, observability, and
   audit boundaries.

**Status:** done 2026-04-18. Current now uses the authenticated ALOS sidecar
at `/api/current/*`, supports async execution/cancel/resume semantics, keeps
approval/audit records persisted, exposes an in-Current Agent tab for
workflow-design assistance, and requires proposed graph JSON to be reviewed,
validated, and manually applied by the user.
4. Verify `invoke_agent` steps execute through the real runtime and record
   events.

### Step 7 — Task 0152: Atlas dependency intelligence

**File:** `planning/40-tracking/tasks/0152-atlas-visual-dependency-intelligence.md`

1. Index/register this repository through Atlas.
2. Render a visual interactive file/dependency map.
3. Support dependency consequence and concept-search queries.
4. Expose Atlas mapping to agents as structured context/tools.
5. Document GitNexus parity gaps and proprietary Atlas upgrades.

### Step 8 — Task 0153: Chamber pre-write gate

**File:** `planning/40-tracking/tasks/0153-chamber-prewrite-build-test-gate.md`

1. Stage agent-proposed writes inside Chamber before workspace mutation.
2. Run required build/test commands for the affected task area.
3. Block writes by default when the Chamber gate fails.
4. Record pass/fail/override evidence.
5. Integrate this gate with Forge and Current autonomous modes.

### Step 9 — Task 0154: Robust Settings

**File:** `planning/40-tracking/tasks/0154-robust-settings-interface.md`

1. Build provider setup/edit/validate/clear flows.
2. Add original-admin setup/recovery controls.
3. Add runtime/workspace/module settings and diagnostics.
4. Add safety/approval settings for agents and Chamber gates.
5. Verify normal setup and operation do not require terminal knowledge.

### Step 10 — Task 0146: DMG packaging

**File:** `planning/40-tracking/tasks/0146-dmg-bundle-failure.md`

1. Run the release packaging path after higher-risk product/runtime blockers are
   addressed.
2. Fix the DMG-generation failure without regressing `.app` generation.
3. Verify the DMG installs/launches the same packaged app that passed auth,
   Chat, and Forge checks.

### Step 11 — Task 0143: End-to-end Tauri smoke test

**File:** `planning/40-tracking/tasks/0143-end-to-end-smoke-test.md`

1. `rm -rf ~/.alos` (exercises the setup wizard).
2. `npm run tauri dev`.
3. Walk the state machine:
   - Preflight OK → backend spawns.
   - Backend online → setup wizard → auth.
   - Auth complete → `RootShell` mounts, activity bar renders.
   - Click each module icon (Chat, Forge, Current, Atlas, QA-SIR).
     Each view mounts without console errors.
   - Open the Forge terminal. Echo keystrokes. Resize. Quit.
   - Quit via tray "Quit". Verify Python sidecar exits within 5s.
4. Capture a screenshot at every transition. Attach to PR.
5. Tail `~/Library/Logs/…/ALOS.log` (macOS) or platform equivalent.
   Zero Rust panics. Zero uncaught console errors.
6. Verify no orphaned child procs: `ps aux | grep alos` after quit.
7. If you hit a bug: **do not patch inline.** File a new task (0144+),
   note the bug in 0143's status update, and decide with the user
   whether 0143 is a hard block or can be accepted-with-known-issues.
8. Flip frontmatter and board row on success.

### Step 12 — Task 0147: Production readiness gate

**File:** `planning/40-tracking/tasks/0147-production-readiness-gate.md`

1. Read [`RELEASE-READINESS.md`](RELEASE-READINESS.md) end to end.
2. Verify every gate: build/test, packaging, end-to-end product flows,
   integration bridges, dependency intelligence, rebrand honesty, and docs.
3. Produce a dependency and impact map for release-critical flows using Atlas,
   local CLI output, filesystem audit evidence, or GitNexus MCP resources when
   they are available.
4. File a task for every failed gate. Do not patch inline.
5. Write a final readiness report with one conclusion:
   `release_candidate`, `integration_candidate`, or `active_buildout`.
6. Only mark v0.2 as a release candidate if all gates pass or the user
   explicitly approves and records an exception.

---

## After v0.2 (forward-looking)

Once 0152 through 0154 are done, 0143 and 0146 are green, and 0147 concludes
`release_candidate`, we're at the v0.2 candidate build. Everything beyond that
is v0.3 scope — do **not** move any of the clarified v0.2 product gates into
v0.3 just to make the date easier.

Known v0.3 follow-ups (not yet filed as tasks):

- **MUI → Tailwind-native design system** — MUI is vendored so that
  Forge + Current render today, but the shell is Tailwind. Unify.
- **Playwright / spectron automated smoke harness** — replaces the
  manual 0143 run with CI coverage.
- **Per-module implementation deepening beyond the v0.2 gates** — 0010, 0030,
  0050 were vendor-inventory-only, but the release-critical Chat, Forge,
  Current, Atlas, Chamber, and Settings work is now v0.2 scope under 0149
  through 0154; 0149 through 0151 are done, and the remaining 0152 through 0154
  gates must still be closed. Deeper v0.3 work must not replace those gates.
- **LSP supervisor extensions (beyond 0060–0063)** — see
  `planning/20-modules/_future/` for sketches.
- **MCP / agent bridge work (0090–0099 range reserved)** — not
  started; scope to be defined.

File each as its own `NNNN-slug.md` task under
`planning/40-tracking/tasks/` when its scope is firmed up. Don't
add rows to `board.md` without a backing task file.

---

## Ground rules for anyone picking up work

1. **Read the task file first.** Frontmatter + Scope + Acceptance
   criteria. No exceptions.
2. **Claim the task by flipping `assigned_to: <yourname>` and moving
   the board row to "In Progress"** before the first edit. This
   prevents two agents stomping on the same task.
3. **Don't expand scope.** If you discover adjacent breakage, file a
   new task. The audit from 0140 exists precisely because the
   previous agent mixed scopes and no one could tell what was fixed.
4. **Run the verification commands listed in the task file** before
   flipping `status: done`. Paste the outputs into the task's
   "Status updates" section so the next reviewer has evidence.
5. **Update `board.md` atomically with the task file state.** If one
   moves and the other doesn't, the tracking state is broken.
6. **Respect the dependency DAG.** If `blocked_by` lists an ID, do
   not start work until that ID is `done`. If you think the blocker
   is wrong, discuss it — don't just ignore it.
7. **Commit messages should reference the task ID.** Example:
   `0141: install @mui/material@^6 + monaco/xterm for vendored modules`.
8. **Never delete a vendored file** outside a dedicated "remove
   vendor X" task. Vendored code is frozen by policy until
   deliberately replaced.

---

## Quick-reference commands

```bash
# Project root
cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp"

# Rust core health
cd src-tauri && cargo check && cargo fmt --check && cargo test

# Python backend health
pytest backend/tests/

# Frontend type-check (shell-only errors, ignore vendored)
npx tsc -b --noEmit 2>&1 | grep -v '^modules/' | grep -E 'error TS'

# Full build
npm run build

# Dev run (the actual smoke test)
npm run tauri dev
```

---

## Status at time of writing

- ✅ 0001–0007, 0008, 0009, 0010, 0011, 0012, 0030, 0031, 0032, 0033,
  0039, 0050, 0051, 0060–0063, 0070, 0071, 0072, 0100, 0120 — **done**.
- ✅ 0140 (Post-Antigravity remediation) — **done** 2026-04-17.
- ✅ 0141 (Install vendored module deps) — **done** 2026-04-17.
- ✅ 0142 (verbatimModuleSyntax + implicit-any cleanup) — **done** 2026-04-17.
- ✅ 0144 (release-bundle dry run) — **done** 2026-04-17, produced `.app`,
  surfaced 0145 + 0146.
- ✅ 0145 — **done** 2026-04-18 (packaged `.app` launches bundled backend and
  WebView reaches health/setup gates).
- ✅ 0148 — **done** 2026-04-18 (original-admin first-run setup without
  terminal bootstrap).
- ✅ 0149 — **done** 2026-04-18 (frontier-grade authenticated Chat).
- ✅ 0150 — **done** 2026-04-18 (Forge solo/assisted/autonomous programming,
  with patch/write application held for 0153's Chamber gate).
- ✅ 0151 — **done** 2026-04-18 (Current solo/assisted/autonomous workflow
  orchestration).
- ✅ 0157 — **done** 2026-04-19 (frozen backend now bundles and discovers
  module routers so packaged Current/Atlas/Chamber APIs can mount after the
  next backend rebuild/restart).
- 🔜 0152 — **ready** (Atlas visual dependency intelligence for users and
  agents).
- 🔜 0153 — **ready** (Chamber pre-write build/test gate).
- 🔜 0154 — **ready** (robust Settings).
- 🔜 0146 — **ready** (DMG packaging — required before release-candidate status).
- 🔜 0143 — **ready** only after 0152 through 0154 have been implemented
  (manual smoke walkthrough in `tauri dev`).
- ⛔ 0147 — **blocked by 0143 + 0146 + 0152-0154** (full production readiness
  gate — final release decision).
- 🚫 Nothing in review.

When this document's "TL;DR" table is all-done and 0147 says
`release_candidate`, this file becomes a historical artifact. At that
point open a v0.3 equivalent under the same name and archive this one.
