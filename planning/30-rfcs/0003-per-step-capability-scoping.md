---
rfc: 0003
title: Per-workflow-step capability scoping
status: accepted
author: claude
created: 2026-04-15
accepted: 2026-04-15
supersedes: null
---

# RFC 0003 — Per-workflow-step capability scoping

## Summary

Define how a Current workflow step can narrow an agent's capabilities for the duration of one invocation. Establishes the "AND-only, never OR" rule so workflow authors can tighten but never loosen an agent's policy. Closes OQ flagged in `agent-runtime.md`.

## Motivation

Agents ship with a default capability policy (see `backend/src/agents/capabilities.py::AgentCapabilityPolicy`): an allowed-tools list, a `max_risk` ceiling, a set of declared capabilities. A workflow author sometimes wants to be more conservative than the default for one specific step:

- "For this step, the agent may read files but not run shell."
- "For this step, cap risk at `medium` even though the agent can handle `high`."
- "For this step, disable the `atlas_change_scope` tool because we only want it to answer from context, not re-query."

Without a rule, three implementation outcomes are possible:
1. Step config overrides agent policy fully (agent can do anything the step lists, even if the agent wasn't meant to). **Dangerous.**
2. Step config ignored if the agent lacks the capability. **Confusing for the author.**
3. Step config AND'd with agent policy. **Safe, predictable.**

This RFC picks #3 and nails down the details.

## Proposal

### Decision 1 — AND-only intersection

A scoped policy is always a **subset** of the agent's default policy. The workflow step can tighten; it cannot widen.

Formally, given agent policy `A` and step overrides `S`:

```
effective.allowed_tools = A.allowed_tools ∩ (S.allowed_tools if provided, else A.allowed_tools)
effective.max_risk      = min(A.max_risk, S.max_risk if provided, else A.max_risk)
effective.capabilities  = A.capabilities    # capabilities are declarative; steps do not scope them
```

`max_risk` ordering: `low < medium < high < critical`.

### Decision 2 — `ScopedCapabilityPolicy` data model

```python
# backend/src/agents/capabilities.py — addition
class ScopedCapabilityPolicy(BaseModel):
    """A per-invocation override layered on top of an agent's default policy.

    Fields left as None inherit from the agent's default. Fields set narrow
    the agent (see RFC-0003). Widening is impossible by construction.
    """
    allowed_tools: Optional[List[str]] = None       # None = no override; [] = no tools; [...] = intersect
    max_risk: Optional[Literal["low", "medium", "high", "critical"]] = None  # None = no override


def effective_policy(
    agent: AgentCapabilityPolicy,
    scoped: Optional[ScopedCapabilityPolicy],
) -> AgentCapabilityPolicy:
    """Return a new AgentCapabilityPolicy = agent AND scoped."""
```

`effective_policy` is the **only** way to compute the runtime policy for a step. Ad-hoc intersections elsewhere are a code-review fail.

### Decision 3 — Silent-but-audited overreach

If the step's `allowed_tools` lists a tool the agent doesn't have:

- The tool is **silently dropped** from the effective set (it's already absent).
- A WARN log is emitted: `"scoped_policy: step requested tool 'X' that agent 'Y' does not have; ignored"`.
- The step's audit record includes an `ignored_step_tools: ["X"]` entry so it's visible in the Monitor tab and workflow export.

Rationale: hard-failing would make copy-pasted workflow templates brittle across agent configurations. Silent drop + audit preserves robustness with observability.

### Decision 4 — Denied-tool response at runtime

If the agent tries to call a tool that's blocked by the effective policy (either at agent-default level or by scoping):

1. The tool gate returns a structured denial: `{"status": "denied", "tool": "name", "reason": "not_in_allowed_tools" | "exceeds_max_risk"}`.
2. The denial is surfaced to the agent as a tool-result message it can react to (common outcome: it routes around or asks the user).
3. The denial lands in `ToolCallRecord.status = "denied"` + `denial_reason` in the step output.
4. The counter-system records `tool_denied += 1` for the agent (feeds EWMA decay — existing behavior in `record_agent_completion`).

**Denials do not terminate the agent turn by default.** Let the agent decide whether to give up or pivot. A step can set `fail_on_denial: true` in a future extension (out of scope for v0.2).

### Decision 5 — Where the scoped policy flows

1. Workflow author configures an `invoke_agent` step with `allowed_tools` and/or `max_risk` (see RFC-0002 `InvokeAgentNodeInput`).
2. Current's executor constructs a `ScopedCapabilityPolicy` from that config.
3. `alos_current.runtime.executor` calls `backend.src.agents.invoke.run_agent_step(inputs, scoped_policy=policy, ...)`.
4. Inside the agent runtime: `effective_policy(agent, scoped_policy)` runs once per turn (scope is per-step, not per-turn — cached once per invocation).
5. Each tool call consults the effective policy via the existing gate functions (`allows_tool`, `allows_risk`).

### Decision 6 — `capabilities` are NOT scoped

`AgentCapabilityPolicy.capabilities` is the declarative list of what the agent is "good at" — it drives routing, not runtime enforcement. Scoping capabilities makes no sense: you can't tell a coder agent "for this step, pretend you can't code." You either invoke it or you don't.

Step-level scoping affects `allowed_tools` and `max_risk` only.

### Decision 7 — Capability scoping for direct chat (not workflows)

Conversational agent turns (outside any workflow) do **not** support scoping in v0.2. Direct-chat agents run on their default policy. A later RFC may extend scoping to user-driven policies (e.g., "per-session restricted mode" for demo environments), but it is out of scope now.

### Decision 8 — Observability

The step's audit record (persisted by Current in `execution_steps`) includes:

```json
{
  "scoped_policy": {
    "allowed_tools": ["atlas_impact_symbol", "forge_read_file"],
    "max_risk": "medium"
  },
  "effective_policy": {
    "allowed_tools": ["atlas_impact_symbol", "forge_read_file"],
    "max_risk": "medium"
  },
  "ignored_step_tools": [],
  "denials": [
    { "turn": 3, "tool": "forge_run_command", "reason": "exceeds_max_risk" }
  ]
}
```

This lets the user reconstruct "why did the agent not do X" from the Monitor tab alone.

## Alternatives considered

### A. Override-not-intersect (OR semantics)

Let a step's `allowed_tools` add tools to an agent. Rejected. Violates the principle of least surprise: a workflow author shouldn't grant capabilities the agent was never vetted for.

### B. Hard-fail on unknown tool in step config

If the step lists a tool the agent doesn't have, reject the workflow at publish time. Rejected for v0.2: workflow templates are expected to move across agent configurations (e.g., demo template vs. production), and some tool-name divergence is common. Silent-drop + audit is friendlier; a linter at publish time can surface warnings without blocking.

### C. Scope `capabilities` too

Let steps restrict which of an agent's declared capabilities it advertises. Rejected per Decision 6 — capabilities are routing metadata, not runtime enforcement.

### D. Per-tool risk caps (not just `max_risk`)

Let a step say "allow `forge_apply_diff` but cap at risk=low" even if that tool is labeled `risk=high`. Rejected. Tools carry their own immutable risk class; caps operate globally, not per-tool. If a workflow author wants that granularity, they name the tool in `allowed_tools` or they don't.

## Impact

- **Code additions:** `ScopedCapabilityPolicy` model and `effective_policy` helper added to `backend/src/agents/capabilities.py`. Tool-gate functions unchanged (they already consult a `AgentCapabilityPolicy`; now they just consult the effective one).
- **Contract additions:** none in the contracts directories beyond what RFC-0002 already includes (`InvokeAgentNodeInput.allowed_tools` and `.max_risk`).
- **Events added:** none. Denials land in existing `current.agent_step.tool_call` events via `status: "denied"`.
- **Persistence:** step audit schema gains `scoped_policy`, `effective_policy`, `ignored_step_tools`, `denials`. Add in the same migration that introduces the `invoke_agent` node type.
- **Rollback:** without scoping, all steps run on agent defaults. Safe rollback — workflows keep working.

## Open questions

- **OQ-3-1:** Should `fail_on_denial` be a step-level option in v0.2 or deferred? **Decision:** deferred. Default "continue on denial" covers the overwhelming common case; hard-fail is a niche pattern.
- **OQ-3-2:** Where does the publish-time linter (Alternative B) live if/when we add it? **Answer:** outside this RFC — separate task, separate UI. The contract is agnostic.
- **OQ-3-3:** Do MCP tools exposed by modules (`forge_*`, `atlas_*`, `current_*`) register their risk class in a central registry, or per-module? **Decision:** per-module MCP registration declares risk on each `@mcp.tool()` decorator. A cross-module registry is aggregated at sidecar startup for audit purposes but is not the source of truth. (Locked by convention; no separate RFC needed.)

## Decision log

- 2026-04-15 (claude): initial draft and accepted. Depends on RFC-0002 for the step input contract.
