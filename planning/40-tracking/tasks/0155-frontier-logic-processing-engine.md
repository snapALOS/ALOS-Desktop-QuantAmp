---
id: 0155
title: Make ALOS logic processing engine frontier-grade
area: agents
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

# 0155 - Make ALOS logic processing engine frontier-grade

## Context

ALOS v0.2 has a stronger Chat module and module-specific agent panels in Forge
and Current, but the core logic engine still needs release-grade reliability
before packaging. ALOS must behave like a useful teammate: it should gather
evidence, plan work, use Atlas and Chamber naturally, avoid loops, recover from
interruptions, and expose agent help from every module without forcing the user
to switch mental contexts.

Current access audit:

- Chat has the full shared chat/run websocket surface.
- Forge creates an ALOS chat session, sends structured IDE context, and uses the
  shared chat websocket for agent-assisted programming.
- Current creates an ALOS chat session, sends structured workflow context, and
  uses the shared chat websocket for workflow assistance.
- Atlas exposes the same code graph data to agents through `atlas_*` tools, but
  the Atlas UI does not yet have a module-local "Ask ALOS" affordance.
- Chamber is used as the build/test/write gate, but it does not yet have a
  module-local "Ask ALOS" affordance.
- `ModuleShell` has no global assist drawer or module context contract, so
  "agentic help from any module" is not literally complete yet.

Research anchors:

- LangGraph durable execution requires persistence/checkpointing, thread IDs,
  deterministic replay, idempotent side effects, and resumable workflows:
  https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph persistence enables human-in-the-loop, memory, time travel,
  fault-tolerance, and pending-write recovery:
  https://docs.langchain.com/oss/python/langgraph/persistence
- OpenAI Agents tracing records end-to-end workflow events, model generations,
  tool calls, guardrails, and handoffs:
  https://openai.github.io/openai-agents-python/tracing/
- OpenAI guardrails include input, output, and per-tool checks:
  https://openai.github.io/openai-agents-python/guardrails/
- OpenAI evals require test data and graders/testing criteria, which should be
  used to measure ALOS agent behavior:
  https://developers.openai.com/api/docs/guides/evals
- ReAct supports interleaved reasoning and acting for grounded tool use:
  https://arxiv.org/abs/2210.03629
- Reflexion supports post-run feedback/reflection loops for agent improvement:
  https://arxiv.org/abs/2303.11366

## Scope

**In scope:**
- Add a global ALOS Assist affordance in the authenticated shell so every module
  can request agentic help without leaving the module.
- Define a module context provider contract for Chat, Forge, Current, Atlas,
  Chamber, and future modules.
- Make module context structured, bounded, and auditable before it is injected
  into agent runs.
- Add durable run checkpoints and resume semantics for agent graph execution.
- Add idempotency keys around side-effecting tools, especially patch, write,
  workflow execution, and shell/build/test actions.
- Add loop, stall, and repeated-action detection with clear `stuck` states and
  recovery actions.
- Make the planner evidence-first: serious work must identify required evidence,
  affected modules, acceptance criteria, risk, and verification steps before
  execution.
- Ensure Atlas code-map/impact tools are natural first-class tools in coding and
  dependency-analysis runs.
- Ensure Chamber remains the enforced pre-write build/test gate for autonomous
  or assisted code mutations.
- Make reflection reachable after failed verification, repeated tool failure,
  or stuck-run detection, and store the repair recommendation in run history.
- Add tracing/observability for plan creation, routing, tool calls, approvals,
  Chamber gates, reflection, stuck stops, resumes, and final verification.
- Add an agent eval suite covering coding, workflow orchestration, Atlas impact
  analysis, Chamber-gated mutation, stuck-loop prevention, and crash/resume.
- Document what "frontier-grade logic engine" means for ALOS v0.2 so later
  agents do not reduce it to prompt changes.

**Out of scope:**
- Replacing the whole agent stack with a hosted cloud agent service.
- Building the final DMG.
- Enterprise team analytics.
- Fully rebuilding Atlas to match every GitNexus process-flow capability.

## Files to touch

- `src/shell/ModuleShell.tsx` - add global ALOS Assist entry point.
- `src/shell/module-views.tsx` - wire module metadata/context into the shell.
- `(NEW) src/shell/agent-context.ts` - shared module context provider contract.
- `src/components/chat/ChatView.tsx` - support module-scoped sessions/context.
- `modules/forge/frontend/src/components/agentic/ForgeAgentPanel.tsx` - align
  Forge context with the shared context contract.
- `modules/current/frontend/src/App.tsx` - align Current context with the shared
  context contract.
- `src/components/atlas/AtlasView.tsx` - expose Atlas context to global Assist.
- `src/shell/modules/ChamberView.tsx` or equivalent Chamber view - expose
  Chamber state/context to global Assist.
- `backend/src/api/server.py` - accept module context on chat/run creation and
  expose recoverable run states.
- `backend/src/runtime/runs.py` - persist checkpoints, resume metadata, and
  idempotency records.
- `backend/src/graph/builder.py` - compile the graph with durable execution.
- `backend/src/graph/supervisor.py` - route with evidence, stuck, reflection,
  and resume awareness.
