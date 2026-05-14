---
id: 0151
title: Current must fully support solo, assisted, and autonomous workflow orchestration
area: current
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

# 0151 — Current must fully support solo, assisted, and autonomous workflow orchestration

## Context

Current is not just a mounted workflow UI. For v0.2 it must be the operational
workflow layer of ALOS: users can build workflows alone, build them with agent
assistance, or let ALOS autonomously orchestrate workflows as part of broader
operations.

## Scope

**In scope:**
- Connect the Current UI to the ALOS sidecar/API contract.
- Create, edit, save, publish, execute, approve, stop, and audit workflows.
- Wire Current to the agent runtime through the existing `invoke_agent` node and
  runtime event recording.
- Support solo workflow authoring without agents.
- Support user-led agent-assisted workflow making.
- Support ALOS autonomous workflow orchestration with clear approval,
  observability, and rollback/audit boundaries.
- Surface workflow execution state and errors in the UI.

**Out of scope:**
- A marketplace of workflow templates.
- v0.3-only workflow collaboration features.

## Acceptance criteria

- [x] User can create, edit, save, publish, execute, approve, stop, and audit a
      workflow from the desktop app.
- [x] User can build workflows alone with no agentic help.
- [x] User can ask agents to assist in workflow creation and review proposed
      workflow changes.
- [x] ALOS can autonomously orchestrate workflows as part of operations without
      bypassing approval and audit gates.
- [x] `invoke_agent` workflow steps execute through the real agent runtime and
      record run events.
- [x] Current uses the ALOS sidecar/API contract, not old standalone ports or
      legacy Rex-era assumptions.
- [x] Workflow failures are visible, recoverable, and persisted for audit.

## Verification commands

```bash
npx tsc -b --noEmit
npx vitest run --exclude "scratch/**"
npm run build
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
```

Manual verification:

1. Create and save a simple workflow.
2. Publish and execute it.
3. Execute a workflow with an `invoke_agent` step.
4. Approve or reject a gated workflow action.
5. Stop a running workflow and confirm the audit trail records it.

## Status updates

- 2026-04-18 (codex): created from v0.2 clarification. Current is a release
  blocker until it is a real workflow orchestration surface, not just mounted UI.
- 2026-04-18 (codex): completed Current v0.2 orchestration hardening. The
  Current backend now mounts under the authenticated ALOS sidecar at
  `/api/current/*`; the desktop UI no longer targets the old standalone
  `127.0.0.1:8770` contract. Workflow execution can now be started
  asynchronously so the UI can stream/poll state and cancel active runs.
  Approval resolution can also resume asynchronously. Added an in-Current
  Agent tab backed by the authenticated Chat websocket; agents receive
  structured workflow context and proposed workflow graph JSON must be
  reviewed, validated, and manually applied by the user. Added focused Current
  service tests for approval/audit persistence and cancellable async execution.
  Verification passed: `npx tsc -b --noEmit`,
  `npx vitest run --exclude "scratch/**"`, `npm run build`, and
  `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/` (36 passed).
