---
id: 0147
title: Run full v0.2 production readiness gate
area: core
status: blocked
assigned_to: null
created: 2026-04-18
updated: 2026-04-18
effort: m
blocks: []
blocked_by: [0143, 0146, 0152, 0153, 0154]
related_rfc: null
pr: null
---

# 0147 — Run full v0.2 production readiness gate

## Context

ALOS is close enough to release that the risk is no longer "can we build it?"
The risk is shipping a partially wired product because the shell launches and
the visible surfaces mount. This task is the final readiness gate. It uses
[`../RELEASE-READINESS.md`](../RELEASE-READINESS.md) as the standard.

## Scope

**In scope:**
- Verify every gate in `RELEASE-READINESS.md`.
- Produce a release-readiness report with pass/fail status for each gate.
- File follow-up tasks for every failed gate.
- Confirm whether v0.2 is a release candidate, an integration candidate, or
  still in active buildout.

**Out of scope:**
- Fixing failures discovered during the gate. Each failure gets its own task.
- Adding v0.3 features.
- Waiving gates without explicit user approval recorded in
  `RELEASE-READINESS.md`.

## Files to touch

- `planning/40-tracking/RELEASE-READINESS.md` — record any approved exception.
- `planning/40-tracking/tasks/0147-production-readiness-gate.md` — status
  updates and evidence.
- `planning/40-tracking/board.md` — task state transition.
- New task files under `planning/40-tracking/tasks/` for any failed gates.

## Acceptance criteria

- [ ] `npx tsc -b --noEmit` exits 0.
- [ ] `npm run build` exits 0.
- [ ] `cd src-tauri && cargo check && cargo fmt --check && cargo test` exits 0.
- [ ] `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/` exits 0.
- [ ] Root JavaScript test scope is corrected or documented so scratch/vendor
      GitNexus failures do not mask ALOS-owned test results.
- [ ] Packaged `.app` launches and spawns the frozen Python sidecar.
- [ ] Packaged first-run auth bootstrap UX is release-ready and verified.
- [ ] Original-admin first-run setup works without terminal bootstrap.
- [ ] Chat is a frontier-grade authenticated agent experience through the
      backend session/WebSocket contract.
- [ ] Forge supports solo, user-led agent-assisted, and autonomous programming.
- [ ] Current supports solo, user-led agent-assisted, and autonomous workflow
      orchestration.
- [ ] Atlas provides visual dependency intelligence for users and agents.
- [ ] Chamber gates agent writes through build/test completion before disk
      mutation.
- [ ] Settings are robust enough for provider setup, admin setup/recovery,
      diagnostics, runtime/workspace settings, and safety controls.
- [ ] `npm run tauri build` produces a valid DMG and the app launches from it.
- [ ] Manual end-to-end smoke evidence from 0143 is attached or linked.
- [ ] A dependency and impact map exists for release-critical flows, produced
      from Atlas evidence, local CLI evidence, filesystem audit, or external
      GitNexus MCP resources when available.
- [ ] `grep -rn -E 'RexCode|RexFlow|RexNexus|RexBot|RexHub' . -g '!Upgrades From Rex/**' -g '!planning/**' -g '!node_modules/**' -g '!scratch/**' -g '!**/_vendor/**' -g '!dist/**' -g '!backend/dist/**'`
      returns 0.
- [ ] A final readiness report states one of: `release_candidate`,
      `integration_candidate`, or `active_buildout`.

## Implementation notes

- Do not compress this task into a quick smoke test. It is allowed to take
  time.
- Use GitNexus MCP resources if available, but do not treat Codex-side MCP
  configuration as an ALOS release blocker. If MCP is unavailable, continue
  with Atlas, local CLI output, and direct filesystem audit evidence.
- If Atlas claims parity with GitNexus for a gate, record the exact Atlas
  command/tool output used as evidence.
- Any failure should become a new task with mechanical acceptance criteria.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
cd src-tauri && cargo check && cargo fmt --check && cargo test
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
grep -rn -E 'RexCode|RexFlow|RexNexus|RexBot|RexHub' . \
  -g '!Upgrades From Rex/**' \
  -g '!planning/**' \
  -g '!node_modules/**' \
  -g '!scratch/**' \
  -g '!**/_vendor/**' \
  -g '!dist/**' \
  -g '!backend/dist/**'
```

## Status updates

- 2026-04-18 (codex): created as blocked by 0143 and 0145 to prevent v0.2
  from being treated as shippable before the full product, packaging,
  integration, dependency, and docs gates pass.
- 2026-04-18 (codex): 0145 is done; 0148 now blocks this gate because packaged
  first-run auth bootstrap is not release-ready yet.
- 2026-04-18 (codex): 0148 is done; original-admin setup now happens in-app
  for an empty local auth database and terminal bootstrap is no longer the
  normal first-run path.
- 2026-04-18 (codex): 0149 and 0150 now block this gate after packaged
  verification exposed Chat as a scaffold and Forge as not yet release-hardened.
- 2026-04-18 (codex): 0151 through 0154 now block this gate after user
  clarified v0.2 must include fully connected Current, visual/agent-usable
  Atlas, Chamber pre-write build/test gating, and robust Settings.
- 2026-04-18 (codex): 0149 is done; full readiness remains blocked by 0143,
  0146, and 0150 through 0154.
- 2026-04-18 (codex): 0150 is done. Full readiness remains blocked by 0143,
  0146, and 0151 through 0154.
- 2026-04-18 (codex): 0151 is done. Full readiness remains blocked by 0143,
  0146, and 0152 through 0154.
