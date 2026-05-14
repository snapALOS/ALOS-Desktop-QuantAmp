---
id: 0153
title: Chamber must gate agent writes through build and test completion
area: chamber
status: done
assigned_to: null
created: 2026-04-18
updated: 2026-04-18
effort: l
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0153 — Chamber must gate agent writes through build and test completion

## Context

Agents should not write directly to disk just because they can produce a patch.
For v0.2, build tasks and tests must complete inside Chamber before changes are
written to disk. Chamber becomes the operational proving ground for agent work:
plan, stage, build, test, review, then write.

## Scope

**In scope:**
- Define Chamber's pre-write lifecycle for agent work.
- Stage proposed file changes in Chamber before disk writes.
- Run required build/test commands in Chamber for the task's affected area.
- Block direct agent disk writes until the Chamber gate passes or the user
  explicitly overrides with an audited exception.
- Integrate Chamber status with Forge and Current autonomous workflows.
- Record build/test evidence and approval decisions.
- Make failed Chamber runs visible and recoverable.

**Out of scope:**
- Removing all developer/manual edit paths.
- Full cloud sandboxing unless already required by the local Chamber design.

## Acceptance criteria

- [x] Agent-proposed disk writes are staged before they touch the workspace.
- [x] Chamber runs the required build/test commands for the staged task.
- [x] Failed build/test gates block writes by default.
- [x] Successful gates record evidence before writing.
- [x] User override is possible only with explicit approval and audit record.
- [x] Forge autonomous programming routes proposed writes through Chamber.
- [x] Current autonomous workflow changes route proposed writes through Chamber.
- [x] Chamber UI shows running, passed, failed, blocked, and approved states.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
```

After code changes, the GitNexus index should be refreshed by the user with:

```bash
node scratch/git-nexus/gitnexus/dist/cli/index.js analyze --skip-git
```

Manual verification:

1. Ask an agent to make a harmless code change.
2. Confirm the change is staged in Chamber before disk write.
3. Confirm build/test commands run.
4. Confirm a failing gate blocks the write.
5. Confirm a passing gate can be approved and written with evidence.

## Status updates

- 2026-04-18 (codex): created from v0.2 clarification. Chamber is a release
  blocker because safe autonomous work depends on a real pre-write build/test
  gate.
- 2026-04-18 (codex): completed the v0.2 Chamber pre-write gate. Added
  persistent Chamber gate records, isolated workspace staging, inferred
  build/test command execution, failed-gate blocking, explicit override audit,
  patch payload gate visibility, authenticated Chamber gate API endpoints, and
  Chamber UI status/evidence display. Forge and Current agent instructions now
  route autonomous file writes through proposed patches and the Chamber gate.
  Documented the lifecycle in `modules/chamber/docs/PREWRITE-GATES.md`.
