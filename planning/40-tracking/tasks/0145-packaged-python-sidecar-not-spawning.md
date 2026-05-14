---
id: 0145
title: Packaged `.app` does not spawn the frozen Python sidecar
area: core
status: done
assigned_to: codex
created: 2026-04-17
updated: 2026-04-18
effort: s
blocks: []
blocked_by: []
related_rfc: null
pr: null
---

# 0145 — Packaged `.app` does not spawn the frozen Python sidecar

## Context

Surfaced by **0144** dry run. After `npm run tauri build` produced
`src-tauri/target/release/bundle/macos/ALOS.app` (1.3 GB, with
`Contents/Resources/resources/backend/alos-backend` correctly staged
by PyInstaller), launching the `.app`:

- The Tauri Rust process stays alive at steady state (PID observed,
  quits cleanly via `osascript -e 'quit app "ALOS"'`).
- `~/Library/Logs/com.alos.desktop/ALOS.log` is created but stays
  **0 bytes** for the duration of the run.
- **No `alos-backend` process is spawned** (`pgrep -fl alos-backend`
  returns nothing across a 20-second live run).

Dev-mode (`tauri dev`) is expected to still spawn the sidecar via the
dev-time Python interpreter path. Release-mode should prefer the
frozen binary. Something in that "prefer frozen, fall back to
interpreter" chain in `src-tauri/src/backend.rs` is broken for the
packaged context.

## Scope

**In scope:**
- Diagnose why `alos-backend` isn't invoked from the bundled `.app`.
- Fix so launching the `.app` spawns the frozen binary at
  `Contents/Resources/resources/backend/alos-backend`.
- Verify preflight reaches `backend online` state in the log and
  the sidecar process shows up under `ps aux`.

**Out of scope:**
- Cross-platform (Windows/Linux sidecar path) — can come in a
  followup if the macOS fix doesn't translate.
- Codesigning — the `.app` is adhoc-signed; that's fine for a dry
  run.

## Likely root causes (to verify)

1. **Path resolution**: `backend.rs` probably builds the sidecar path
   relative to the running binary's CWD or to a hardcoded dev-mode
   path. In the packaged bundle the binary runs from
   `ALOS.app/Contents/MacOS/` and the sidecar lives at
   `ALOS.app/Contents/Resources/resources/backend/alos-backend`. Need
   to use `std::env::current_exe()` + `../Resources/resources/backend/alos-backend`
   or Tauri's `PathResolver` API.
2. **Missing log init**: `fern`/`tauri-plugin-log` may be configured
   only in dev. If log init is conditional on a flag that's false in
   release, errors from the sidecar spawn attempt would be swallowed.
   The 0-byte log file suggests this is at least partially true.
3. **`externalBin` vs `resources` confusion**: `tauri.conf.json` uses
   `"resources": ["resources/backend/**/*"]` which copies files into
   the bundle but does NOT register the binary as a Tauri sidecar.
   A Tauri sidecar (spawnable via `Command::sidecar()`) needs
   `"externalBin"` in the bundler config. If the Rust code uses
   `Command::sidecar("alos-backend")` it will silently fail because
   Tauri's sidecar registry doesn't know about it.

## Files likely to touch

- `src-tauri/src/backend.rs` — sidecar spawn logic.
- `src-tauri/tauri.conf.json` — possibly add `"externalBin"` entry.
- `src-tauri/src/lib.rs` — if log init is release-gated.

## Acceptance criteria

- [ ] Launching `ALOS.app` from Finder produces a running
      `alos-backend` child process (`pgrep -fl alos-backend` → 1+
      lines).
- [ ] `~/Library/Logs/com.alos.desktop/ALOS.log` accumulates entries
      during launch — at minimum a "spawning backend" and "backend
      online" line.
- [ ] Shell reaches the auth screen (same gate 0144 proved
      structurally).
- [ ] Quitting the app leaves no orphan `alos-backend` process
      (`pgrep alos-backend` returns nothing after quit — 0140 already
      hardened this for the dev path, confirm it holds in release).

## Verification commands

```bash
APP="src-tauri/target/release/bundle/macos/ALOS.app"
open -a "$APP"
sleep 5
pgrep -fl alos-backend           # expect 1+ lines
cat ~/Library/Logs/com.alos.desktop/ALOS.log | head -40
osascript -e 'quit app "ALOS"'
sleep 3
pgrep alos-backend               # expect nothing
```

## Implementation notes

- Start by reading `src-tauri/src/backend.rs` top-to-bottom and
  tracing how `sidecar_path` is computed.
- The Tauri recommended pattern is
  `app.path().resolve("resources/backend/alos-backend", BaseDirectory::Resource)`
  which works in both dev and release.
- If switching to `externalBin`: rename the file to
  `alos-backend-aarch64-apple-darwin` (Tauri's triple-suffix
  requirement) and update `tauri.conf.json` accordingly. The
  `scripts/build_backend.py` stage step would need to rename the
  output too.

## Status updates

- 2026-04-17 (claude): created from 0144 dry-run findings.
- 2026-04-18 (codex): claimed for packaged sidecar startup diagnosis. Start
  by tracing `src-tauri/src/backend.rs`, bundle resource layout, and release
  logging before editing runtime code.
- 2026-04-18 (codex): fixed packaged startup. Root causes were: frozen backend
  import crashed when `public/` was missing in packaged CWD; Tauri WebView could
  reach `/api/health` but CORS blocked reading the response; configured installs
  hit `401` on `/api/setup/status` before the frontend could decide auth/setup
  routing. Verified `npm run tauri -- build --bundles app`, launched packaged
  `.app`, observed bundled `alos-backend` child process, confirmed
  `/api/health` returns `200` with `Access-Control-Allow-Origin:
  tauri://localhost`, and saw WebView logs for both `/api/health` and
  `/api/setup/status` returning `200 OK`. Backend tests now pass: `29 passed`.
