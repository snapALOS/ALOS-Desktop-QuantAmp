---
id: 0154
title: Users need a robust settings interface
area: core
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

# 0154 — Users need a robust settings interface

## Context

ALOS cannot depend on hidden files, terminal-only bootstrap commands, or
developer knowledge for normal configuration. Users need a robust settings
surface for providers, auth/admin state, runtime paths, module settings,
privacy/safety choices, and diagnostics.

## Scope

**In scope:**
- Provider/API-key configuration and validation.
- Original-admin/account/key management flows appropriate for v0.2.
- Runtime and workspace settings.
- Module settings for Chat, Forge, Current, Atlas, and Chamber where needed.
- Safety/approval settings for agent writes, Chamber gates, and autonomous
  actions.
- Diagnostics: backend status, logs location, data directory, version/build
  info, and reset/recovery actions.
- Clear save/cancel/error states.

**Out of scope:**
- Enterprise multi-tenant admin console.
- Cloud account billing management.

## Acceptance criteria

- [x] Settings are reachable from the authenticated shell.
- [x] Provider settings can be validated, saved, edited, and cleared.
- [x] Admin/auth settings support the v0.2 first-run and recovery flows.
- [x] Users can inspect data directory, logs, backend health, and app version.
- [x] Users can configure safety/approval behavior for agent and Chamber gates.
- [x] Settings failures are visible and recoverable.
- [x] Settings copy is honest and does not require terminal knowledge for
      ordinary use.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
```

Manual verification:

1. Open Settings after login.
2. Validate and save provider configuration.
3. Inspect backend/data/log diagnostics.
4. Change an approval/safety setting and confirm the runtime honors it.
5. Exercise a failed settings save and confirm the UI recovers.

## Status updates

- 2026-04-18 (codex): created from v0.2 clarification. Settings are a release
  blocker because users should not need terminal-only workflows for normal app
  setup and operation.
- 2026-04-18 (codex): completed robust authenticated Settings module. Added
  provider validation/save/clear, advanced model controls (temperature, top-p,
  top-k, token/context budgets, penalties, seed), runtime retry/timeout knobs,
  Chamber safety controls, admin/bootstrap state, diagnostics paths/version,
  backend persistence, LLM factory propagation, and tests for config and
  Chamber safety behavior.
- 2026-04-18 (codex): verification passed: `python3.11 -m py_compile` for
  changed backend modules, `env PYTHONPATH=.:backend python3.11 -m pytest
  backend/tests/` (50 passed), `npx tsc -b --noEmit`, and `npm run build`
  (passed with Vite's existing large-chunk warning).
