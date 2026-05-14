from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from pydantic import BaseModel, Field


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# A routing decision is "ambiguous" when the top two candidate coverage
# scores differ by less than this epsilon. Below the threshold, the
# supervisor hands the final pick to the LLM tiebreaker; at or above, the
# deterministic top scorer wins with no LLM call.
AMBIGUITY_EPSILON = 0.5

# Stickiness bonus: prefer the currently-active worker if it can cover
# the required capabilities, so we don't churn agents between turns.
ACTIVE_WORKER_BONUS = 0.4


class CapabilityPolicyViolation(Exception):
    """Raised when an agent attempts an action outside its capability policy."""


class AgentPerformanceCounters(BaseModel):
    selected: int = 0
    completed: int = 0
    failed: int = 0
    tool_allowed: int = 0
    tool_denied: int = 0


class RoutingDecision(BaseModel):
    """Audit record for a single routing decision.

    `reason` is one of:
      - "token_safety_valve"  — forced compactor turn
      - "plan_step"           — deterministic plan assignment
      - "handoff_request"     — `[REQUEST_SPECIALIST: ...]` intercepted
      - "single_candidate"    — only one agent covers the capabilities
      - "sticky"              — active worker covers & is within epsilon of top
      - "score_winner"        — top scorer wins by >= epsilon
      - "preferred_agent"     — caller passed preferred_agent and it qualified
      - "fallback"            — nothing scored; Human_Proxy_Agent / orchestrators
      - "ambiguous"           — top candidates tied; LLM tiebreaker required
      - "llm_tiebreaker"      — LLM picked from the ambiguous shortlist
    """
    reason: str
    selected: str
    candidates: List[str] = Field(default_factory=list)
    scores: Dict[str, float] = Field(default_factory=dict)
    active_worker: Optional[str] = None
    required_capabilities: List[str] = Field(default_factory=list)
    risk: str = "low"
    reason_detail: Optional[str] = None


class AgentCapabilityPolicy(BaseModel):
    agent_name: str
    capabilities: List[str] = Field(default_factory=list)
    max_risk: str = "medium"
    allowed_tools: List[str] = Field(default_factory=list)
    fallback_agents: List[str] = Field(default_factory=list)
    selection_weight: float = 1.0

    def allows_risk(self, risk: str) -> bool:
        return RISK_ORDER.get(risk or "low", 0) <= RISK_ORDER.get(self.max_risk, 1)

    def allows_tool(self, tool_name: str) -> bool:
        return tool_name in set(self.allowed_tools)


