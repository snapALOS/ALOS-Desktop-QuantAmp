from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class InvokeAgentNodeInput(BaseModel):
    """Input contract for the invoke_agent workflow node (RFC-0002)."""
    prompt: str
    agent_id: str = "supervisor"
    allowed_tools: Optional[List[str]] = None       # None = agent default; [] = no tools
    max_risk: Optional[Literal["low", "medium", "high", "critical"]] = None
    max_turns: int = 10
    timeout_seconds: int = 300
    context: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = True


class ToolCallRecord(BaseModel):
    """Audit record for a tool call performed during an agent step."""
    turn: int
    tool_name: str
    args: Dict[str, Any]
    result_summary: str            # truncated preview; full result in logs
    status: Literal["ok", "denied", "error"]
    denial_reason: Optional[str] = None
    duration_ms: int


class ErrorDetail(BaseModel):
    """Machine-readable error detail for agent failures."""
    code: str                       # e.g. "agent_timeout", "tool_error"
    message: str
    turn_index: Optional[int] = None
    tool_name: Optional[str] = None


class InvokeAgentNodeOutput(BaseModel):
    """Output contract for the invoke_agent workflow node (RFC-0002)."""
    status: Literal["ok", "timeout", "max_turns_exceeded", "capability_denied", "cancelled", "error"]
    output: str = ""                # agent's final answer
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    turns_used: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime = Field(default_factory=datetime.now)
    error: Optional[ErrorDetail] = None
    routing_decisions: List[Dict[str, Any]] = Field(default_factory=list)
