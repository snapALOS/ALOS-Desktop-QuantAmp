from typing import Any, Dict, Iterable, List, Optional

from src.agents.swarm_manifest import SWARM_REGISTRY
from src.agents.capabilities import select_agent_for_capabilities
from src.planning.schemas import ExitCriterion, PlanStep, RequiredCapability, RunPlan, RiskLevel


LOW_RISK_CHAT_MARKERS = {
    "hello",
    "hi",
    "hey",
    "thanks",
    "thank you",
    "what is",
    "explain",
    "summarize",
    "tell me",
}

CRITICAL_RISK_MARKERS = {
    "rm -rf",
    "reset --hard",
    "delete database",
    "drop table",
    "wipe",
    "destroy",
    "erase all",
}

HIGH_RISK_MARKERS = {
    "write",
    "edit",
    "modify",
    "change",
    "implement",
    "fix",
    "install",
    "deploy",
    "migration",
    "migrate",
    "secret",
    "api key",
    "shell",
    "bash",
    "command",
    "code",
    "file",
    "database",
    "server",
    "frontend",
    "backend",
}

MEDIUM_RISK_MARKERS = {
    "test",
    "debug",
    "review",
    "analyze",
    "audit",
    "refactor",
    "diagnose",
    "trace",
}

CAPABILITY_ROUTES = [
    ({"ui", "frontend", "css", "html", "javascript", "app.js", "styles", "browser"}, "Frontend_UI_Agent", "frontend_ui"),
    ({"python", "fastapi", "backend", "api", "server", "websocket"}, "Python_Backend_Agent", "python_backend"),
    ({"database", "sqlite", "sql", "schema", "migration", "db"}, "Database_Engineer_Agent", "database"),
    ({"dependency", "dependencies", "install", "venv", "pip", "npm", "package"}, "Dependency_Agent", "dependency"),
    ({"deploy", "launcher", "boot", "port", "release", "installer"}, "Deployment_Agent", "deployment"),
    ({"security", "secret", "api key", "audit", "permission", "auth"}, "Security_Auditor_Agent", "security"),
    ({"doc", "docs", "readme", "install.md", "documentation"}, "DocString_Auditor_Agent", "documentation"),
    ({"test", "pytest", "jest", "eval", "regression", "verify"}, "Unit_Tester_Agent", "testing"),
    ({"refactor", "cleanup", "optimize", "performance"}, "Code_Refactor_Agent", "refactor"),
    ({"tool", "registry", "patch"}, "Dynamic_Tool_Agent", "tooling"),
]


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


def classify_risk(objective: str) -> RiskLevel:
    text = objective.lower()
    if _contains_any(text, CRITICAL_RISK_MARKERS):
        return "critical"
    if _contains_any(text, HIGH_RISK_MARKERS):
        return "high"
    if _contains_any(text, MEDIUM_RISK_MARKERS):
        return "medium"
    return "low"


def is_casual_objective(objective: str) -> bool:
    text = objective.strip().lower()
    if not text:
        return True
    if text in LOW_RISK_CHAT_MARKERS:
        return True
    return classify_risk(text) == "low" and _contains_any(text, LOW_RISK_CHAT_MARKERS)


def capability_for_objective(objective: str) -> RequiredCapability:
    text = objective.lower()
    for markers, agent_name, capability_name in CAPABILITY_ROUTES:
        if _contains_any(text, markers):
            return RequiredCapability(
                name=capability_name,
                reason=f"Objective matches {agent_name.replace('_Agent', '').replace('_', ' ').lower()} work.",
                risk=classify_risk(objective),
            )
    return RequiredCapability(
        name="general_execution",
        reason="Objective needs general orchestration rather than a narrow specialist.",
        risk=classify_risk(objective),
    )


def evidence_requirements_for_objective(objective: str, capability_name: str, risk: RiskLevel) -> list[str]:
    requirements = ["Current user request and active run context"]
    if capability_name in {"python_backend", "frontend_ui", "refactor", "testing", "tooling", "dependency"}:
        requirements.append("Relevant source files and direct dependencies")
        requirements.append("Atlas code-map or impact evidence when the repository is indexed")
    if capability_name == "frontend_ui":
        requirements.append("TypeScript/build output for affected UI surface")
    if capability_name in {"python_backend", "testing"}:
        requirements.append("Python test or compile evidence for affected backend surface")
    if risk in {"high", "critical"}:
        requirements.append("Explicit human approval before high-risk execution")
        requirements.append("Chamber build/test gate evidence before disk mutation")
    return requirements