STATIC_AGENT_POLICIES: Dict[str, AgentCapabilityPolicy] = {
    "Project_Manager_Agent": AgentCapabilityPolicy(
        agent_name="Project_Manager_Agent",
        capabilities=["planning", "task_breakdown", "coordination"],
        max_risk="high",
        allowed_tools=[
            "read_local_directory", "read_file_content",
            "atlas_search", "atlas_status",
        ],
        fallback_agents=["Technical_Architect_Agent", "Human_Proxy_Agent"],
    ),
    "Technical_Architect_Agent": AgentCapabilityPolicy(
        agent_name="Technical_Architect_Agent",
        capabilities=["architecture_mapping", "api_design", "code_reading", "planning"],
        max_risk="high",
        allowed_tools=[
            "read_local_directory", "read_file_content", "propose_patch",
            "atlas_search", "atlas_context", "atlas_impact", "atlas_file_context", "atlas_report",
        ],
        fallback_agents=["File_Map_Agent", "Project_Manager_Agent"],
        selection_weight=1.12,
    ),
    "Python_Backend_Agent": AgentCapabilityPolicy(
        agent_name="Python_Backend_Agent",
        capabilities=["python_backend", "api_implementation", "fastapi", "coding", "patching"],
        max_risk="high",
        allowed_tools=["propose_patch", "read_file_content", "read_local_directory", "execute_sandboxed_python", "write_system_file"],
        fallback_agents=["Code_Refactor_Agent", "Technical_Architect_Agent"],
        selection_weight=1.18,
    ),
    "Frontend_UI_Agent": AgentCapabilityPolicy(
        agent_name="Frontend_UI_Agent",
        capabilities=["frontend_ui", "dom_interaction", "css", "javascript", "patching"],
        max_risk="high",
        allowed_tools=["propose_patch", "read_file_content", "read_local_directory", "write_system_file"],
        fallback_agents=["UX_Critic_Agent", "Code_Refactor_Agent"],
        selection_weight=1.18,
    ),
    "Database_Engineer_Agent": AgentCapabilityPolicy(
        agent_name="Database_Engineer_Agent",
        capabilities=["database", "sql", "schema_design", "migration", "vector_memory", "patching"],
        max_risk="high",
        allowed_tools=["propose_patch", "read_file_content", "read_local_directory", "write_system_file"],
        fallback_agents=["Python_Backend_Agent", "Technical_Architect_Agent"],
        selection_weight=1.12,
    ),
    "Code_Refactor_Agent": AgentCapabilityPolicy(
        agent_name="Code_Refactor_Agent",
        capabilities=["refactor", "optimization", "coding", "patching"],
        max_risk="high",
        allowed_tools=[
            "propose_patch", "read_file_content", "read_local_directory", "write_system_file",
            "atlas_search", "atlas_context", "atlas_impact",
        ],
        fallback_agents=["Python_Backend_Agent", "O_Complexity_Agent"],
    ),
    "DocString_Auditor_Agent": AgentCapabilityPolicy(
        agent_name="DocString_Auditor_Agent",
        capabilities=["documentation", "docstrings", "readme", "patching"],
        max_risk="medium",
        allowed_tools=["propose_patch", "read_file_content", "read_local_directory", "write_system_file"],
        fallback_agents=["Technical_Architect_Agent", "Project_Manager_Agent"],
    ),
    "File_Map_Agent": AgentCapabilityPolicy(
        agent_name="File_Map_Agent",
        capabilities=["file_mapping", "code_reading", "repository_inspection"],
        max_risk="medium",
        allowed_tools=[
            "read_local_directory", "read_file_content",
            "atlas_search", "atlas_file_context", "atlas_status",
        ],
        fallback_agents=["Technical_Architect_Agent"],
    ),
    "Web_Crawler_Agent": AgentCapabilityPolicy(
        agent_name="Web_Crawler_Agent",
        capabilities=["web_research", "html_scraping", "external_research"],
        max_risk="medium",
        allowed_tools=["scrape_html_text", "web_search", "read_file_content", "read_local_directory"],
        fallback_agents=["API_Hunter_Agent", "Data_Synthesizer_Agent"],
    ),
    "API_Hunter_Agent": AgentCapabilityPolicy(
        agent_name="API_Hunter_Agent",
        capabilities=["api_research", "external_api_mapping", "web_research"],
        max_risk="medium",
        allowed_tools=["web_search", "scrape_html_text", "read_file_content", "read_local_directory"],
        fallback_agents=["Web_Crawler_Agent", "Technical_Architect_Agent"],
    ),
    "Competitor_Analysis_Agent": AgentCapabilityPolicy(
        agent_name="Competitor_Analysis_Agent",
        capabilities=["competitor_analysis", "benchmarking", "web_research"],
        max_risk="medium",
        allowed_tools=["web_search", "read_file_content", "read_local_directory"],
        fallback_agents=["Data_Synthesizer_Agent", "Web_Crawler_Agent"],
    ),
    "Data_Synthesizer_Agent": AgentCapabilityPolicy(
        agent_name="Data_Synthesizer_Agent",
        capabilities=["synthesis", "summarization", "research_compression"],
        max_risk="medium",
        allowed_tools=["read_file_content", "read_local_directory"],
        fallback_agents=["Memory_Archivist_Agent", "Project_Manager_Agent"],
    ),
    "Bash_Command_Agent": AgentCapabilityPolicy(
        agent_name="Bash_Command_Agent",
        capabilities=["shell", "command_execution", "local_system"],
        max_risk="critical",
        allowed_tools=["execute_system_bash", "read_file_content", "read_local_directory"],
        fallback_agents=["Dependency_Agent", "LocalNetwork_Agent"],
    ),
    "Git_Ops_Agent": AgentCapabilityPolicy(
        agent_name="Git_Ops_Agent",
        capabilities=["git", "version_control", "rollback", "patching"],
        max_risk="critical",
        allowed_tools=["execute_system_bash", "git_targeted_revert", "read_file_content", "read_local_directory", "propose_patch"],
        fallback_agents=["Bash_Command_Agent", "Project_Manager_Agent"],
    ),
    "Dependency_Agent": AgentCapabilityPolicy(
        agent_name="Dependency_Agent",
        capabilities=["dependency", "package_management", "environment_repair"],
        max_risk="critical",
        allowed_tools=["execute_system_bash", "read_file_content", "read_local_directory", "propose_patch"],
        fallback_agents=["Bash_Command_Agent", "Deployment_Agent"],
    ),
    "Deployment_Agent": AgentCapabilityPolicy(
        agent_name="Deployment_Agent",
        capabilities=["deployment", "installer", "launcher", "packaging", "patching"],
        max_risk="high",
        allowed_tools=["propose_patch", "read_file_content", "read_local_directory", "write_system_file", "execute_system_bash"],
        fallback_agents=["Dependency_Agent", "Technical_Architect_Agent"],
    ),
    "LocalNetwork_Agent": AgentCapabilityPolicy(
        agent_name="LocalNetwork_Agent",
        capabilities=["network_diagnostics", "port_diagnostics", "websocket", "local_system"],
        max_risk="critical",
        allowed_tools=["execute_system_bash", "read_file_content", "read_local_directory"],
        fallback_agents=["Bash_Command_Agent", "Python_Backend_Agent"],
    ),
    "Unit_Tester_Agent": AgentCapabilityPolicy(
        agent_name="Unit_Tester_Agent",
        capabilities=["testing", "verification", "pytest", "regression", "patching"],
        max_risk="high",
        allowed_tools=["propose_patch", "execute_system_bash", "write_system_file", "read_file_content", "read_local_directory"],
        fallback_agents=["Sanity_Check_Agent", "Python_Backend_Agent"],
        selection_weight=1.08,
    ),
    "StackTrace_Agent": AgentCapabilityPolicy(
        agent_name="StackTrace_Agent",
        capabilities=["debugging", "stacktrace", "failure_analysis", "code_reading"],
        max_risk="medium",
        allowed_tools=[
            "read_file_content", "read_local_directory",
            "atlas_search", "atlas_context", "atlas_impact",
        ],
        fallback_agents=["Code_Refactor_Agent", "Reflection_Guard_Agent"],
    ),
    "Security_Auditor_Agent": AgentCapabilityPolicy(
        agent_name="Security_Auditor_Agent",
        capabilities=["security", "trust_boundary", "secret_review", "code_reading"],
        max_risk="critical",
        allowed_tools=[
            "read_file_content", "read_local_directory",
            "atlas_search", "atlas_context", "atlas_impact", "atlas_report",
        ],
        fallback_agents=["Technical_Architect_Agent", "Human_Proxy_Agent"],
        selection_weight=1.1,
    ),
    "O_Complexity_Agent": AgentCapabilityPolicy(
        agent_name="O_Complexity_Agent",
        capabilities=["complexity_analysis", "performance", "optimization", "patching"],
        max_risk="high",
        allowed_tools=["read_file_content", "read_local_directory", "propose_patch", "write_system_file"],
        fallback_agents=["Code_Refactor_Agent", "Python_Backend_Agent"],
    ),
    "UX_Critic_Agent": AgentCapabilityPolicy(
        agent_name="UX_Critic_Agent",
        capabilities=["ux_review", "frontend_review", "code_reading"],
        max_risk="high",
        allowed_tools=["read_file_content", "read_local_directory"],
        fallback_agents=["Frontend_UI_Agent", "Sanity_Check_Agent"],
        selection_weight=1.05,
    ),
    "Memory_Archivist_Agent": AgentCapabilityPolicy(
        agent_name="Memory_Archivist_Agent",
        capabilities=["memory", "summarization", "context_compression"],
        max_risk="medium",
        allowed_tools=["read_file_content", "read_local_directory"],
        fallback_agents=["Data_Synthesizer_Agent", "Human_Proxy_Agent"],
    ),
    "Dynamic_Tool_Agent": AgentCapabilityPolicy(
        agent_name="Dynamic_Tool_Agent",
        capabilities=["tooling", "tool_registry", "patching", "python_backend"],
        max_risk="high",
        allowed_tools=["propose_patch", "read_file_content", "read_local_directory", "write_system_file"],
        fallback_agents=["Python_Backend_Agent", "Security_Auditor_Agent"],
    ),
    "Reflection_Guard_Agent": AgentCapabilityPolicy(
        agent_name="Reflection_Guard_Agent",
        capabilities=["loop_guard", "failure_analysis", "orchestration_safety"],
        max_risk="medium",
        allowed_tools=["read_file_content", "read_local_directory"],
        fallback_agents=["StackTrace_Agent", "Sanity_Check_Agent"],
    ),
    "Human_Proxy_Agent": AgentCapabilityPolicy(
        agent_name="Human_Proxy_Agent",
        capabilities=["conversation", "clarification", "human_handoff"],
        max_risk="critical",
        allowed_tools=["read_file_content", "read_local_directory"],
        fallback_agents=["Project_Manager_Agent"],
    ),
    "Sanity_Check_Agent": AgentCapabilityPolicy(
        agent_name="Sanity_Check_Agent",
        capabilities=["verification", "sanity_check", "file_mapping", "local_system"],
        max_risk="critical",
        allowed_tools=[
            "read_local_directory", "read_file_content", "execute_system_bash",
            "atlas_impact", "atlas_status", "atlas_report",
        ],
        fallback_agents=["Unit_Tester_Agent", "Technical_Architect_Agent"],
        selection_weight=1.05,
    ),
}


