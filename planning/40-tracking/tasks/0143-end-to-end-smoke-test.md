---
id: 0143
title: End-to-end Tauri smoke test (launch → auth → switch modules → quit)
area: core
status: blocked
assigned_to: null
created: 2026-04-17
updated: 2026-04-18
effort: s
blocks: []
blocked_by: [0152, 0153, 0154]
related_rfc: null
pr: null
---

# 0143 — End-to-end Tauri smoke test

## Context

After 0140 (remediation), 0141 (deps), and 0142 (type-clean), the project could
launch and exercise the shell state machine. That is no longer enough for v0.2.
This smoke test is blocked until the clarified product gates pass: original
admin setup, frontier-grade Chat, complete Forge, complete Current, visual and
agent-usable Atlas, Chamber pre-write build/test gating, and robust Settings.

## Scope

**In scope:**
- `npm run tauri dev` boots the app.
- State-machine transitions exercised in order:
  1. Preflight OK → backend spawns.
  2. Backend online → setup wizard (fresh install) or straight to auth.
  3. Auth complete → `RootShell` mounts, activity bar renders.
  4. Click each module icon; each view mounts without console errors.
  5. Open terminal (Forge view) → keystrokes echo, resize works, quit clean.
  6. Quit via tray "Quit" — Python sidecar exits within 5s.
- Screenshot captured at each state transition and attached to the PR.

**Out of scope:**
- Automated Playwright / spectron test harness (future task).
- Feature validation beyond "the surface mounts and doesn't crash."

## Files to touch

None expected. If any bug is found, it must be filed as a new task
(0144+) rather than patched inline.

## Acceptance criteria

- [ ] Manual smoke run documented in the PR description with a
      chronological narrative.
- [ ] Zero uncaught console errors during the happy-path run.
- [ ] Zero Rust panics in `~/Library/Logs/…/ALOS.log` (macOS) or
      equivalent on Linux/Windows.
- [ ] Screenshots of: splash, setup wizard (if shown), login, activity bar
      with each module highlighted, terminal session, tray menu.
- [ ] The app quits cleanly; `ps aux | grep alos` after quit returns no
      child processes.

## Implementation notes

- Run from a fresh `~/.alos/` directory to exercise the setup wizard.
- If a module fails to mount, file the bug and move on — do not fix it
  inside this task.

## Verification commands

```bash
rm -rf ~/.alos
npm run tauri dev
# manual; see acceptance criteria above
```

## Status updates

- 2026-04-17 (claude): created. Final gate before v0.2 candidate build.
- 2026-04-18 (codex): moved to blocked. Smoke testing is not useful until
  0150 through 0154 establish the remaining real product capabilities that v0.2 must
  ship.
- 2026-04-18 (codex): 0150 is done. Smoke testing remains blocked by 0151
  through 0154.
- 2026-04-18 (codex): 0151 is done. Smoke testing remains blocked by 0152
  through 0154.
