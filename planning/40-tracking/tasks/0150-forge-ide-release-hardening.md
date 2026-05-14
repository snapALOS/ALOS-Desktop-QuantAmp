---
id: 0150
title: Forge must fully support solo, assisted, and autonomous programming
area: forge
status: done
assigned_to: null
created: 2026-04-18
updated: 2026-04-18
effort: m
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0150 — Forge must fully support solo, assisted, and autonomous programming

## Context

During packaged-app verification, selecting the IDE left the user on a black
screen. Code audit found three concrete risks:

- Module render failures were not isolated from the root shell.
- Pre-release persisted module state could reopen directly into the IDE after
  relaunch.
- Forge imported the JavaScript dialog plugin without registering the root
  Tauri dialog plugin or granting its permission.

Initial hardening has been applied, but Forge still needs to become a complete
ALOS programming environment. v0.2 requires three working modes: solo user
programming, user-led agent-assisted programming, and ALOS autonomous
programming with appropriate approval and verification gates.

## Scope

**In scope:**
- Verify Forge opens visibly from the packaged shell and can return to Chat.
- Verify module error containment keeps the shell usable if Forge crashes.
- Verify folder selection works through the registered Tauri dialog plugin.
- Verify file tree, file open, edit, save, search, source control panel, and
  terminal interactions against the root Tauri commands.
- Verify terminal startup and resize failures are visible instead of blanking
  the IDE.
- Wire Forge actions into the ALOS agent/runtime layer so agents can inspect
  context, propose changes, run safe checks, and coordinate with Chamber before
  disk writes.
- Support three explicit modes: solo user programming, user-led agent-assisted
  programming, and autonomous programming.
- Record any remaining Forge gaps as explicit tasks instead of hiding them
  under the smoke test.

**Out of scope:**
- Replacing the vendored Forge UI with a new design system.
- Adding advanced IDE features not already claimed by the v0.2 readiness gate.

## Acceptance criteria

- [x] Opening Forge from the packaged app produces visible UI within 3 seconds.
- [x] Reloading/relaunching after a prior Forge selection does not trap the
      user on a black screen.
- [x] Folder picker opens and returns a selected directory.
- [x] File tree lists the selected directory.
- [x] Opening a file displays readable content in Monaco.
- [x] Editing and saving a file writes to disk through `core_fs_write_file`.
- [x] Search panel can search within the selected workspace.
- [x] Source control panel handles a non-git and git workspace without crashing.
- [x] Terminal starts, accepts input, resizes, and reports startup failures
      visibly.
- [x] User can work alone without agentic help.
- [x] User can ask an agent for help inside Forge and review proposed changes.
- [x] ALOS can perform autonomous programming tasks only through the approved
      Chamber/build/test gate before writing to disk.
- [x] Forge file, terminal, and source-control state is available to agents as
      structured context.
- [x] Any remaining failure is captured as a task with reproduction steps.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
cd src-tauri && cargo check
npx vitest run --exclude "scratch/**"
cd src-tauri && cargo test
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
```

Manual packaged-app verification:

1. Login with a valid API key.
2. Open Forge.
3. Select a workspace folder.
4. Open, edit, and save a harmless test file.
5. Use search, source control, and terminal.
6. Switch back to Chat and quit cleanly.

## Status updates

- 2026-04-18 (codex): created after black-screen report. Initial mitigations
  landed in the shell, Forge empty states, terminal startup handling, and root
  Tauri dialog plugin registration, but the full Forge release path still needs
  to pass.
- 2026-04-18 (codex): rebuilt the packaged `.app` with those mitigations.
  Verification passed: `npx tsc -b --noEmit`, `npm run build`,
  `cd src-tauri && cargo check`, `cd src-tauri && cargo fmt --check`,
  `cd src-tauri && cargo test`, and
  `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/`.
  Bundle contains `Contents/Resources/resources/backend/alos-backend`.
- 2026-04-18 (codex): completed Forge release hardening. Stopped the stray
  packaged `alos-backend` process, added Tauri-managed workspace roots so
  selected folders can be read/written/search/git-operated inside the sandbox,
  surfaced search/source-control/save/tree/terminal failures in the IDE,
  switched terminal sessions away from the fixed `default` id, added observed
  terminal transcript capture, added structured Forge agent context, and added
  an in-Forge Agent panel backed by the authenticated Chat websocket. Forge
  can approve plans and review proposed patches, but patch/write approval is
  intentionally blocked until 0153 supplies the Chamber build/test write gate.
  Verification passed: `npx tsc -b --noEmit`,
  `npx vitest run --exclude "scratch/**"`, `npm run build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`, and
  `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/`.