def affected_surfaces_for_objective(objective: str, capability_name: str) -> list[str]:
    text = objective.lower()
    surfaces = []
    for marker, surface in [
        ("forge", "Forge IDE"),
        ("current", "Current workflow orchestration"),
        ("atlas", "Atlas dependency intelligence"),
        ("chamber", "Chamber write gate"),
        ("chat", "Chat"),
        ("settings", "Settings"),
        ("frontend", "Frontend"),
        ("backend", "Backend"),
        ("api", "Backend API"),
        ("workflow", "Current workflow orchestration"),
        ("dependency", "Atlas dependency intelligence"),
    ]:
        if marker in text and surface not in surfaces:
            surfaces.append(surface)
    if not surfaces:
        surfaces.append(capability_name.replace("_", " ").title())
    return surfaces


def agent_for_capability(capability_name: str) -> str:
    return select_agent_for_capabilities(
        [capability_name],
        risk="low",
        available_agents=SWARM_REGISTRY.keys(),
    )


def _verification_agent_for(capability_name: str) -> str:
    if capability_name in {"frontend_ui", "documentation"}:
        return "Sanity_Check_Agent"
    return "Unit_Tester_Agent"


def _step(
    step_id: str,
    title: str,
    description: str,
    agent: str,
    capabilities: Optional[List[RequiredCapability]] = None,
    criteria: Optional[List[ExitCriterion]] = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        title=title,
        description=description,
        assigned_agent=agent,
        required_capabilities=capabilities or [],
        exit_criteria=criteria or [],
    )


def create_run_plan(objective: str) -> RunPlan:
    clean_objective = (objective or "").strip()
    risk = classify_risk(clean_objective)

    if is_casual_objective(clean_objective):
        step = _step(
            "step-1-respond",
            "Respond Directly",
            "Answer the user without tool work or filesystem changes.",
            "Human_Proxy_Agent",
            [RequiredCapability(name="conversation", reason="The objective is conversational.", risk="low")],
            [ExitCriterion(description="The response addresses the user directly.")],
        )
        step.status = "running"
        return RunPlan(
            objective=clean_objective,
            steps=[step],
            risk="low",
            needs_approval=False,
            approved=True,
            status="running",
            current_step_id=step.id,
            evidence_requirements=["Current conversation context"],
            affected_surfaces=["Chat"],
            acceptance_criteria=["The response addresses the user directly."],
            verification_required=False,
        )

    primary_capability = capability_for_objective(clean_objective)
    primary_agent = agent_for_capability(primary_capability.name)
    verification_agent = _verification_agent_for(primary_capability.name)
    needs_approval = risk in {"high", "critical"}

    steps = [
        _step(
            "step-1-analyze",
            "Analyze Objective",
            "Map the request, constraints, affected surfaces, and evidence needed before acting.",
            "Technical_Architect_Agent",
            [RequiredCapability(name="architecture_mapping", reason="Serious tasks need explicit scope before execution.", risk="medium")],
            [ExitCriterion(description="The objective and affected system boundaries are identified.")],
        ),
        _step(
            "step-2-execute",
            "Execute Work",
            "Perform the requested work through the specialist assigned to the detected capability.",
            primary_agent,
            [primary_capability],
            [ExitCriterion(description="The requested change or analysis has been completed.")],
        ),
        _step(
            "step-3-verify",
            "Verify Result",
            "Validate the outcome and report failures against the active plan step.",
            verification_agent,
            [RequiredCapability(name="verification", reason="Serious tasks must not finish without an explicit verification pass.", risk="medium")],
            [ExitCriterion(description="Verification evidence has been produced before the run can finish.")],
        ),
    ]

    if not needs_approval:
        steps[0].status = "running"

    return RunPlan(
        objective=clean_objective,
        steps=steps,
        risk=risk,
        needs_approval=needs_approval,
        approved=not needs_approval,
        status="blocked" if needs_approval else "running",
        current_step_id=steps[0].id,
        evidence_requirements=evidence_requirements_for_objective(clean_objective, primary_capability.name, risk),
        affected_surfaces=affected_surfaces_for_objective(clean_objective, primary_capability.name),
        acceptance_criteria=[
            "Affected surfaces are identified before execution.",
            "Execution follows the assigned specialist and capability policy.",
            "Verification evidence is produced before completion.",
        ],
        verification_required=True,
    )


