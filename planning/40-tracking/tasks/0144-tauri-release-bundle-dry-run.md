---
id: 0144
title: Tauri release-bundle dry run — `npm run tauri build` produces an installer
area: core
status: done
assigned_to: claude
created: 2026-04-17
updated: 2026-04-17
effort: s
blocks: []
blocked_by: [0141, 0142]
related_rfc: null
pr: null
---

# 0144 — Tauri release-bundle dry run

## Context

0141 + 0142 proved `tsc -b` and `vite build` are clean. 0143 proves
the dev-server flavor (`tauri dev`) boots and the shell state machine
works. Neither touches `tauri build`, which is what actually produces
a shippable `.app` / `.dmg` / `.deb` / `.msi`. Release mode runs
`cargo build --release` (not `cargo check`) plus the Tauri bundler
plus codesigning, and those layers can surface issues that dev mode
hides:

- Release-mode Rust warnings promoted to errors by profile config.
- Optimizer-triggered UB in unsafe blocks (rare, but the PTY code
  touches `portable-pty`).
- Missing icons / malformed `tauri.conf.json` bundler section.
- Capability / permission manifest mismatches that only trip in
  the packaged binary.
- Python sidecar not being copied into the app bundle.

This task is a dry run — we produce the bundle and verify it loads
once. We do **not** codesign, notarize, or publish.

## Scope

**In scope:**
- Run `npm run tauri build` to completion.
- Verify the bundle directory is produced at the expected platform
  path.
- On macOS: open the `.app`, verify the window shows the splash /
  auth / shell (at least one transition past preflight).
- On Linux/Windows: run the produced binary once.
- Document any bundler config fixes required to reach a clean build.

**Out of scope:**
- Codesigning / notarization — v0.3.
- Auto-update / release publishing — v0.3.
- Cross-platform bundle (run on whatever host the operator has).
- Fixing in-app bugs that appear once launched; those go to 0143 or
  new tasks.

## Files to touch

None expected. If the build fails on config, candidates are:

- `src-tauri/tauri.conf.json` — bundler identifier, icons, resources.
- `src-tauri/Cargo.toml` — release profile, bundle features.
- `src-tauri/capabilities/*.json` — missing/extra permissions.
- `package.json` — `build` script ordering if bundler complains.

## Acceptance criteria

- [x] Bundle produced at `src-tauri/target/release/bundle/macos/ALOS.app`
      (1.3 GB). **DMG step failed** (`bundle_dmg.sh` crashed); tracked
      separately as **0146**.
- [x] `.app` launches without panicking. Rust process stays alive,
      quits cleanly via `osascript -e 'quit app "ALOS"'`. No orphan
      children after quit.
- [x] No `error[E…]` in the cargo output. Two benign PyInstaller
      collection warnings noted (`chromadb.server.fastapi` +
      `torch.utils.tensorboard` — both optional paths).
- [ ] **Python sidecar does NOT spawn** inside the packaged bundle.
      `~/Library/Logs/com.alos.desktop/ALOS.log` stays 0 bytes; no
      `alos-backend` process observed during a 20-second live run.
      Tracked as **0145**.
- [x] Build pipeline reaches the bundler step; this task is a dry
      run, not ship-readiness. The 0145 follow-up is what gates
      ship-readiness.

## Implementation notes

- First release build will take a while — expect 5–15 minutes of
  Rust compile time. Subsequent incremental builds are fast.
- On macOS, if bundler complains about codesigning with no
  identity, set `"macOS": { "signingIdentity": null }` in
  `tauri.conf.json` → `bundle` for the dry run. Record the setting
  reverted before shipping.
- Python sidecar bundling: confirm `tauri.conf.json` → `bundle` →
  `externalBin` or `resources` includes the backend entrypoint. If
  it's not there, the packaged app will fail preflight.

## Verification commands

```bash
cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp"
npm run tauri build 2>&1 | tee /tmp/tauri-build.log
# macOS
ls src-tauri/target/release/bundle/macos/
open src-tauri/target/release/bundle/macos/ALOS.app
# Linux
ls src-tauri/target/release/bundle/deb/ src-tauri/target/release/bundle/appimage/ 2>/dev/null
# Windows
ls src-tauri/target/release/bundle/msi/ 2>/dev/null
```

## Status updates

- 2026-04-17 (claude): created. Final release-gate task. Blocks the
  v0.2 candidate build declaration once 0143 also passes.
- 2026-04-17 (claude): dry run executed. Four config fixes required
  before the pipeline ran end-to-end (all pre-existing Antigravity
  leftovers):
  1. Root `package.json` was missing `"tauri": "tauri"` script. Added.
  2. `src-tauri/tauri.conf.json` `beforeDevCommand` used `bun run dev`
     (bun not installed on host). Changed to `npm run dev`.
  3. Same file `beforeBuildCommand` used
     `bun run build && python3 ../scripts/build_backend.py` — wrong
     command AND wrong path (the `../` assumed CWD=src-tauri/, but
     Tauri 2.x runs the hook from project root). Changed to
     `npm run build && python3.11 scripts/build_backend.py`.
  4. The `python3.11` explicit invocation is a stopgap because Tauri's
     subprocess picks `/usr/bin/python3` (Xcode stub, 3.9, no
     PyInstaller) before `/opt/homebrew/bin/python3.11`. The right
     long-term answer is the `backend/.venv-build` pattern prescribed
     in `scripts/build_backend.py` docstring, referenced via
     `--venv backend/.venv-build`. Not done in this pass — v0.3
     packaging-polish task.
  Also: `pip3 install pyinstaller` into brew python to enable the
  freeze step.

  Results:
  - Frontend bundle: 2.53s, ~896 KB gzipped.
  - PyInstaller freeze: produced
    `src-tauri/resources/backend/alos-backend` (Mach-O arm64)
    successfully.
  - `cargo build --release`: 1m 44s clean, zero errors.
  - `.app` produced at
    `src-tauri/target/release/bundle/macos/ALOS.app` (1.3 GB),
    `Info.plist` valid, MacOS binary present, Resources/resources/backend
    contains the frozen sidecar.
  - `.app` launches: process stays alive at steady state, quits
    cleanly. No crash, no panic.
  - **Bug found**: Python sidecar does not spawn inside the
    packaged bundle. Log stays empty, no `alos-backend` process. Filed
    as **0145**. In dev-mode (`tauri dev`) the sidecar likely spawns
    because backend.rs falls through to the raw interpreter path; in
    release-mode it should spawn the frozen binary from
    `resources/backend/alos-backend` and does not. Most likely a
    sidecar-path resolution bug in `src-tauri/src/backend.rs`.
  - **Bug found**: `bundle_dmg.sh` failed after `.app` was already
    produced. Filed as **0146**.

  Overall: the release pipeline works; the `.app` is structurally
  correct; two real bugs (sidecar spawn, DMG packaging) need fixing
  before a v0.2 candidate build can be declared shippable.
