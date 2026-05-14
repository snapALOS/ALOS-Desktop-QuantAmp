---
id: 0148
title: Original-admin first-run setup must not require terminal bootstrap
area: core
status: done
assigned_to: null
created: 2026-04-18
updated: 2026-04-18
effort: s
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0148 — Original-admin first-run setup must not require terminal bootstrap

## Context

After 0145, the packaged `.app` launches, starts the frozen backend, and reaches
the intended API-key login gate. The current login copy tells the user:

```bash
python -m src.auth.bootstrap_admin
```

That command is source-tree oriented and is misleading for a packaged app. The
packaged runtime reads state from
`~/Library/Application Support/com.alos.desktop`, so running the command in the
wrong context can create a key in the dev database instead of the app database.

For v0.2, first-run auth must be a refined in-app original-admin setup flow.
The original admin should not have to run a terminal command just to get into
ALOS.

## Scope

**In scope:**
- Decide the v0.2 first-run auth bootstrap flow for packaged macOS builds.
- Build an in-app original-admin creation/unlock path for a fresh install.
- Make the UI copy and command path match the actual packaged app data
  directory.
- Keep terminal bootstrap available only as an explicit developer/recovery path,
  not as the primary admin setup.
- Verify the generated key authenticates via the packaged app login screen.

**Out of scope:**
- Full multi-user account management UX.
- Keychain migration; that can remain a follow-up if not already required by a
  separate security gate.

## Acceptance criteria

- [x] The packaged app no longer instructs users to run an ambiguous source-tree
      command.
- [x] A fresh packaged app install can create or unlock the original admin from
      inside the app.
- [x] Any generated credential targets the packaged app data directory without
      modifying the dev database by accident.
- [x] The setup/login flow reaches the authenticated shell without terminal use.
- [x] Release docs explain where packaged auth state lives on macOS.
- [x] Existing `backend/src/auth/bootstrap_admin.py` output no longer gives
      stale browser-console/localStorage instructions for the Tauri app, or the
      stale instructions are clearly scoped to legacy browser/dev usage.

## Verification commands

```bash
env ALOS_DATA_DIR=/tmp/alos-0148-review PYTHONPATH=.:backend python3.11 -c '...'
npx tsc -b --noEmit
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
```

Manual packaged-app verification: on a fresh local data directory, complete
provider setup, create the original admin from the login screen, connect with
the generated key, and confirm the authenticated shell opens without using a
terminal bootstrap command.

## Status updates

- 2026-04-18 (codex): created during 0145 verification. The runtime startup
  bug is fixed, but the packaged first-run auth experience is not release-ready.
- 2026-04-18 (codex): implemented in-app original-admin setup. Added public
  `/auth/bootstrap/status` and guarded `/auth/bootstrap/original-admin`
  endpoints, limited creation to an empty local users table, updated the login
  screen to create the first admin without terminal use, removed stale browser
  console bootstrap instructions from the script output, and made `/auth/me`
  return a full user payload from bearer-key auth. Verification passed:
  `npx tsc -b --noEmit`, `npm run build`, and
  `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/`.
- 2026-04-18 (codex): review pass tightened original-admin creation so the
  user row, API key row, and audit row are committed in one transaction. A
  focused fresh-data-dir API check confirmed `/auth/bootstrap/status`,
  `/auth/bootstrap/original-admin`, `/auth/me`, and second-bootstrap rejection.
