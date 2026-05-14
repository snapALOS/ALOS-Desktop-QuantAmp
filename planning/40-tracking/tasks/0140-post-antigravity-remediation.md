---
id: 0140
title: Post-Antigravity remediation — restore canonical shell, harden core, cleanup
area: core
status: done
assigned_to: claude
created: 2026-04-17
updated: 2026-04-17
effort: l
blocks: []
blocked_by: []
related_rfc: null
pr: null
---

# 0140 — Post-Antigravity remediation

## Context

An external "Antigravity" agent produced a large, partially-correct patchset inside
`ALOS + QA-SIR/ALOS-Desktop + QuantAmp/`. A follow-up Opus 4.6 agent fixed most of
the compile-breaking regressions and did the Forge fold-in integration, but left
behind a cluster of high-severity issues identified in my 2026-04-17 audit:

- `App.tsx` violated Rules of Hooks (conditional hook after early return) — crash
  on first render.
- `RootShell.tsx` did not own registry load / activeId validation / Tauri event
  bridge startup as RFC-0001 requires.
- `ModuleShell.tsx` carried an inline `Record<moduleId, Component>` instead of
  dispatching through the `defaultRenderFor()` extension point.
- Tauri event listener in `App.tsx` could double-attach on re-mount (no
  idempotence, no payload validation).
- `terminalCreate()` frontend signature passed no arguments; Rust
  `core_terminal_create(id: String, …)` required one → every terminal session
  failed on open.
- `terminal.rs` emitted events with `.unwrap()` (panic when the window
  unmounted) and never removed exited sessions from state.
- `fs_ops.rs::validate_path` used a naive `string.contains("..")` guard — did
  not canonicalize, did not clamp to a workspace root, did not follow symlinks.
- `core_fs_run_git` accepted arbitrary argv, so `git config --global
  credential.helper …` was reachable from the frontend.
- `lib.rs::generate_handler!` subsystem grouping would be destroyed by
  `rustfmt` on any format pass.
- `modules_ipc.rs` documentation was a 20-line stub — missing the
  `createModuleInvoke` TS pattern and the add-a-command checklist.
- `supervisor.py` silently upgraded routing risk to `"high"` when QA-SIR
  priority > 0.8, with no log entry — untraceable in postmortems.
- Stray `modules/hello/` demo and `modules/current/contracts/nodes/__pycache__/`
  checked into the tree.
- `modules/forge/MODULE.toml` had `[contracts]` commented out with no stub
  files backing it.
- `board.md` had two rows for task 0008 and a stale `Last updated` date.
- Three files in `src/shell/modules/` used `'../../modules/…'` relative
  imports that resolved to the non-existent `src/modules/` (should be `../../../`).
- `modules/current/frontend/src/components/workflow-canvas/WorkflowCanvas.tsx`
  was missing the line `function ConfigInput({` — the first parameter line had
  been truncated, breaking `tsc` entirely.

This task consolidates every fix for those issues under one ID. Individual
sub-items are tracked in the "Files to touch" + "Acceptance criteria"
checklists below, not as separate task files.

## Scope

**In scope:**
- Restore the canonical shell architecture (App.tsx → RootShell → ModuleShell
  → defaultRenderFor) per RFC-0001.
- Extract the Tauri event bridge into `src/shell/tauri-bridge.ts` with
  idempotent startup, payload validation, and a `forwardToBackend()` outbound
  helper.
- Fix every concrete Rust safety hole in `terminal.rs` and `fs_ops.rs`.
- Preserve the grouped `generate_handler!` layout across `cargo fmt`.
- Complete the `modules_ipc.rs` documentation (Rust + frontend patterns).
- Make the QA-SIR priority → risk escalation explicit and logged.
- Create the Forge `contracts/{events,commands}.ts` stubs and uncomment
  `[contracts]` in `modules/forge/MODULE.toml`.
- Delete `modules/hello/` and checked-in `__pycache__/`.
- Dedup `board.md` row 0008 and bump `Last updated`.
- Fix the three broken relative imports and the truncated `ConfigInput`
  signature.

**Out of scope:**
- Installing missing frontend dependencies (MUI, Monaco, xterm) for the
  vendored module frontends — tracked separately under 0141.
- `verbatimModuleSyntax` type-only-import cleanup in vendored module code —
  tracked under 0142.
- Any new feature work. This is strictly a remediation pass.

## Files to touch

Shell architecture:
- `src/App.tsx` — clean state-machine; stops at auth.
- `src/shell/RootShell.tsx` — owns registry load + activeId validation +
  event-bridge lifecycle.
- `src/shell/ModuleShell.tsx` — header + `{defaultRenderFor(activeId)}`.
- (NEW) `src/shell/module-views.tsx` — `defaultRenderFor()` dispatcher.
- (NEW) `src/shell/tauri-bridge.ts` — idempotent `listen('alos-event')` with
  `isAlosEvent()` guard + `forwardToBackend()`.
- `src/contracts/tauri-commands.ts` — `terminalCreate(id: string)` fixed to
  match Rust.

Rust hardening:
- `src-tauri/src/terminal.rs` — no `.unwrap()` on emit; cleanup session on
  PTY exit.