KEYWORD_CAPABILITY_MAP: Sequence[tuple[Set[str], Sequence[str]]] = (
    ({"frontend", "ui", "css", "html", "style", "styles", "responsive", "browser"}, ("frontend_ui", "ux_review")),
    ({"javascript", "app.js", "dom"}, ("frontend_ui", "testing")),
    ({"python", "fastapi", "backend", "server", "websocket"}, ("python_backend", "api_implementation")),
    ({"api", "endpoint", "route"}, ("api_design", "python_backend")),
    ({"database", "sqlite", "sql", "schema", "migration", "db"}, ("database", "schema_design")),
    ({"memory", "checkpoint", "semantic", "retrieval"}, ("memory", "vector_memory")),
    ({"security", "secret", "token", "api key", "permission", "trust"}, ("security", "trust_boundary")),
    ({"tool", "registry", "tools"}, ("tooling", "tool_registry")),
    ({"bash", "shell", "command", "terminal"}, ("shell",)),
    ({"dependency", "dependencies", "install", "venv", "pip", "npm", "package"}, ("dependency",)),
    ({"deploy", "launcher", "boot", "port", "installer", "packaging", "release"}, ("deployment", "installer")),
    ({"test", "pytest", "jest", "eval", "regression", "verify"}, ("testing", "verification")),
    ({"bug", "error", "trace", "stack", "debug", "failure"}, ("debugging", "failure_analysis")),
    ({"refactor", "cleanup", "optimize", "performance"}, ("refactor", "optimization")),
    ({"docs", "document", "readme", "docstring"}, ("documentation",)),
    ({"search", "web", "scrape", "research"}, ("web_research", "synthesis")),
    ({"competitor", "openclaw", "benchmark"}, ("competitor_analysis", "benchmarking")),
    ({"plan", "phase", "roadmap"}, ("planning", "task_breakdown")),
)

