# Agent Runtime: LangGraph vs ALOSCurrent

**TL;DR:** They are different layers. LangGraph stays; Current is added on top.

## The distinction

| | **LangGraph** | **ALOSCurrent** |
|---|---|---|
| Purpose | Agent turn engine | Workflow orchestrator |
| Scope | One conversation / one job | Cross-time, cross-module |
| Lifetime | Seconds–minutes | Minutes–days, recurring |
| State | In-memory + per-turn checkpoint | Durable SQLite, audit log |
| Triggered by | User message / tool call | Cron, webhook, event, manual |
| Thinks about | Which agent answers next | Which step runs next, given history |
| Human-in-the-loop | Implicit (chat) | Explicit (approval gates) |
| Retry semantics | None (agent just re-answers) | First-class (retry, escalate, bail) |

## How they compose

```
User or cron or webhook
        │
        ▼
 ┌──────────────┐
 │  ALOSCurrent │   workflow picks up; executes DAG
 │   (workflow) │
 └──────┬───────┘
        │  node type = "invoke_agent"
        ▼
 ┌──────────────┐
 │  LangGraph   │   agent supervisor runs one "conversation"
 │  supervisor  │   scoped to this workflow step
 └──────┬───────┘
        │
        ▼
 Tools (Atlas, LSP, shell, etc.) → result bubbles back to Current
```

**A Current workflow step of type `invoke_agent`** accepts:
- `prompt: string` — what the agent is asked to do
- `allowed_tools: string[]` — scoped capability list
- `max_turns: int` — hard cap
- `timeout_seconds: int`
- `context: object` — forwarded as initial agent state

and returns:
- `output: string`
- `tool_calls: ToolCall[]`
- `turns_used: int`
- `status: "ok" | "timeout" | "capability_denied" | "error"`

## Where the v0.1 supervisor fits

The v0.1 supervisor (capability-scored routing, ambiguity-gated LLM fallback, EWMA decay, single-selection invariant) is **preserved verbatim**. It runs as the LangGraph-side orchestrator whenever:

- The user chats directly with the agent surface (existing v0.1 flow), OR
- A Current workflow's `invoke_agent` node fires.

No architectural change to `backend/src/agents/` is required for v0.2 beyond exposing the supervisor entry point to Current as a Python function.

## What this means for the dev team

- **No rewrite of the agent swarm.** LangGraph stays, v0.1 routing stays.
- **No rewrite of Current.** It already has DAG engine + SQLite persistence (see evaluation in [../20-modules/current/overview.md](../20-modules/current/overview.md)).
- **The fold-in work** is: (a) build the adapter that lets Current invoke LangGraph, (b) replace Current's hardcoded RexBot swarm nodes with the ALOS agent model, (c) wrap synchronous agent calls in threads so Current's blocking executor doesn't stall.

## Decision: is Current required for every agent interaction?

**No.** Direct chat with agents bypasses Current entirely (goes straight to LangGraph). Current is opt-in: users build workflows in the Current canvas for repeatable automations. This keeps the conversational UX fast and the workflow UX powerful.

## Open questions (resolve via RFC before implementation)

- **Checkpointing across layers:** if a workflow step invokes an agent that invokes a tool that partially fails, where does the checkpoint live? Proposal: LangGraph state is ephemeral inside the step; only step-level results checkpoint to Current. See RFC-0002 (TBD).
- **Tool gating per workflow:** a workflow author may want to *narrow* an agent's capabilities for a specific step. Proposal: `allowed_tools` at the step level overrides (AND's with) the agent's default capabilities. See RFC-0003 (TBD).
