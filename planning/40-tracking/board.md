# Board — v0.2

**Last updated:** 2026-04-19

Keep this file ordered: newest-backlog at top of Backlog; oldest-done at bottom of Done. Always update atomically with task file state changes.

---

## Backlog

Tasks that exist but aren't ready to pick up (missing scope, dependencies, or decisions).

| ID | Title | Area | Blocked by |
|---|---|---|---|

*(empty — initial tasks are all Ready or explicit follow-ups)*

---

## Ready

Pickable. Any agent may claim. Acceptance criteria are final.

See `PATH-TO-COMPLETION.md` for the full sequence.

| ID | Title | Area | Effort |
|---|---|---|---|
| 0154 | Users need a robust settings interface | core | m |
| 0153 | Chamber must gate agent writes through build and test completion | chamber | l |
| 0152 | Atlas must provide visual dependency intelligence for users and agents | atlas | l |
| 0146 | `bundle_dmg.sh` fails after `.app` is produced | core | xs |

---

## In Progress

One row per agent currently working. Keep this short — if it grows past ~5 rows something's wrong.

| ID | Title | Area | Owner |
|---|---|---|---|

*(empty)*

---

## Review

PR open, waiting for merge.

| ID | Title | Area | PR |
|---|---|---|---|

*(empty)*

---

## Blocked

Has blockers that need resolution before it can move.

| ID | Title | Area | Blocked by |
|---|---|---|---|
| 0147 | Full v0.2 production readiness gate | core | 0143, 0146, 0152, 0153, 0154 |
| 0143 | End-to-end Tauri smoke test (launch → auth → switch modules → quit) | core | 0152, 0153, 0154 |

---

## Done

Closed tasks, newest first.

| ID | Title | Area | Date |
|---|---|---|---|
| 0158 | Scout-driven systematic QA audit harness | core | 2026-04-19 |
| 0157 | Packaged backend must mount module routers | core | 2026-04-19 |
| 0151 | Current must fully support solo, assisted, and autonomous workflow orchestration | current | 2026-04-18 |
| 0150 | Forge must fully support solo, assisted, and autonomous programming | forge | 2026-04-18 |
| 0149 | Chat must be a frontier-grade authenticated agent experience | core | 2026-04-18 |
| 0148 | Original-admin first-run setup must not require terminal bootstrap | core | 2026-04-18 |
| 0145 | Packaged `.app` does not spawn the frozen Python sidecar | core | 2026-04-18 |
| 0144 | Tauri release-bundle dry run (`npm run tauri build`) | core | 2026-04-17 |
| 0142 | Fix verbatimModuleSyntax + implicit-any in vendored module code | core | 2026-04-17 |
| 0141 | Install frontend deps required by vendored module code | core | 2026-04-17 |
| 0140 | Post-Antigravity remediation — shell restore + Rust hardening | core | 2026-04-17 |
| 0072 | Agent tool `execute_system_bash` PTY upgrade | backend | 2026-04-16 |
| 0071 | ALOSCurrent `shell` node integration | current | 2026-04-16 |
| 0070 | Observed PTY Runner implementation | core | 2026-04-16 |
| 0063 | IPC Contract Mirror (ts) | core | 2026-04-16 |
| 0062 | LSP JSON-RPC bridge & Tauri commands | core | 2026-04-16 |
| 0061 | LSP Registry (TOML) implementation | core | 2026-04-16 |
| 0060 | Rust LSP Supervisor scaffolding | core | 2026-04-16 |
| 0039 | Agent supervisor invocation bridge | agents | 2026-04-16 |
| 0033 | `invoke_agent` runtime executor | current | 2026-04-16 |
| 0032 | `invoke_agent` node contract | current | 2026-04-16 |
| 0100 | Final Polish & Verification | core | 2026-04-16 |
| 0012 | Forge Terminal Rewire | forge | 2026-04-16 |
| 0009 | Core PTY Backend (Rust) | core | 2026-04-16 |
| 0008 | Backend Port Wiring (Discovery Stability) | core | 2026-04-16 |
| 0051 | Atlas Rebranding & Scaffolding | atlas | 2026-04-16 |
| 0031 | Current Rebranding & Scaffolding | current | 2026-04-16 |
| 0011 | Forge Rebranding & Scaffolding | forge | 2026-04-16 |
| 0007 | Root shell routing wiring | core | 2026-04-16 |
| 0050 | Atlas — vendor source and produce INVENTORY.md | atlas | 2026-04-16 |
| 0030 | Current — vendor source and produce INVENTORY.md | current | 2026-04-16 |
| 0010 | Forge — vendor source and produce INVENTORY.md | forge | 2026-04-16 |
| 0006 | Tauri command registration pattern | core | 2026-04-16 |
| 0005 | Preserve Chat as built-in | core | 2026-04-16 |
| 0004 | Add MODULE.toml loader | core | 2026-04-16 |
| 0003 | Define event bus contract and bridge | core | 2026-04-16 |
| 0002 | Build module registry + activity bar skeleton | core | 2026-04-16 |
| 0001 | Create `modules/` directory and workspace manifests | core | 2026-04-16 |
| 0120 | Write CONVENTIONS.md (+ AGENTS.md) | docs | 2026-04-15 |