_PERFORMANCE_COUNTERS: Dict[str, AgentPerformanceCounters] = defaultdict(AgentPerformanceCounters)
GLOBAL_READ_ONLY_TOOLS = ["scout_query"]


def _with_global_tools(policy: AgentCapabilityPolicy) -> AgentCapabilityPolicy:
    tools = list(dict.fromkeys([*policy.allowed_tools, *GLOBAL_READ_ONLY_TOOLS]))
    if tools == policy.allowed_tools:
        return policy
    payload = policy.model_dump() if hasattr(policy, "model_dump") else policy.dict()
    payload["allowed_tools"] = tools
    return AgentCapabilityPolicy(**payload)


def policy_for_agent(agent_name: str) -> AgentCapabilityPolicy:
    policy = STATIC_AGENT_POLICIES.get(
        agent_name,
        AgentCapabilityPolicy(
            agent_name=agent_name,
            capabilities=["general_execution"],
            max_risk="medium",
            fallback_agents=["Project_Manager_Agent", "Human_Proxy_Agent"],
        ),
    )
    return _with_global_tools(policy)


def policy_snapshot_for_agent(agent_name: str) -> Dict[str, Any]:
    policy = policy_for_agent(agent_name)
    return policy.model_dump() if hasattr(policy, "model_dump") else policy.dict()