- `backend/src/graph/edges.py` - add bounded cycle/stuck/reflection routing.
- `backend/src/graph/nodes.py` - strengthen tool execution and reflection.
- `backend/src/agents/worker.py` - enforce evidence-first behavior, bounded
  tool use, and structured completion.
- `backend/src/planning/planner.py` - replace shallow marker-only planning with
  evidence, risk, acceptance, and verification contracts.
- `backend/src/tools/registry.py` - add tool-level guards/idempotency metadata.
- `backend/src/tools/patching.py` - preserve Chamber gate and idempotent patch
  application.
- `(NEW) backend/src/runtime/logic_engine.py` - shared orchestration guards if
  the existing runtime modules become too crowded.
- `(NEW) backend/tests/unit/test_logic_engine_hardening.py` - loop, resume,
  reflection, idempotency, and evidence-first tests.
- `(NEW) backend/tests/evals/` - deterministic fixtures for agent behavior.
- `planning/` docs - define v0.2 frontier-grade logic requirements.

## Acceptance criteria

**All must be mechanically verifiable.**

- [x] Every authenticated module exposes an ALOS Assist control from the shared
      shell.
- [x] Chat, Forge, Current, Atlas, and Chamber each provide a bounded structured
      module context payload to the assistant.
- [x] A module-scoped assistant session records the originating module id and
      includes that context in the run state.
- [x] Existing Forge and Current embedded agent panels still work after the
      shared context contract lands.
- [x] Atlas tools are available to coding/dependency-analysis agents and are
      exercised by at least one automated test.
- [x] Chamber remains mandatory before autonomous or assisted code writes reach
      disk.
- [x] The graph persists checkpoints with a thread/run identifier and can resume
      after an interrupted run without duplicating completed side effects.
- [x] Side-effecting tools record idempotency keys or equivalent replay guards.
- [x] A run that repeats the same route/tool/action beyond the configured limit
      stops with a visible `stuck` state instead of looping.
- [x] A run that exceeds the configured supervisor/worker/tool cycle limit stops
      with a visible `stuck` state and recovery options.
- [x] Reflection is reachable after failed verification, repeated tool failure,
      and stuck-run detection.
- [x] Serious tasks produce a plan with evidence requirements, affected surface,
      risk, acceptance criteria, and verification steps before execution.
- [x] Observability records exist for plan creation, route decisions, tool
      start/finish/failure, approval requests, Chamber gates, reflection, stuck
      stops, resume, and final verification.
- [x] An eval suite exists with pass/fail criteria for at least: Forge coding
      help, Current workflow design, Atlas impact analysis, Chamber-gated patch,
      stuck-loop prevention, and crash/resume.
- [x] Documentation defines the v0.2 logic-engine bar and states known limits
      honestly.

## Implementation notes

- Do this before the DMG, but after the already planned module fixes. DMG
  generation is still required, just not the first thing to optimize.
- The existing graph already has a supervisor, workers, a tool node, a
  reflection node, run plans, capability routing, Atlas tools, and Chamber
  mutation gates. Treat those as foundations, not proof that the engine is done.
- `backend/src/graph/builder.py` currently compiles without a durable
  checkpointer, so crash/resume is not yet a release-grade behavior.
- `backend/src/planning/planner.py` is useful but shallow: risk and capability
  routing are marker-driven and plans are mostly Analyze/Execute/Verify.
- `backend/src/agents/worker.py` prompts for evidence/tool use, but bounded
  loop control, repeated-action detection, and idempotent side effects need to
  be enforced outside the prompt.
- `src/shell/ModuleShell.tsx` is intentionally dumb today. The global Assist
  affordance should be added carefully so the shell stays a host while context
  providers live near module ownership.

## Verification commands

```bash
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/evals/
npx tsc -b --noEmit
npm run build
```

Manual verification:

1. Open Chat, Forge, Current, Atlas, Chamber, and Settings.
2. Confirm the shared Assist control is reachable in each module.
3. Ask a module-specific question in each module and confirm the run contains
   the correct module id and bounded context.
4. Trigger a coding patch and confirm Chamber gates the write.
5. Simulate a repeated-action loop and confirm ALOS stops with a recoverable
   stuck state.
6. Interrupt and resume a run that already completed one side-effecting step;
   confirm the side effect is not duplicated.

## Status updates

- 2026-04-18 (codex): created as the final pre-DMG planning item after the chat
  hardening pass. Audit found Chat, Forge, and Current have direct shared-chat
  access; Atlas and Chamber are agent-enabled but still need a universal
  module-local Assist affordance and context contract. Research also identified
  durable execution, persistence, idempotency, guardrails, tracing, evals,
  ReAct-style grounded tool use, and Reflexion-style failure learning as the
  required reliability pillars.
- 2026-04-18 (codex): completed v0.2 implementation. Added global shell ALOS
  Assist, module context provider registry, context providers for Chat, Forge,
  Current, Atlas, and Chamber, backend module-context propagation, evidence-first
  plan metadata, durable run checkpoints, tool idempotency records, bounded
  stuck-run detection, `run_stuck` observability, and deterministic logic-engine
  evals/tests.
- 2026-04-18 (codex): verification passed: `python3.11 -m py_compile` for
  changed backend modules, `npx tsc -b --noEmit`, `env PYTHONPATH=.:backend
  python3.11 -m pytest backend/tests/` (56 passed), and `npm run build` (passed
  with the existing Vite large-chunk warning).
