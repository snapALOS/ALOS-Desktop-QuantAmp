---
id: 0158
title: Add Scout-driven systematic QA audit harness
area: core
status: done
assigned_to: codex
created: 2026-04-19
updated: 2026-04-19
effort: m
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0158 — Add Scout-driven systematic QA audit harness

## Context

Scout now records backend logs, frontend renderer failures, event-bus activity,
and agent/runtime events. To use it effectively for v0.2 hardening, we need a
repeatable harness that drives the product surface, records each probe into
Scout, and emits a clean CSV of observed failures instead of relying on noisy
manual bug-report dumps.

## Scope

**In scope:**
- Add a script that runs authenticated API smoke checks for core, Chat, Forge,
  Current, Atlas, Chamber, Settings, and Scout.
- Record each audit step into Scout with a shared audit `run_id`.
- Write a valid CSV with quoted fields, status, severity, HTTP details, Scout
  event ids, and summarized JSON details.
- Support safe write checks for temporary project/session/workflow flows behind
  an explicit flag.
- Support optional frontend crawling through Chrome DevTools Protocol without
  adding a Playwright dependency.

**Out of scope:**
- Full native Tauri WebView automation.
- Destructive UI clicking by default.
- Replacing manual release QA or 0147 production readiness gates.

## Files Touched

- `scripts/scout_audit.mjs` — new Scout/API/UI audit harness.
- `package.json` — adds `npm run audit:scout`.
- `planning/40-tracking/tasks/0158-scout-systematic-qa-audit-harness.md` — task record.
- `planning/40-tracking/board.md` — marks task done.

## Acceptance Criteria

**All must be mechanically verifiable.**

- [x] `node --check scripts/scout_audit.mjs` exits 0.
- [x] `node scripts/scout_audit.mjs --help` prints usage with API, CSV, write-check, and frontend-crawl options.
- [x] `npm run audit:scout -- --help` works through the package script.
- [x] The script writes RFC-compliant CSV rows using CSV escaping instead of ad-hoc comma joins.
- [x] The script records audit start, step, result, and finish events into Scout when an API key is provided.
- [x] Frontend crawling is optional and does not require adding new npm dependencies.

## Implementation Notes

The API checks are the reliable baseline because they run against the live ALOS
backend and module routers. The UI crawler is intentionally optional because the
packaged Tauri WebView is not directly controllable by Playwright/CDP; it is
useful against a browser/dev frontend or a Chrome debug target.

Use safe mode first:

```bash
ALOS_API_KEY="alos_..." npm run audit:scout
```

Then expand coverage:

```bash
ALOS_API_KEY="alos_..." npm run audit:scout -- --write-checks
ALOS_API_KEY="alos_..." npm run audit:scout -- --frontend-url http://localhost:5173
```

## Verification Commands

```bash
node --check scripts/scout_audit.mjs
node scripts/scout_audit.mjs --help
npm run audit:scout -- --help
```

## Status Updates

- 2026-04-19 (codex): added the Scout audit harness, package script, CSV schema,
  Scout event recording, safe write checks, and optional Chrome/CDP UI crawling.