def all_policy_snapshots() -> Dict[str, Dict[str, Any]]:
    return {agent_name: policy_snapshot_for_agent(agent_name) for agent_name in STATIC_AGENT_POLICIES}


def tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", "") or getattr(tool, "__name__", "") or tool)


def risk_allowed(agent_name: str, risk: str) -> bool:
    return policy_for_agent(agent_name).allows_risk(risk)


def tool_allowed(agent_name: str, tool: Any) -> bool:
    return policy_for_agent(agent_name).allows_tool(tool_name(tool))


def filter_tools_for_agent(agent_name: str, tools: Iterable[Any], risk: str = "low") -> List[Any]:
    policy = policy_for_agent(agent_name)
    if not policy.allows_risk(risk):
        return []
    allowed = set(policy.allowed_tools)
    return [tool for tool in tools if tool_name(tool) in allowed]


def enforce_tool_permission(agent_name: str, tool: Any, risk: str = "medium") -> None:
    name = tool_name(tool)
    policy = policy_for_agent(agent_name)
    if not policy.allows_risk(risk):
        raise CapabilityPolicyViolation(
            f"{agent_name} is limited to {policy.max_risk} risk and cannot execute {risk} risk tool work."
        )
    if name not in set(policy.allowed_tools):
        raise CapabilityPolicyViolation(f"{agent_name} is not permitted to call tool '{name}'.")


def infer_capabilities_from_text(text: str) -> List[str]:
    lowered = (text or "").lower()
    capabilities: List[str] = []
    for keywords, mapped_capabilities in KEYWORD_CAPABILITY_MAP:
        if any(keyword in lowered for keyword in keywords):
            for capability in mapped_capabilities:
                if capability not in capabilities:
                    capabilities.append(capability)
    if not capabilities:
        if any(word in lowered for word in ["hello", "hi ", "question", "explain", "what is", "thanks"]):
            return ["conversation"]
        return ["planning", "architecture_mapping"]
    return capabilities


def _coverage(agent_name: str, required_capabilities: Iterable[str]) -> Set[str]:
    policy_capabilities = set(policy_for_agent(agent_name).capabilities)
    return policy_capabilities & set(required_capabilities)


def _candidate_pool(available_agents: Iterable[str], risk: str) -> List[str]:
    return [agent for agent in available_agents if agent in STATIC_AGENT_POLICIES and risk_allowed(agent, risk)]


def fallback_agents_for(agent_name: str, available_agents: Iterable[str] = None, risk: str = "low") -> List[str]:
    available = set(available_agents or STATIC_AGENT_POLICIES.keys())
    fallbacks = []
    for fallback in policy_for_agent(agent_name).fallback_agents:
        if fallback in available and risk_allowed(fallback, risk):
            fallbacks.append(fallback)
    if "Human_Proxy_Agent" in available and "Human_Proxy_Agent" not in fallbacks:
        fallbacks.append("Human_Proxy_Agent")
    return fallbacks


def _score_agent(
    agent: str,
    covered: Set[str],
    *,
    prefer_agent: Optional[str] = None,
) -> float:
    policy = policy_for_agent(agent)
    counters = _PERFORMANCE_COUNTERS[agent]
    performance_penalty = min(counters.failed + counters.tool_denied, 5) * 0.03
    score = (len(covered) * 10.0) + policy.selection_weight - performance_penalty
    if prefer_agent and agent == prefer_agent:
        score += ACTIVE_WORKER_BONUS
    return score


