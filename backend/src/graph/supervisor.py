"""Supervisor routing node.

Invariant: at most one call to ``record_agent_selection`` per invocation.
Every return path constructs exactly one ``RoutingDecision`` and logs it.
The LLM is invoked only when ``decide_routing`` returns
``reason="ambiguous"`` — otherwise the deterministic winner wins.
"""

from typing import Any, Optional
import json
import re

from langchain_core.messages import SystemMessage, RemoveMessage

from src.core.state import AgentState
from src.core.llm_factory import get_llm
from src.core.config import system_logger
from src.agents.swarm_manifest import SWARM_REGISTRY
from src.agents.task_classifier import candidate_agents_for_state, routing_inputs_for_state
from src.agents.capabilities import (
    RoutingDecision,
    decide_routing,
    explain_agent_choice,
    record_agent_selection,
)
from src.planning.planner import active_plan_step, public_plan, start_active_step
from src.core.quant_amp.doctrine import AtomicManager
from src.core.quant_amp.qasir import QASIRCompiler
from src.runtime.aps import PrecisionManager


AGENT_NAMES = list(SWARM_REGISTRY.keys())


def _finalize(
    decision: RoutingDecision,
    *,
    extra: Optional[dict] = None,
) -> dict[str, Any]:
    """Apply a routing decision: record selection exactly once, build the
    agent_selection payload (including the routing decision record), and
    return the state update dict."""
    record_agent_selection(decision.selected)
    selection = explain_agent_choice(
        decision.selected,
        decision.required_capabilities,
        risk=decision.risk,
        reason=_human_reason(decision),
    )
    selection["routing_decision"] = decision.model_dump()
    system_logger.info(
        f"Supervisor routed -> [{decision.selected}] reason={decision.reason} "
        f"candidates={decision.candidates} scores={decision.scores}"
    )
    result: dict[str, Any] = {
        "current_step_id": decision.selected,
        "active_worker": decision.selected,
        "agent_selection": selection,
    }
    if extra:
        result.update(extra)
    return result


def _human_reason(decision: RoutingDecision) -> str:
    mapping = {
        "token_safety_valve": "Automatic context-compaction safety valve.",
        "plan_step": "Deterministic plan step assignment.",
        "handoff_request": "Explicit [REQUEST_SPECIALIST:] handoff.",
        "preferred_agent": "Plan step's assigned agent covers the capabilities.",
        "single_candidate": "Only one agent covers the required capabilities.",
        "sticky": "Active worker still covers the required capabilities.",
        "score_winner": "Highest coverage score by a clear margin.",
        "llm_tiebreaker": "LLM chose from the ambiguous shortlist.",
        "fallback": "No capability match — falling back to orchestration.",
        "ambiguous": "Multiple equally-qualified candidates.",
    }
    return mapping.get(decision.reason, decision.reason)


