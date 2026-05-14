---
rfc: 0002
title: invoke_agent node contract + Current/LangGraph checkpoint semantics
status: accepted
author: claude
created: 2026-04-15
accepted: 2026-04-15
supersedes: null
---

# RFC 0002 — invoke_agent node contract + Current/LangGraph checkpoint semantics

## Summary

Define exactly how a Current workflow step invokes a LangGraph agent run: the input/output contract, the threading model, cancellation and timeout semantics, and where the checkpoint boundary sits between the two engines. Closes open question OQ-1 flagged in [`agent-runtime.md`](../10-architecture/agent-runtime.md).

## Motivation

Current (workflow orchestrator, minute-to-day lifetime, durable SQLite) and LangGraph (agent turn engine, second-to-minute lifetime, ephemeral state) are different runtimes. A Current workflow step of type `invoke_agent` needs to reach into LangGraph, run a conversation, and return a result.

Without a locked contract, each implementation agent will answer differently:
- What's the shape of the input?
- Does the step block or fire-and-forget?
- What happens if the workflow is cancelled mid-agent-turn?
- If a step times out at turn 3 of 10, does a retry resume from turn 3 or restart?
- Where does LangGraph state persist? In Current's SQLite? Its own? Nowhere?
- What does the Monitor tab show during a long agent step?

This RFC answers all of them. It binds tasks 0033 (`invoke_agent` executor), 0034 (HTTP mount), and 0039 (Current MCP tools).

## Proposal

### Decision 1 — Input and output contracts (locked)

Contract files (created as part of task 0033):

```python
# modules/current/contracts/nodes/invoke_agent.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class InvokeAgentNodeInput(BaseModel):
    prompt: str
    agent_id: str = "supervisor"
    allowed_tools: Optional[List[str]] = None       # None = agent default; [] = no tools; [...] = explicit allowlist (subject to RFC-0003 scoping rules)
    max_risk: Optional[Literal["low", "medium", "high", "critical"]] = None  # step-level cap on risk; AND with agent default
    max_turns: int = 10
    timeout_seconds: int = 300
    context: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = True


class ToolCallRecord(BaseModel):
    turn: int
    tool_name: str
    args: Dict[str, Any]
    result_summary: str            # truncated preview; full result in logs
    status: Literal["ok", "denied", "error"]
    denial_reason: Optional[str] = None
    duration_ms: int


class ErrorDetail(BaseModel):
    code: str                       # machine-readable, e.g. "agent_timeout", "tool_error"
    message: str
    turn_index: Optional[int] = None
    tool_name: Optional[str] = None


class InvokeAgentNodeOutput(BaseModel):
    status: Literal["ok", "timeout", "max_turns_exceeded", "capability_denied", "cancelled", "error"]
    output: str = ""                # agent's final answer; empty on non-ok unless partial is available
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    turns_used: int = 0
    started_at: datetime
    completed_at: datetime
    error: Optional[ErrorDetail] = None
    routing_decisions: List[Dict[str, Any]] = Field(default_factory=list)  # shape from backend.src.agents.capabilities.RoutingDecision
```

The TypeScript mirror lives at `modules/current/contracts/nodes/invoke_agent.ts` with the same shape (use a TS codegen or hand-author; hand-author acceptable for v0.2).

### Decision 2 — Threading model (locked)

- The Current workflow executor stays synchronous (per the source evaluation). Each step runs on the executor thread.
- A `concurrent.futures.ThreadPoolExecutor` with **4 workers by default** is owned by the Current service (`alos_current.runtime.agent_pool`). Configurable via `~/.alos/current/config.json` key `agent_pool.max_workers`.
- When an `invoke_agent` step fires, the executor submits a callable to this pool and blocks the workflow-step thread on `future.result(timeout=timeout_seconds)`.
- The inside of the callable is what actually talks to LangGraph.