def scored_agent_candidates(
    required_capabilities: Iterable[str],
    *,
    risk: str = "low",
    available_agents: Iterable[str] = None,
    prefer_agent: Optional[str] = None,
) -> List[tuple]:
    """Return all coverage-providing candidates scored against the required
    capability set. Result is a list of (score, agent, covered_set) tuples
    sorted by score desc, agent asc. Used by both ``build_minimal_agent_set``
    (greedy cover) and ``decide_routing`` (ambiguity detection).
    """
    available = list(available_agents or STATIC_AGENT_POLICIES.keys())
    required = {c for c in required_capabilities if c}
    if not required:
        required = {"conversation"}
    pool = _candidate_pool(available, risk)
    scored = []
    for agent in pool:
        covered = _coverage(agent, required)
        if not covered:
            continue
        scored.append((_score_agent(agent, covered, prefer_agent=prefer_agent), agent, covered))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored


def routing_is_ambiguous(
    scored: Sequence[tuple],
    active_worker: Optional[str] = None,
    *,
    epsilon: float = AMBIGUITY_EPSILON,
) -> bool:
    """Does this scored candidate list leave genuine room for the LLM?

    Ambiguous iff all of:
      - >= 2 candidates present;
      - top two scores within ``epsilon`` of each other;
      - the active worker (if any) is NOT the unique top scorer.
    """
    if len(scored) < 2:
        return False
    top_score = scored[0][0]
    second_score = scored[1][0]
    if (top_score - second_score) >= epsilon:
        return False
    if active_worker and scored[0][1] == active_worker and (top_score - second_score) > 0:
        return False
    return True


def build_minimal_agent_set(
    required_capabilities: Iterable[str],
    *,
    risk: str = "low",
    available_agents: Iterable[str] = None,
    limit: int = 7,
    prefer_agent: Optional[str] = None,
) -> List[str]:
    available = list(available_agents or STATIC_AGENT_POLICIES.keys())
    required = [capability for capability in dict.fromkeys(required_capabilities) if capability]
    if not required:
        required = ["conversation"]

    candidates = _candidate_pool(available, risk)
    selected: List[str] = []
    uncovered = set(required)

    while uncovered and len(selected) < limit:
        scored = []
        for agent in candidates:
            if agent in selected:
                continue
            covered = _coverage(agent, uncovered)
            if not covered:
                continue
            scored.append((_score_agent(agent, covered, prefer_agent=prefer_agent), agent, covered))
        if not scored:
            break
        _score, chosen, covered = sorted(scored, key=lambda item: (-item[0], item[1]))[0]
        selected.append(chosen)
        uncovered -= covered

    if uncovered:
        for fallback in ["Project_Manager_Agent", "Technical_Architect_Agent", "Human_Proxy_Agent"]:
            if fallback in available and fallback not in selected and risk_allowed(fallback, risk):
                selected.append(fallback)
                if len(selected) >= limit:
                    break

    if "verification" in required and "Sanity_Check_Agent" in available and "Sanity_Check_Agent" not in selected and risk_allowed("Sanity_Check_Agent", risk):
        selected.append("Sanity_Check_Agent")

    if not selected and "Human_Proxy_Agent" in available:
        selected.append("Human_Proxy_Agent")

    return selected[:limit]


