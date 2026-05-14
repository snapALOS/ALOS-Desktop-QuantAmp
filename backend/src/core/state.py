import operator
from typing import TypedDict, Annotated, Sequence, Any, Optional
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

class TokenUsage(BaseModel):
    """Explicitly tracks token consumption matrix over the application lifecycle"""
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)

class AgentState(TypedDict):
    """
    The rigid, exhaustive state schema driving the orchestration engine.
    Ensures absolute determinism without requiring the LLM to guess memory points.
    All accumulation variables use `operator.add` to chronologically compile history.
    """
    # Core LLM message stream
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Active execution directives for the LangGraph
    current_objective: Optional[str]
    current_step_id: Optional[str]
    active_worker: Optional[str]
    
    # System Debug & Guardrails
    error_history: Annotated[list[str], operator.add]
    
    # Verified Tool Outputs
    tool_results: Annotated[list[dict[str, Any]], operator.add]
    
    # Context Limits
    cumulative_tokens: Optional[TokenUsage]
    
    # Flow Control
    requires_human_approval: bool
    run_plan: Optional[dict[str, Any]]
    current_plan_step: Optional[str]
    agent_selection: Optional[dict[str, Any]]
    module_context: Optional[dict[str, Any]]
    logic_trace: Annotated[list[dict[str, Any]], operator.add]
    logic_cycle_count: Optional[int]
    stuck_reason: Optional[str]

    # [QUANTAMP INTEGRATION: AMP-Q]
    amp_q_correlation_id: Optional[str]
    amp_q_segments: Annotated[list[str], operator.add]
    amp_q_context: Optional[str]
