"""
Event contracts for ALOS — Python mirror of src/contracts/events.ts.

Every event carries a `timestamp` field (Unix milliseconds, float).
This is mandated by RFC-0005 Decision 7.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional


def _now_ms() -> float:
    """Return current time as Unix milliseconds."""
    return time.time() * 1000


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseEvent:
    type: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Forge events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ForgeFileChanged(BaseEvent):
    type: str = field(default="forge.file.changed", init=False)
    path: str = ""


@dataclass(frozen=True)
class ForgeFileSaved(BaseEvent):
    type: str = field(default="forge.file.saved", init=False)
    path: str = ""


@dataclass(frozen=True)
class ForgeFileCreated(BaseEvent):
    type: str = field(default="forge.file.created", init=False)
    path: str = ""


@dataclass(frozen=True)
class ForgeFileDeleted(BaseEvent):
    type: str = field(default="forge.file.deleted", init=False)
    path: str = ""


# ---------------------------------------------------------------------------
# Atlas events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AtlasIndexStarted(BaseEvent):
    type: str = field(default="atlas.index.started", init=False)
    root: str = ""


@dataclass(frozen=True)
class AtlasIndexComplete(BaseEvent):
    type: str = field(default="atlas.index.complete", init=False)
    root: str = ""
    symbols: int = 0


@dataclass(frozen=True)
class AtlasWorkspaceOpened(BaseEvent):
    type: str = field(default="atlas.workspace.opened", init=False)
    root: str = ""


# ---------------------------------------------------------------------------
# Current (workflow) events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrentWorkflowStarted(BaseEvent):
    type: str = field(default="current.workflow.started", init=False)
    workflowId: str = ""
    runId: str = ""


@dataclass(frozen=True)
class CurrentWorkflowCompleted(BaseEvent):
    type: str = field(default="current.workflow.completed", init=False)
    runId: str = ""
    status: str = ""  # "ok" | "error"


@dataclass(frozen=True)
class CurrentWorkflowStepStarted(BaseEvent):
    type: str = field(default="current.workflow.step.started", init=False)
    runId: str = ""
    stepId: str = ""


@dataclass(frozen=True)
class CurrentWorkflowStepCompleted(BaseEvent):
    type: str = field(default="current.workflow.step.completed", init=False)
    runId: str = ""
    stepId: str = ""
    status: str = ""


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentTurnStarted(BaseEvent):
    type: str = field(default="agent.turn.started", init=False)
    conversationId: str = ""
    agentId: str = ""


@dataclass(frozen=True)
class AgentTurnCompleted(BaseEvent):
    type: str = field(default="agent.turn.completed", init=False)
    conversationId: str = ""
    agentId: str = ""
    tokens: int = 0


# ---------------------------------------------------------------------------
# Agent step events (RFC-0002)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrentAgentStepTurnStarted(BaseEvent):
    type: str = field(default="current.agent_step.turn_started", init=False)
    runId: str = ""
    stepId: str = ""
    turn: int = 0
    agentId: str = ""


@dataclass(frozen=True)
class CurrentAgentStepTurnCompleted(BaseEvent):
    type: str = field(default="current.agent_step.turn_completed", init=False)
    runId: str = ""
    stepId: str = ""
    turn: int = 0
    agentId: str = ""
    tokensIn: int = 0
    tokensOut: int = 0
    toolCalls: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class CurrentAgentStepToolCall(BaseEvent):
    type: str = field(default="current.agent_step.tool_call", init=False)
    runId: str = ""
    stepId: str = ""
    turn: int = 0
    toolName: str = ""
    status: str = ""
    durationMs: float = 0


# ---------------------------------------------------------------------------
# Approval events (RFC-0004)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoreApprovalRequested(BaseEvent):
    type: str = field(default="core.approval.requested", init=False)
    request: Any = None


@dataclass(frozen=True)
class CoreApprovalResolved(BaseEvent):
    type: str = field(default="core.approval.resolved", init=False)
    id: str = ""
    status: str = ""
    resolvedAt: str = ""
    actor: Optional[str] = None


@dataclass(frozen=True)
class CoreApprovalCancelled(BaseEvent):
    type: str = field(default="core.approval.cancelled", init=False)
    id: str = ""
    cancelledAt: str = ""


# ---------------------------------------------------------------------------
# Module badge event (RFC-0001)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModuleBadgeSet(BaseEvent):
    type: str = field(default="module.badge.set", init=False)
    moduleId: str = ""
    badge: Any = None  # int | "dot" | None


# ---------------------------------------------------------------------------
# Terminal / Shell events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TerminalObservedData(BaseEvent):
    type: str = field(default="terminal.observed_data", init=False)
    data: str = ""
    runId: Optional[str] = None
    nodeId: Optional[str] = None


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def create_forge_file_changed(path: str) -> ForgeFileChanged:
    return ForgeFileChanged(timestamp=_now_ms(), path=path)


def create_forge_file_saved(path: str) -> ForgeFileSaved:
    return ForgeFileSaved(timestamp=_now_ms(), path=path)


def create_forge_file_created(path: str) -> ForgeFileCreated:
    return ForgeFileCreated(timestamp=_now_ms(), path=path)


def create_forge_file_deleted(path: str) -> ForgeFileDeleted:
    return ForgeFileDeleted(timestamp=_now_ms(), path=path)


def create_atlas_index_started(root: str) -> AtlasIndexStarted:
    return AtlasIndexStarted(timestamp=_now_ms(), root=root)


def create_atlas_index_complete(root: str, symbols: int) -> AtlasIndexComplete:
    return AtlasIndexComplete(timestamp=_now_ms(), root=root, symbols=symbols)


def create_atlas_workspace_opened(root: str) -> AtlasWorkspaceOpened:
    return AtlasWorkspaceOpened(timestamp=_now_ms(), root=root)


def create_current_workflow_started(workflow_id: str, run_id: str) -> CurrentWorkflowStarted:
    return CurrentWorkflowStarted(timestamp=_now_ms(), workflowId=workflow_id, runId=run_id)


def create_current_workflow_completed(run_id: str, status: str) -> CurrentWorkflowCompleted:
    return CurrentWorkflowCompleted(timestamp=_now_ms(), runId=run_id, status=status)


def create_current_workflow_step_started(run_id: str, step_id: str) -> CurrentWorkflowStepStarted:
    return CurrentWorkflowStepStarted(timestamp=_now_ms(), runId=run_id, stepId=step_id)


def create_current_workflow_step_completed(
    run_id: str, step_id: str, status: str
) -> CurrentWorkflowStepCompleted:
    return CurrentWorkflowStepCompleted(timestamp=_now_ms(), runId=run_id, stepId=step_id, status=status)


def create_agent_turn_started(conversation_id: str, agent_id: str) -> AgentTurnStarted:
    return AgentTurnStarted(timestamp=_now_ms(), conversationId=conversation_id, agentId=agent_id)


def create_agent_turn_completed(
    conversation_id: str, agent_id: str, tokens: int
) -> AgentTurnCompleted:
    return AgentTurnCompleted(timestamp=_now_ms(), conversationId=conversation_id, agentId=agent_id, tokens=tokens)


def create_current_agent_step_turn_started(
    run_id: str, step_id: str, turn: int, agent_id: str
) -> CurrentAgentStepTurnStarted:
    return CurrentAgentStepTurnStarted(
        timestamp=_now_ms(), runId=run_id, stepId=step_id, turn=turn, agentId=agent_id
    )


def create_current_agent_step_turn_completed(
    run_id: str,
    step_id: str,
    turn: int,
    agent_id: str,
    tokens_in: int,
    tokens_out: int,
    tool_calls: List[Any],
) -> CurrentAgentStepTurnCompleted:
    return CurrentAgentStepTurnCompleted(
        timestamp=_now_ms(),
        runId=run_id,
        stepId=step_id,
        turn=turn,
        agentId=agent_id,
        tokensIn=tokens_in,
        tokensOut=tokens_out,
        toolCalls=tool_calls,
    )


def create_current_agent_step_tool_call(
    run_id: str,
    step_id: str,
    turn: int,
    tool_name: str,
    status: str,
    duration_ms: float,
) -> CurrentAgentStepToolCall:
    return CurrentAgentStepToolCall(
        timestamp=_now_ms(),
        runId=run_id,
        stepId=step_id,
        turn=turn,
        toolName=tool_name,
        status=status,
        durationMs=duration_ms,
    )


def create_core_approval_requested(request: Any) -> CoreApprovalRequested:
    return CoreApprovalRequested(timestamp=_now_ms(), request=request)


def create_core_approval_resolved(
    id: str, status: str, resolved_at: str, actor: Optional[str] = None
) -> CoreApprovalResolved:
    return CoreApprovalResolved(
        timestamp=_now_ms(), id=id, status=status, resolvedAt=resolved_at, actor=actor
    )


def create_core_approval_cancelled(id: str, cancelled_at: str) -> CoreApprovalCancelled:
    return CoreApprovalCancelled(timestamp=_now_ms(), id=id, cancelledAt=cancelled_at)


def create_module_badge_set(module_id: str, badge: Any) -> ModuleBadgeSet:
    return ModuleBadgeSet(timestamp=_now_ms(), moduleId=module_id, badge=badge)


def create_terminal_observed_data(
    data: str, run_id: Optional[str] = None, node_id: Optional[str] = None
) -> TerminalObservedData:
    return TerminalObservedData(
        timestamp=_now_ms(), data=data, runId=run_id, nodeId=node_id
    )