def plan_from_state(raw_plan: Any) -> Optional[RunPlan]:
    if not raw_plan:
        return None
    if isinstance(raw_plan, RunPlan):
        return raw_plan
    if hasattr(RunPlan, "model_validate"):
        return RunPlan.model_validate(raw_plan)
    return RunPlan.parse_obj(raw_plan)


def public_plan(plan: Any) -> Dict[str, Any]:
    parsed = plan_from_state(plan)
    return _model_to_dict(parsed) if parsed else {}


def approve_plan(plan: Any) -> RunPlan:
    parsed = plan_from_state(plan)
    if parsed is None:
        raise ValueError("Cannot approve a missing plan.")
    parsed.approved = True
    parsed.status = "running"
    step = active_plan_step(parsed)
    if step and step.status in {"pending", "blocked"}:
        step.status = "running"
    return parsed


def active_plan_step(plan: Any) -> Optional[PlanStep]:
    parsed = plan_from_state(plan)
    if parsed is None:
        return None

    if parsed.current_step_id:
        for step in parsed.steps:
            if step.id == parsed.current_step_id and step.status in {"pending", "running", "blocked", "failed"}:
                return step

    for status in ("running", "pending", "blocked", "failed"):
        for step in parsed.steps:
            if step.status == status:
                parsed.current_step_id = step.id
                return step
    return None


def agent_for_active_step(plan: Any) -> Optional[str]:
    step = active_plan_step(plan)
    if not step:
        return None
    parsed = plan_from_state(plan)
    risk = parsed.risk if parsed else "low"
    required = [capability.name for capability in step.required_capabilities]
    return select_agent_for_capabilities(
        required,
        risk=risk,
        preferred_agent=step.assigned_agent,
        available_agents=SWARM_REGISTRY.keys(),
    )


def start_active_step(plan: Any) -> Optional[RunPlan]:
    parsed = plan_from_state(plan)
    if parsed is None:
        return None
    if parsed.needs_approval and not parsed.approved:
        parsed.status = "blocked"
        return parsed
    step = active_plan_step(parsed)
    if step and step.status == "pending":
        step.status = "running"
    parsed.status = "running" if step else "complete"
    return parsed


def complete_active_step(plan: Any, agent_name: str) -> Optional[RunPlan]:
    parsed = plan_from_state(plan)
    if parsed is None:
        return None

    step = active_plan_step(parsed)
    if not step:
        parsed.status = "complete"
        parsed.current_step_id = None
        return parsed

    if step.assigned_agent != agent_name:
        return parsed

    step.status = "complete"
    for criterion in step.exit_criteria:
        criterion.satisfied = True
    step.failure_reason = None

    for next_step in parsed.steps:
        if next_step.status == "pending":
            next_step.status = "running"
            parsed.current_step_id = next_step.id
            parsed.status = "running"
            return parsed

    parsed.current_step_id = None
    parsed.status = "complete"
    return parsed


def fail_active_step(plan: Any, reason: str) -> Optional[RunPlan]:
    parsed = plan_from_state(plan)
    if parsed is None:
        return None
    step = active_plan_step(parsed)
    if step:
        step.status = "failed"
        step.failure_reason = reason
        parsed.current_step_id = step.id
    parsed.status = "failed"
    return parsed


def block_plan(plan: Any, reason: str) -> Optional[RunPlan]:
    parsed = plan_from_state(plan)
    if parsed is None:
        return None
    step = active_plan_step(parsed)
    if step:
        step.status = "blocked"
        step.failure_reason = reason
        parsed.current_step_id = step.id
    parsed.status = "blocked"
    return parsed


def plan_has_remaining_work(plan: Any) -> bool:
    parsed = plan_from_state(plan)
    if parsed is None:
        return False
    return any(step.status in {"pending", "running", "blocked", "failed"} for step in parsed.steps)


def has_incomplete_required_verification(plan: Any) -> bool:
    parsed = plan_from_state(plan)
    if parsed is None:
        return False
    verification_steps = [
        step for step in parsed.steps
        if any(capability.name == "verification" for capability in step.required_capabilities)
    ]
    return any(step.status != "complete" for step in verification_steps)


def failed_step_label(plan: Any) -> str:
    parsed = plan_from_state(plan)
    if parsed is None:
        return "unknown plan step"
    for step in parsed.steps:
        if step.status == "failed":
            return step.title
    step = active_plan_step(parsed)
    return step.title if step else "unknown plan step"