def minimal_agents_for_plan(plan: Any, *, available_agents: Iterable[str] = None, limit: int = 7) -> List[str]:
    if not plan:
        return build_minimal_agent_set(["conversation"], available_agents=available_agents, limit=limit)
    risk = str(plan.get("risk", "low") if isinstance(plan, dict) else getattr(plan, "risk", "low"))
    steps = plan.get("steps", []) if isinstance(plan, dict) else getattr(plan, "steps", [])
    capabilities: List[str] = []
    assigned_agents: List[str] = []
    for step in steps:
        step_status = step.get("status") if isinstance(step, dict) else getattr(step, "status", "")
        if step_status not in {"pending", "running", "blocked"}:
            continue
        assigned = step.get("assigned_agent") if isinstance(step, dict) else getattr(step, "assigned_agent", "")
        if assigned and assigned not in assigned_agents:
            assigned_agents.append(assigned)
        required = step.get("required_capabilities", []) if isinstance(step, dict) else getattr(step, "required_capabilities", [])
        for capability in required:
            name = capability.get("name") if isinstance(capability, dict) else getattr(capability, "name", "")
            if name and name not in capabilities:
                capabilities.append(name)
    selected = build_minimal_agent_set(capabilities or ["planning"], risk=risk, available_agents=available_agents, limit=limit)
    for assigned in assigned_agents:
        if assigned in (available_agents or STATIC_AGENT_POLICIES.keys()) and assigned not in selected and risk_allowed(assigned, risk):
            selected.append(assigned)
    return selected[:limit]


def agent_satisfies_capabilities(agent_name: str, capabilities: Iterable[str], risk: str = "low") -> bool:
    if not risk_allowed(agent_name, risk):
        return False
    required = set(capabilities)
    return not required or bool(_coverage(agent_name, required))


def select_agent_for_capabilities(
    capabilities: Iterable[str],
    *,
    risk: str = "low",
    preferred_agent: str = "",
    available_agents: Iterable[str] = None,
) -> str:
    available = set(available_agents or STATIC_AGENT_POLICIES.keys())
    required = list(capabilities)
    if preferred_agent and preferred_agent in available and agent_satisfies_capabilities(preferred_agent, required, risk):
        return preferred_agent
    if preferred_agent:
        for fallback in fallback_agents_for(preferred_agent, available, risk):
            if agent_satisfies_capabilities(fallback, required, risk):
                return fallback
    candidates = build_minimal_agent_set(required, risk=risk, available_agents=available, limit=1)
    return candidates[0] if candidates else "Human_Proxy_Agent"


def decide_routing(
    required_capabilities: Iterable[str],
    *,
    risk: str = "low",
    available_agents: Iterable[str] = None,
    active_worker: Optional[str] = None,
    preferred_agent: Optional[str] = None,
    epsilon: float = AMBIGUITY_EPSILON,
) -> RoutingDecision:
    """Single entry point for deterministic agent selection.

    Returns a ``RoutingDecision`` whose ``reason`` tells the supervisor
    what to do next. When ``reason == "ambiguous"`` the ``candidates``
    field holds the shortlist the LLM tiebreaker should choose from (the
    supervisor must then fill in ``llm_tiebreaker``/``selected``).

    Selection precedence:
      1. ``preferred_agent`` if it covers the capabilities and passes risk.
      2. Sticky active worker if within epsilon of the top score.
      3. Single candidate → that candidate.
      4. Clear top scorer (gap >= epsilon) → score winner.
      5. Otherwise → ambiguous shortlist.
    """
    required = [c for c in dict.fromkeys(required_capabilities) if c]
    required_for_record = list(required) if required else ["conversation"]
    available_list = list(available_agents or STATIC_AGENT_POLICIES.keys())

    # Explicit caller preference (plan step's assigned_agent).
    if preferred_agent and preferred_agent in available_list \
            and agent_satisfies_capabilities(preferred_agent, required, risk):
        return RoutingDecision(
            reason="preferred_agent",
            selected=preferred_agent,
            candidates=[preferred_agent],
            scores={preferred_agent: _score_agent(
                preferred_agent,
                _coverage(preferred_agent, required or ["conversation"]),
                prefer_agent=active_worker,
            )},
            active_worker=active_worker,
            required_capabilities=required_for_record,
            risk=risk,
        )

    scored = scored_agent_candidates(
        required or ["conversation"],
        risk=risk,
        available_agents=available_list,
        prefer_agent=active_worker,
    )

    if not scored:
        fallback = "Human_Proxy_Agent" if "Human_Proxy_Agent" in available_list else (
            available_list[0] if available_list else "Human_Proxy_Agent"
        )
        return RoutingDecision(
            reason="fallback",
            selected=fallback,
            candidates=[fallback],
            scores={},
            active_worker=active_worker,
            required_capabilities=required_for_record,
            risk=risk,
            reason_detail="no candidate covered required capabilities",
        )

    scores_map = {agent: round(score, 4) for score, agent, _ in scored}
    candidate_names = [agent for _, agent, _ in scored]

    if len(scored) == 1:
        return RoutingDecision(
            reason="single_candidate",
            selected=candidate_names[0],
            candidates=candidate_names,
            scores=scores_map,
            active_worker=active_worker,
            required_capabilities=required_for_record,
            risk=risk,
        )

    top_score, top_agent, _ = scored[0]
    second_score = scored[1][0]
    gap = top_score - second_score

    # Sticky: active worker is ranked first (possibly via the stickiness
    # bonus). That's a win; don't invoke the LLM.
    if active_worker and top_agent == active_worker:
        return RoutingDecision(
            reason="sticky",
            selected=top_agent,
            candidates=candidate_names[:4],
            scores=scores_map,
            active_worker=active_worker,
            required_capabilities=required_for_record,
            risk=risk,
        )

    if gap >= epsilon:
        return RoutingDecision(
            reason="score_winner",
            selected=top_agent,
            candidates=candidate_names[:4],
            scores=scores_map,
            active_worker=active_worker,
            required_capabilities=required_for_record,
            risk=risk,
        )

    # Ambiguous — hand the shortlist to the caller's LLM tiebreaker.
    shortlist = [agent for score, agent, _ in scored if (top_score - score) < epsilon][:4]
    return RoutingDecision(
        reason="ambiguous",
        selected=shortlist[0],  # provisional; caller should overwrite if LLM picks different
        candidates=shortlist,
        scores=scores_map,
        active_worker=active_worker,
        required_capabilities=required_for_record,
        risk=risk,
    )