**Why shared pool, not per-workflow:** a single long-running agent step should not starve other workflows running in parallel. Pool size 4 is sane for desktop (user's CPU, one user, agent calls are I/O-bound on the LLM).

**Why block the step thread:** the Current executor is already built to run steps sequentially with checkpoints between them. Introducing async/await at the step level is a larger refactor than v0.2 should absorb. The pool wrapper protects responsiveness without forcing async.

### Decision 3 — Cancellation (cooperative)

Cancellation is **cooperative**, not preemptive. When a workflow is cancelled (user clicks Cancel on Monitor, or a parent step fails hard):

1. Current sets `run_state[runId].cancelled = True` in an in-memory dict.
2. The `invoke_agent` callable polls this flag **between turns** (not mid-LLM-call).
3. On observing the flag, the callable stops the LangGraph loop and returns with `status: "cancelled"` and whatever partial `output` / `tool_calls` were produced so far.
4. In-flight LLM HTTP requests are not aborted. Let them complete (they're already billed). The result is discarded.

Implementation: LangGraph supervisor accepts a `cancel_check: Callable[[], bool]` callback. It consults it between turns. If True → raise a `CooperativeCancelException` caught by the `invoke_agent` wrapper.

### Decision 4 — Timeout semantics

- Step-level timeout (`timeout_seconds`, default 300) starts when the pool submits the task, not when LangGraph starts the first turn.
- On timeout:
  - The pool raises `concurrent.futures.TimeoutError` to the workflow thread.
  - The workflow step records `status: "timeout"` with whatever `turns_used` / `tool_calls` were observable at the last turn boundary (best-effort; may be zero).
  - The underlying thread is **not forcibly killed** (Python doesn't support safe thread kill). It sets the cancel flag and detaches; the thread completes its current turn and exits.
- A workflow can set `timeout_seconds: 0` to mean "no timeout" (user's choice, logged as WARN).

### Decision 5 — Retry semantics

Current's existing retry logic reruns failed steps. For `invoke_agent`:

- **Each retry starts the agent from scratch** — new LangGraph run, fresh state, same `InvokeAgentNodeInput`.
- **No partial resume** in v0.2. Agents are non-deterministic; "resume from turn 3" is undefined behavior because the agent's internal reasoning doesn't checkpoint coherently mid-run.
- If a workflow author needs "resume-like" behavior, they model it as separate workflow steps (agent step A → tool step → agent step B), not as retry-in-place.

### Decision 6 — Checkpoint boundary

- **Current's SQLite persists step-level I/O only:** the `InvokeAgentNodeInput`, the `InvokeAgentNodeOutput`, step status, timestamps. That's it.
- **LangGraph's internal state is ephemeral.** It is not written into Current's SQLite. If the backend crashes mid-step, on restart Current sees an `invoke_agent` step stuck in `running` and promotes it to `error` with code `"sidecar_restart"`. The workflow's retry policy takes over.
- LangGraph may maintain its own per-run audit log for debugging, but it is **not** consulted during retry and **not** shared with Current.

This boundary means LangGraph can evolve its internal state shape freely — even breaking changes — without affecting Current's persisted data.

### Decision 7 — Streaming to the Monitor UI

When `stream: true` (default), the `invoke_agent` wrapper publishes events to the shell event bus per RFC-0005 semantics:

- `current.agent_step.turn_started` — payload: `{ runId, stepId, turn, agentId }`
- `current.agent_step.turn_completed` — payload: `{ runId, stepId, turn, agentId, tokensIn, tokensOut, toolCalls: ToolCallRecord[] }`
- `current.agent_step.tool_call` — payload: `{ runId, stepId, turn, toolName, status, durationMs }`

These are additive to existing Current step events (`current.workflow.step.started` / `.completed`). The Monitor tab subscribes to them for a nested "agent turns within this step" timeline view (UI implementation deferred to a later task — contract is wired now).

With `stream: false`, only the step-level events fire. For performance-sensitive workflows or very long agent conversations.

### Decision 8 — Error classification

Map agent-runtime outcomes → `InvokeAgentNodeOutput.status`:

| Runtime condition | status | notes |
|---|---|---|
| Agent returns final answer within `max_turns` | `"ok"` | happy path |
| Agent exhausts `max_turns` | `"max_turns_exceeded"` | `output` contains the last turn's partial content |
| Step exceeds `timeout_seconds` | `"timeout"` | partial if reachable |
| Workflow cancelled from UI or parent | `"cancelled"` | partial if reachable |
| Tool call denied by capability gate | `"capability_denied"` | only if the denial is terminal; if the agent recovers by routing around, final status can still be `"ok"` |
| LLM / tool / runtime exception (network, parse, etc.) | `"error"` | `error.code` typed |

### Decision 9 — Where is the supervisor entry point exposed?

Add a pure function to the existing agents package:

```python
# backend/src/agents/invoke.py
from __future__ import annotations

from typing import Callable, Optional
from src.agents.capabilities import ScopedCapabilityPolicy  # see RFC-0003
from modules.current.contracts.nodes.invoke_agent import (
    InvokeAgentNodeInput,
    InvokeAgentNodeOutput,
)


def run_agent_step(
    inputs: InvokeAgentNodeInput,
    scoped_policy: Optional[ScopedCapabilityPolicy] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> InvokeAgentNodeOutput:
    """Run one agent 'conversation' for a workflow step.

    - `scoped_policy`: per-step capability scoping (RFC-0003). None = agent default.
    - `cancel_check`: polled between turns (Decision 3).
    - `on_event`: fired with (event_type, payload) for streaming (Decision 7).
    """
```

This function is the single integration point. `alos_current` imports it; no other integration surface exists.

### Decision 10 — What this RFC does NOT decide

- **Distributed execution.** All agent steps run on the same machine as Current. Remote agent workers are v0.3+.
- **Cross-workflow agent state sharing.** Each step is a fresh agent run. State sharing (e.g., a shared "notebook" across steps) needs its own RFC.
- **Multiple agents cooperating within one step.** The `agent_id` field picks one (or defaults to supervisor routing); multi-agent-per-step coordination happens inside the supervisor, not in the Current contract.
- **Subscription-based UI** (WebSocket, real-time tokens). v0.2 emits turn-granular events only. Token streaming is a v0.3+ concern.

## Alternatives considered

### A. Fully async Current executor

Convert Current's DAG engine to async/await and remove the thread pool. Rejected: the source evaluation says Current is ~3.4K LOC of synchronous Python with SQLite-backed state. Converting it touches every step type and the checkpoint layer. For 0.5–1 days of "responsiveness under agent load," pool-wrapping is 80% of the benefit at 10% of the risk.

### B. Persist LangGraph state in Current's SQLite

Enable resume-from-turn-N retries. Rejected: agent turn sequences are semantically fragile; resuming tends to produce incoherent behavior because the agent "didn't really remember" why it was about to do the next thing. Let failures restart. Let authors decompose workflows if granular resume is needed.

### C. Preemptive cancellation via signal / thread-kill

Kill in-flight LLM calls on cancel. Rejected: Python lacks safe thread kill; SIGINT to a specific thread is not portable; aborting HTTP requests mid-call is racy and providers bill regardless. Cooperative cancel with `cancel_check` is honest about what we can actually do.

### D. Per-workflow dedicated agent pool

Give each workflow its own `ThreadPoolExecutor`. Rejected: for desktop single-user workloads, 4 shared workers suffice. Per-workflow isolation is a server-side concern.

## Impact

- **Contracts introduced:** `modules/current/contracts/nodes/invoke_agent.py` + `.ts` mirror. Consumed by `alos_current.runtime.executor` (task 0032/0033) and `backend/src/agents/invoke.py` (new).
- **Events added** (must be appended to `src/contracts/events.ts`): `current.agent_step.turn_started`, `current.agent_step.turn_completed`, `current.agent_step.tool_call`.
- **Config file:** `~/.alos/current/config.json` with initial schema `{ "agent_pool": { "max_workers": 4 } }`.
- **Migrations:** none (first release of the contract).
- **Rollback:** revert to a Current without `invoke_agent` support. Workflows stop working but no data corruption — step records with `node_type: "invoke_agent"` can be marked as failed on reload.

## Open questions

- **OQ-2-1:** If a workflow invokes the same agent_id concurrently via `parallel` node children, does the agent have shared state? **Answer (v0.2):** No. Each `invoke_agent` call is an independent LangGraph run. Parallel invocation works but shares nothing except the agent's declarative policy.
- **OQ-2-2:** Should `timeout_seconds: 0` mean "no timeout" or "timeout immediately"? **Decision:** no timeout. Match Unix convention on `timeout` utility.
- **OQ-2-3:** Per-step `max_risk` override — is it a cap (can only lower) or a replacement (can raise)? **See RFC-0003.** Decided there: cap only.

## Decision log

- 2026-04-15 (claude): initial draft and accepted. Binds tasks 0033, 0034, 0039.
