from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


StepStatus = Literal["pending", "running", "blocked", "failed", "complete"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class RequiredCapability(BaseModel):
    name: str
    reason: str
    risk: RiskLevel = "low"


class ExitCriterion(BaseModel):
    description: str
    required: bool = True
    satisfied: bool = False


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    required_capabilities: list[RequiredCapability] = Field(default_factory=list)
    exit_criteria: list[ExitCriterion] = Field(default_factory=list)
    status: StepStatus = "pending"
    assigned_agent: str
    failure_reason: Optional[str] = None


class RunPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    steps: list[PlanStep]
    risk: RiskLevel = "low"
    needs_approval: bool = False
    approved: bool = False
    status: StepStatus = "pending"
    current_step_id: Optional[str] = None
    evidence_requirements: list[str] = Field(default_factory=list)
    affected_surfaces: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification_required: bool = True
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def current_step(self) -> Optional[PlanStep]:
        if self.current_step_id:
            for step in self.steps:
                if step.id == self.current_step_id:
                    return step
        for step in self.steps:
            if step.status in {"pending", "running", "blocked", "failed"}:
                return step
        return None