def explain_agent_choice(
    agent_name: str,
    required_capabilities: Iterable[str],
    *,
    risk: str = "low",
    reason: str = "",
) -> Dict[str, Any]:
    policy = policy_for_agent(agent_name)
    required = list(required_capabilities)
    matched = sorted(_coverage(agent_name, required))
    return {
        "agent": agent_name,
        "required_capabilities": required,
        "matched_capabilities": matched,
        "agent_capabilities": list(policy.capabilities),
        "risk": risk,
        "max_risk": policy.max_risk,
        "allowed_tools": list(policy.allowed_tools),
        "reason": reason or (
            f"{agent_name} covers {', '.join(matched) if matched else 'fallback orchestration'} "
            f"within {policy.max_risk} risk permission."
        ),
    }


def record_agent_selection(agent_name: str) -> AgentPerformanceCounters:
    counters = _PERFORMANCE_COUNTERS[agent_name]
    counters.selected += 1
    return counters


def record_agent_completion(agent_name: str, success: bool = True) -> AgentPerformanceCounters:
    """Track a completion outcome.

    On success we halve ``failed`` and ``tool_denied`` (integer division)
    so a single string of bad luck can't permanently bench an agent. Over
    ~3 successful completions the counters decay from N to 0, which maps
    to roughly one "bad day" of penalty before recovery.
    """
    counters = _PERFORMANCE_COUNTERS[agent_name]
    if success:
        counters.completed += 1
        if counters.failed > 0:
            counters.failed //= 2
        if counters.tool_denied > 0:
            counters.tool_denied //= 2
    else:
        counters.failed += 1
    return counters


def record_agent_tool(agent_name: str, allowed: bool) -> AgentPerformanceCounters:
    counters = _PERFORMANCE_COUNTERS[agent_name]
    if allowed:
        counters.tool_allowed += 1
    else:
        counters.tool_denied += 1
    return counters


def performance_snapshot() -> Dict[str, Dict[str, int]]:
    snapshot = {}
    for agent_name in STATIC_AGENT_POLICIES:
        counters = _PERFORMANCE_COUNTERS[agent_name]
        snapshot[agent_name] = counters.model_dump() if hasattr(counters, "model_dump") else counters.dict()
    return snapshot


def reset_performance_counters() -> None:
    _PERFORMANCE_COUNTERS.clear()