def supervisor_node(state: AgentState) -> dict[str, Any]:
    system_logger.info("Executing -> [supervisor_node]")

    # --- [QUANTAMP INTEGRATION: APS] Sensor Sweep -------------------------
    aps_state = PrecisionManager.sense_environment()
    aps_weights = PrecisionManager.get_pulse_weights(aps_state)
    target_workers = PrecisionManager.get_target_worker_count(aps_state)
    
    system_logger.info(f"APS RESOURCE SENSE: state={aps_state} target_workers={target_workers}")
    # The supervisor can now pass these weights into the state or use them to 
    # throttle worker selection if the system were multi-threaded.

    # --- 0. [QUANTAMP INTEGRATION] AMP-Q Orchestration Turn ----------
    if state.get("amp_q_correlation_id"):
        # We are in the middle of an atomic task.
        # Check if we should continue or finalize.
        # (This logic will be expanded to handle multi-segment looping)
        pass

    # --- 1. Token compaction safety valve ---------------------------------
    tokens = state.get("cumulative_tokens")
    if tokens and tokens.total_tokens >= 240000 and state.get("active_worker") != "Memory_Archivist_Agent":
        system_logger.warning(
            f"CRITICAL: Context limit [240k] triggered ({tokens.total_tokens}). Forcing Compactor Turn."
        )
        decision = RoutingDecision(
            reason="token_safety_valve",
            selected="Memory_Archivist_Agent",
            candidates=["Memory_Archivist_Agent"],
            active_worker=state.get("active_worker"),
            required_capabilities=["memory", "context_compression"],
            risk="low",
            reason_detail=f"cumulative_tokens={tokens.total_tokens}",
        )
        return _finalize(decision)

    # --- 2. Deterministic plan step ---------------------------------------
    run_plan = state.get("run_plan")
    if run_plan:
        planned = start_active_step(run_plan)
        active_step = active_plan_step(planned)
        if not active_step:
            system_logger.info("Deterministic plan has no remaining active step. Finishing run.")
            return {"current_step_id": "FINISH", "run_plan": public_plan(planned)}

        required = [c.name for c in active_step.required_capabilities]
        risk = planned.risk if planned else "low"
        decision = decide_routing(
            required,
            risk=risk,
            available_agents=SWARM_REGISTRY.keys(),
            active_worker=state.get("active_worker"),
            preferred_agent=active_step.assigned_agent,
        )
        # A plan step's assigned_agent is authoritative — record the reason
        # as ``plan_step`` for audit clarity even when decide_routing took a
        # different branch (preferred_agent, single_candidate, etc).
        decision.reason = "plan_step"
        decision.reason_detail = f"step='{active_step.title}' assigned='{active_step.assigned_agent}'"
        return _finalize(
            decision,
            extra={
                "run_plan": public_plan(planned),
                "current_plan_step": planned.current_step_id,
            },
        )

    # --- 3. Handoff interception ------------------------------------------
    messages = state.get("messages", [])
    last_agent_msg = next(
        (m.content for m in reversed(messages) if getattr(m, "type", "") == "ai"),
        None,
    )
    if last_agent_msg and "[REQUEST_SPECIALIST:" in last_agent_msg:
        match = re.search(r"\[REQUEST_SPECIALIST:\s*([^\]]+)\]", last_agent_msg)
        if match:
            requested = match.group(1).strip()
            if requested in SWARM_REGISTRY:
                decision = RoutingDecision(
                    reason="handoff_request",
                    selected=requested,
                    candidates=[requested],
                    active_worker=state.get("active_worker"),
                    required_capabilities=[],
                    risk="low",
                    reason_detail="agent emitted an explicit handoff marker",
                )
                return _finalize(decision)

    # --- 4. Deterministic selection pipeline ------------------------------
    inputs = routing_inputs_for_state(state)

    # --- [QUANTAMP INTEGRATION: QA-SIR] Intent Compilation -----------------
    objective = inputs.get("objective", "")
    if objective:
        # Detect label for SLL mapping (e.g. "FIX:", "FEATURE:")
        label_match = re.match(r"^([A-Z]+):", objective)
        label = label_match.group(1) if label_match else None
        
        # Compile intent into a logic atom
        try:
            atom = QASIRCompiler.compile_intent(objective, label=label)
            system_logger.info(f"QA-SIR COMPILATION: signature={atom.signature[:8]}... logic_type={atom.metadata.get('logic_type')}")
            
            # Enrich inputs with compiled priority.
            #
            # QA-SIR assigns a 0.0–1.0 priority to every compiled intent. When
            # that priority exceeds 0.8 we treat the task as "high risk" for
            # routing purposes — it bumps the decision toward senior agents
            # and tighter review gates. The upgrade is explicit (and logged)
            # so it shows up in postmortems; silently mutating `inputs["risk"]`
            # is the class of bug that makes QA-SIR impossible to debug.
            if "priority" in atom.metadata:
                priority = atom.metadata["priority"]
                previous_risk = inputs["risk"]
                if priority > 0.8 and previous_risk != "high":
                    system_logger.info(
                        "QA-SIR RISK ESCALATION: %s -> high "
                        "(priority=%.3f, signature=%s)",
                        previous_risk,
                        priority,
                        atom.signature[:8],
                    )
                    inputs["risk"] = "high"
        except Exception as e:
            system_logger.error(f"QA-SIR COMPILATION FAILED: {e}")

    # If there's nothing to do (no message text, no plan) route to proxy.
    if not objective.strip():
        decision = RoutingDecision(
            reason="fallback",
            selected="Human_Proxy_Agent",
            candidates=["Human_Proxy_Agent"],
            active_worker=inputs["active_worker"],
            required_capabilities=["conversation"],
            risk="low",
            reason_detail="no objective / capabilities inferred",
        )
        return _finalize(decision)

    decision = decide_routing(
        inputs["required_capabilities"],
        risk=inputs["risk"],
        available_agents=SWARM_REGISTRY.keys(),
        active_worker=inputs["active_worker"],
    )

    if decision.reason != "ambiguous":
        # Check if this deterministic win needs atomic treatment
        objective = inputs.get("objective", "")
        if AtomicManager.needs_atomic_treatment(objective):
            system_logger.warning(f"AMP-Q TRIGGERED: Task exceeds context ripple. Initiating Atomic Protocol.")
            correlation_id = AtomicManager.generate_correlation_id()
            return _finalize(decision, extra={
                "amp_q_correlation_id": correlation_id,
                "amp_q_context": f"INITIALIZED::{correlation_id}"
            })
        return _finalize(decision)

    # --- 5. LLM tiebreaker (only reached on genuine ambiguity) ------------
    shortlist = decision.candidates
    agent_desc = "\n".join(
        f"- {name}: {SWARM_REGISTRY[name].description}" for name in shortlist if name in SWARM_REGISTRY
    )
    sys_prompt = SystemMessage(content=(
        "You are the ALOS Swarm Supervisor acting as a tiebreaker.\n"
        "Deterministic scoring already narrowed the choice to a short list of "
        "equally-qualified specialists. Pick the single best fit for the user's "
        "latest message. Do not invent an agent name.\n\n"
        f"Shortlist:\n{agent_desc}\n\n"
        'Return ONLY JSON: {"next_target": "<agent_name>", "why": "<one sentence>"}'
    ))
    filtered = [m for m in messages if not isinstance(m, (SystemMessage, RemoveMessage))]

    llm_choice = shortlist[0]
    llm_why = None
    try:
        llm = get_llm().bind(response_format={"type": "json_object"})
        response = llm.invoke([sys_prompt] + filtered)
        payload = json.loads(response.content)
        candidate = payload.get("next_target", "")
        if candidate in shortlist:
            llm_choice = candidate
            llm_why = payload.get("why")
    except Exception as exc:
        system_logger.error(f"Supervisor LLM tiebreaker crashed: {exc}. Falling back to top-scored candidate.")

    decision.reason = "llm_tiebreaker"
    decision.selected = llm_choice
    decision.reason_detail = llm_why
    return _finalize(decision)
