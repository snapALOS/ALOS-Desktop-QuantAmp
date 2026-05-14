---
id: 0146
title: `bundle_dmg.sh` fails after `.app` is produced
area: core
status: ready
assigned_to: null
created: 2026-04-17
updated: 2026-04-17
effort: xs
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0146 — DMG bundling failure

## Context

Surfaced by **0144** dry run. `npm run tauri build` successfully:

1. Ran the frontend bundle.
2. Froze the Python backend via PyInstaller.
3. Compiled the Rust binary in release mode.
4. Produced `ALOS.app` at
   `src-tauri/target/release/bundle/macos/ALOS.app`.

Then failed on the DMG packaging step:

```
Bundling ALOS_0.1.0_aarch64.dmg
  Running bundle_dmg.sh
failed to bundle project error running bundle_dmg.sh:
  `failed to run /Users/.../target/release/bundle/dmg/bundle_dmg.sh`
```

The DMG is a required v0.2 distribution artifact on top of the `.app`. The
`.app` is the actual application and is expected to be functional once 0145 is
fixed, but v0.2 cannot be called a release candidate until this task produces a
valid DMG.

## Scope

**In scope:**
- Diagnose why `bundle_dmg.sh` failed.
- Fix so the DMG is produced at
  `src-tauri/target/release/bundle/dmg/ALOS_<ver>_<arch>.dmg`.

**Out of scope:**
- Codesigning / notarization of the DMG.
- Cross-platform installers (Linux `.deb`/`.AppImage`, Windows `.msi`).

## Likely root causes (to verify)

- `bundle_dmg.sh` calls `create-dmg` — may not be installed or may
  require specific argv that Tauri's invocation didn't provide.
- Could also be `SetFile` (ancient Xcode CLT utility, removed in
  recent CLT versions) or `osascript` Automation permissions not
  granted to the terminal running the build.
- Check `create-dmg` install: `brew install create-dmg` is the
  typical fix on macOS.

## Files likely to touch

- None expected — this is tooling/environment rather than code. If
  Tauri's DMG generator config needs adjustment, it lives under
  `src-tauri/tauri.conf.json` → `bundle` → `macOS`.

## Acceptance criteria

- [x] `npm run tauri build` produces both
      `src-tauri/target/release/bundle/macos/ALOS.app` **and**
      `src-tauri/target/release/bundle/dmg/ALOS_*.dmg` without errors.
- [x] Mounting the DMG opens a Finder window with `ALOS.app` and an
      `Applications` shortcut.
- [ ] Launching `ALOS.app` from the mounted DMG works (relies on
      0145 being fixed).

## Verification commands

```bash
cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp"
npm run tauri build 2>&1 | grep -E 'Bundling|Error'
ls -lh src-tauri/target/release/bundle/dmg/*.dmg
hdiutil attach src-tauri/target/release/bundle/dmg/ALOS_*.dmg
ls /Volumes/ALOS/
hdiutil detach /Volumes/ALOS/
```

## Implementation notes

- If `create-dmg` is missing: `brew install create-dmg`.
- If automation permissions are the issue, it's a per-machine user
  prompt; document the step in `planning/00-overview/` once resolved.
- Tauri 2.x DMG generation is known-finicky on Apple Silicon without
  Xcode CLT fully installed (`xcode-select --install`). Confirm that
  path too.

## Status updates

- 2026-04-17 (claude): created from 0144 dry-run findings. Lower sequencing
  priority than 0145 because product/runtime startup is higher risk, but DMG
  generation is still required before v0.2 can be marked release-candidate.
- 2026-04-18 (codex): during 0145 rebuilds, PyInstaller completed
  successfully but emitted noisy optional dependency warnings
  (`chromadb.server.fastapi` OpenTelemetry instrumentation, TensorBoard,
  CUDA/Linux libraries, database driver extras). These were not the observed
  app-start failure, but 0146 should preserve or triage the packaging warning
  log so real DMG/package errors are easy to distinguish.
- 2026-04-18 (codex): `npm run tauri build` initially failed because
  PyInstaller's spec execution did not define `__file__`; fixed the spec to use
  `SPECPATH`. Re-ran packaging successfully. Produced
  `src-tauri/target/release/bundle/macos/ALOS.app` and
  `src-tauri/target/release/bundle/dmg/ALOS_0.1.0_aarch64.dmg`. Mounted the DMG
  read-only and verified it contains `ALOS.app` plus the `Applications`
  symlink, then detached it. Did not launch the app from the mounted DMG during
  this pass to avoid starting the packaged backend on the user's machine.