- `src-tauri/src/fs_ops.rs` — `validate_path` canonicalizes and clamps to
  workspace root; `core_fs_run_git` gated by `GIT_ALLOWED_SUBCOMMANDS` +
  flag filters.
- `src-tauri/src/lib.rs` — `#[rustfmt::skip]` on `pub fn run()`.
- `src-tauri/src/modules_ipc.rs` — full documentation.

Python:
- `backend/src/graph/supervisor.py` — explicit logged risk escalation.

Modules / hygiene:
- `modules/forge/MODULE.toml` — uncomment `[contracts]`.
- (NEW) `modules/forge/contracts/events.ts` (stub).
- (NEW) `modules/forge/contracts/commands.ts` (stub).
- DELETED `modules/hello/`.
- DELETED `modules/current/contracts/nodes/__pycache__/`.

Planning:
- `planning/40-tracking/board.md` — dedup 0008, bump date.

Pre-existing vendored bugs surfaced while verifying:
- `src/shell/modules/ForgeView.tsx` — `'../../modules/'` → `'../../../modules/'`.
- `src/shell/modules/ModuleViews.tsx` — same fix plus `useEffect` removed
  (unused), bare `>` characters replaced with `&gt;` to unblock JSX parse.
- `modules/current/frontend/src/components/workflow-canvas/WorkflowCanvas.tsx`
  — restored missing `function ConfigInput({` header.

## Acceptance criteria

- [x] `App.tsx` contains no conditional-hook-after-early-return.
- [x] `src/shell/tauri-bridge.ts` exists with `isAlosEvent()`,
      `startTauriEventBridge()` (idempotent), `forwardToBackend()`.
- [x] `ModuleShell.tsx` renders `{defaultRenderFor(activeId)}` and nothing
      else in its main slot.
- [x] `src/contracts/tauri-commands.ts::terminalCreate(id)` passes the `id`
      kwarg to `core_terminal_create`.
- [x] `terminal.rs` has zero `.unwrap()` on `.emit(...)`; sessions are
      removed from state on PTY exit.
- [x] `fs_ops.rs::validate_path` canonicalizes and rejects any resolved path
      that doesn't `starts_with(workspace_root)`.
- [x] `fs_ops.rs::validate_git_args` rejects `-c`, `-C`, `--exec-path`,
      `config --global`, `remote add/remove/set-url/…`, and any subcommand
      not in `GIT_ALLOWED_SUBCOMMANDS`.
- [x] `lib.rs::run` carries `#[rustfmt::skip]` and `cargo fmt --check`
      passes.
- [x] `modules_ipc.rs` documents both the Rust side and the
      `createModuleInvoke('<id>')('<verb>', args)` TS pattern, plus the
      add-a-command checklist.
- [x] `supervisor.py` logs `QA-SIR RISK ESCALATION` with previous risk,
      priority, and signature when it upgrades to `"high"`.
- [x] `modules/forge/MODULE.toml` has `[contracts]` active with paths that
      resolve on disk.
- [x] `find modules -type d -name hello | wc -l` → `0`.
- [x] `find modules -type d -name __pycache__ | wc -l` → `0`.
- [x] `board.md` has exactly one `0008` row and `Last updated: 2026-04-17`.
- [x] `cd src-tauri && cargo check` clean.
- [x] `cd src-tauri && cargo fmt --check` clean.
- [x] `cd src-tauri && cargo test` → all tests passing.
- [x] `pytest backend/tests/` → 28/28 passing.
- [x] `npx tsc -b --noEmit` has **zero** errors in files owned by the shell
      (`src/` tree); remaining errors are all inside vendored module
      frontends and are tracked under 0141 + 0142.

## Implementation notes

- Frontend type-check surfaces a large pile of pre-existing vendored errors
  (missing `@mui/material`, `verbatimModuleSyntax` violations, implicit
  `any`). Do NOT chase those here; they are separate tasks. This task's
  scope is strictly shell-layer code plus the three vendored files that
  were mechanically broken.
- `createModuleInvoke` is the only sanctioned route for module → Rust
  calls. Do not reintroduce `@tauri-apps/api/core` imports in module code.
- 2026-04-18 update: 0150 replaced the CWD-only filesystem root with a
  Tauri-managed selected workspace root, so Forge folder selection now drives
  the `core_fs_*` sandbox.

## Verification commands

```bash
# Rust
cd src-tauri && cargo check && cargo fmt --check && cargo test

# Python
cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp" && pytest backend/tests/

# Frontend shell (expect errors only under modules/**)
cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp" && npx tsc -b --noEmit 2>&1 | grep -v '^modules/' | grep -E 'error TS'

# Hygiene
find modules -type d -name hello | wc -l        # expect 0
find modules -type d -name __pycache__ | wc -l  # expect 0

# Security surface
grep -n 'GIT_ALLOWED_SUBCOMMANDS' src-tauri/src/fs_ops.rs | wc -l  # expect >=1
grep -n 'canonicalize' src-tauri/src/fs_ops.rs | wc -l             # expect >=1
```

## Status updates

- 2026-04-17 (claude): created retroactively after completing all fixes in
  the same session. All acceptance criteria pass. Closed `done`.
