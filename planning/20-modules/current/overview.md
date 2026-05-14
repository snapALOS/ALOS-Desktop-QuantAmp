# ALOSCurrent — Overview

**Canonical name:** ALOSCurrent  
**Dead name:** RexFlow  
**Source:** `Upgrades From Rex/rexflow-workflow-orchestrator/` *(once copy completes)* or `/Volumes/DDrive/Rex'S Upgrades/rexflow-workflow-orchestrator/`  
**Target location:** `modules/current/`  
**Tagline:** "Workflow orchestration for agents, tools, and humans. DAGs that think."

## What it is

A DAG-based workflow orchestrator with a visual editor, SQLite persistence, and a full audit trail. Sits **above** LangGraph in the agent stack — Current runs long-lived workflows that can invoke agents, call HTTP, run shell, wait on human approval, fire on schedules and webhooks.

## Source evaluation (summary)

Full report: see evaluation notes in [../../00-overview/vision.md](../../00-overview/vision.md). Highlights:

- **Python stdlib only** — no external deps. Zero install friction.
- **~3,400 LOC** — production-shaped, not a prototype.
- **SQLite at `~/.alos/current.sqlite`** (rebranded from `~/.rexflow/`).
- **Node types shipped:** manual/webhook/schedule/event triggers, HTTP, transform, condition, parallel, join, delay, approval gate, assign-agent, escalation, notification, audit, terminal output.
- **Frontend:** polished React+Vite SPA. Tabs: Designer / Monitor / Tasks / Swarm / Audit / Settings.
- **API:** HTTP REST on port 8770 (rebrand to `alos-current` on same or configurable port), SSE events, optional token auth.
- **Sync execution** — each step blocks. Agent calls need thread-pool wrapping.
- **RexBot swarm model hardcoded in node executors** — needs adapter layer for ALOS agent runtime.

## Why it's in v0.2

ALOS markets itself as an OS. An OS needs a scheduler / automation layer. Current is that layer:

- "Every git push, run Atlas impact analysis and post to the audit log."
- "At 9am, have the agent summarize yesterday's commits into a markdown file."
- "When a high-risk diff lands, pause and wait for my approval."

These are not conversational. They are workflows. LangGraph cannot express them. Current can.

## Key capabilities (v0.2)

| Capability | Source status | v0.2 change |
|---|---|---|
| Visual DAG editor | Works | Rebrand only |
| SQLite persistence + versioning | Works | Path change: `~/.rexflow/` → `~/.alos/current/` |
| Triggers: manual / webhook / schedule / event | Works | Rename "rexhub event" trigger → "alos event" (reads shell event bus) |
| HTTP / transform / condition / parallel / join / delay nodes | Works | None |
| Swarm nodes (dept-head, sub-agent, escalation) | Works against RexBot model | **Replace** with ALOS agent adapter |
| Approval gates | Works | Frontend integrate with ALOS shell notifications |
| Audit log | Works | Forward to ALOS audit event stream |
| SSE event stream | Works | None |
| Frontend SPA | Works | Embed in `/current` route; strip standalone-mode bootstrap |

## What's added for v0.2

- **`invoke_agent` node type** — see [../../10-architecture/agent-runtime.md](../../10-architecture/agent-runtime.md). Calls LangGraph supervisor as a step.
- **Thread-pool executor wrapper** — keeps the frontend responsive during agent-heavy workflows.
- **Event bus subscription** — Current listens to `forge.*`, `atlas.*` events as trigger sources.

## What is NOT in v0.2

- Standalone-mode (separate `rexflow-server` binary). Deferred.
- Postgres backend. SQLite only.
- Distributed execution. Single-process.
- Workflow marketplace / sharing. Local only.
- Custom node types authored by users at runtime. Node type registry is compile-time.

## Surfaces

### Frontend
- Mount point: `/current` route.
- Owns sub-routes: `/current/designer`, `/current/monitor`, `/current/tasks`, `/current/audit`, `/current/settings`.

### Backend (Python)
- Package: `alos_current` at `modules/current/backend/src/alos_current/`.
- Routes under `/api/current/*` on the sidecar.
- SQLite at `~/.alos/current/current.sqlite`.

### Events emitted
- `current.workflow.created`
- `current.workflow.published`
- `current.workflow.started` (payload: workflowId, runId, trigger)
- `current.workflow.step.started` (payload: runId, stepId, stepType)
- `current.workflow.step.completed` (payload: runId, stepId, status, durationMs)
- `current.workflow.completed` (payload: runId, status)
- `current.approval.requested` (payload: runId, stepId, prompt, options)
- `current.approval.resolved` (payload: runId, stepId, decision, actor)

### Events consumed (as triggers)
- Any `AlosEvent` from the shell event bus. Users pick which events trigger which workflows in the designer.

### Agent-facing tools (MCP)
- `current_list_workflows()` — list all published workflows.
- `current_trigger_workflow(workflowId, inputs)` — fire a workflow manually. `risk: "medium"` (can have side effects).
- `current_get_run_status(runId)` — read a run's state.

## Dependencies on other modules

- **LangGraph / agent runtime** (required if workflows use `invoke_agent` nodes).
- None other; Current is an independent engine.

## Risk & unknowns

- Thread-pool wrapping of agent calls needs careful cancellation semantics (what happens when a workflow is cancelled mid-agent-turn?).
- SSE event stream must not leak memory under long idle sessions.
- The existing RexHub auth model (token-based) may not map cleanly to ALOS's shell-local trust model; plan to drop auth for v0.2 and add back in v0.3 when we support remote control.
