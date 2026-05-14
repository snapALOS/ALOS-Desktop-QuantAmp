from langchain_core.messages import HumanMessage

from src.agents.swarm_manifest import SWARM_REGISTRY
from src.agents.capabilities import (
    build_minimal_agent_set,
    infer_capabilities_from_text,
    minimal_agents_for_plan,
)
from src.core.state import AgentState
from src.planning.planner import classify_risk


def _latest_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            return str(getattr(message, "content", "") or "")
    return str(state.get("current_objective") or "")


def required_capabilities_for_state(state: AgentState) -> list[str]:
    run_plan = state.get("run_plan")
    if run_plan:
        candidates = minimal_agents_for_plan(run_plan, available_agents=SWARM_REGISTRY.keys(), limit=12)
        capabilities: list[str] = []
        for agent_name in candidates:
            blueprint = SWARM_REGISTRY.get(agent_name)
            if not blueprint:
                continue
            for capability in blueprint.capabilities:
                if capability not in capabilities:
                    capabilities.append(capability)
        return capabilities
    return infer_capabilities_from_text(_latest_human_text(state))


def candidate_agents_for_state(state: AgentState, limit: int = 7) -> list[str]:
    run_plan = state.get("run_plan")
    if run_plan:
        return minimal_agents_for_plan(run_plan, available_agents=SWARM_REGISTRY.keys(), limit=limit)

    objective = _latest_human_text(state)
    if not objective.strip():
        return ["Human_Proxy_Agent"]

    capabilities = infer_capabilities_from_text(objective)
    risk = classify_risk(objective)
    return build_minimal_agent_set(
        capabilities,
        risk=risk,
        available_agents=SWARM_REGISTRY.keys(),
        limit=limit,
        prefer_agent=state.get("active_worker") or None,
    )


def routing_inputs_for_state(state: AgentState) -> dict:
    """Bundle the inputs the supervisor needs to call ``decide_routing``.

    Returns ``{required_capabilities, risk, objective, active_worker}``.
    The capability list is derived from the active run plan when present,
    otherwise inferred from the latest human message.
    """
    objective = _latest_human_text(state)
    active_worker = state.get("active_worker") or None
    run_plan = state.get("run_plan")
    if run_plan:
        required = required_capabilities_for_state(state)
        risk = str(run_plan.get("risk", "low") if isinstance(run_plan, dict) else getattr(run_plan, "risk", "low"))
    else:
        required = infer_capabilities_from_text(objective)
        risk = classify_risk(objective)
    return {
        "required_capabilities": required,
        "risk": risk,
        "objective": objective,
        "active_worker": active_worker,
    }
