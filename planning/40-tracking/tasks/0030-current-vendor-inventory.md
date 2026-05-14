---
id: 0030
title: Current — vendor source and produce INVENTORY.md
area: current
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: s
blocks: [0031]
blocked_by: [0001]
related_rfc: null
pr: null
---

# 0030 — Current — vendor source and produce INVENTORY.md

## Context

Phase 1 of the Current fold-in. Same shape as 0010 but for the RexFlow orchestrator.

See [`planning/20-modules/current/integration-plan.md`](../../20-modules/current/integration-plan.md) Phase 1.

## Scope

**In scope:**
- Copy `Upgrades From Rex/rexflow-workflow-orchestrator/` (or equivalent source on DDrive) → `modules/current/_vendor/`.
- Produce `modules/current/_vendor/INVENTORY.md` with the same columns as 0010: `path | size | language | decision | target path | notes`.
- Critical decisions to capture explicitly:
  - Every file importing `rexhub_*` → decision `rewrite` (replace with ALOS event-bus subscriber) or `drop` (if RexHub-only feature with no ALOS equivalent).
  - Every file implementing swarm nodes (`assign_department_head`, `assign_sub_agent`, `escalation_gate`) → `rewrite` (replace with `invoke_agent` node type).
  - The standalone HTTP server bootstrap → `rewrite` (route will mount under the ALOS sidecar instead).
  - The `main.tsx` frontend bootstrap → `rewrite` (module-mounted, not standalone).

**Out of scope:**
- Any code movement out of `_vendor/`.

## Files to touch

- (NEW) `modules/current/_vendor/**`
- (NEW) `modules/current/_vendor/INVENTORY.md`

## Acceptance criteria

- [ ] Inventory exists and is comprehensive.
- [ ] Every file importing `rexhub` is decisioned (no TBDs).
- [ ] Every swarm-node implementation file is decisioned `rewrite` with target "invoke_agent node executor".
- [ ] The standalone `http.server` bootstrap is decisioned `rewrite`.
- [ ] Polished React SPA files (Designer, Monitor, Tasks, Audit tabs) are decisioned `keep` with target path `modules/current/frontend/src/`.

## Implementation notes

- Refer to the evaluation summary in [`planning/20-modules/current/overview.md`](../../20-modules/current/overview.md) for expected file groupings.
- Double-check Python files don't use external packages (source eval said stdlib-only). Any `import` of something other than stdlib or project-local should be flagged.

## Verification commands

```bash
ls modules/current/_vendor/
wc -l modules/current/_vendor/INVENTORY.md
grep -c 'rexhub' modules/current/_vendor/INVENTORY.md   # sanity: should match source prevalence
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-16 (opus): vendor tree copied; INVENTORY.md written.
- 2026-04-17 (claude): verified schema and completeness. Status `ready → done`.
