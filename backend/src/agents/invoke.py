from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, BaseMessage
from src.core.state import AgentState, TokenUsage
from src.graph.builder import build_orchestrator
from modules.current.contracts.nodes.invoke_agent import (
    InvokeAgentNodeInput,
    InvokeAgentNodeOutput,
    ToolCallRecord,
    ErrorDetail
)


def run_agent_step(
    inputs: InvokeAgentNodeInput,
    cancel_check: Optional[Callable[[], bool]] = None,
    on_event: Optional[Callable[[str, dict], None]] = None,
    run_id: str = "",
    step_id: str = "",
) -> InvokeAgentNodeOutput:
    """Entry point for invoking the LangGraph agent swarm from a workflow step (RFC-0002)."""
    
    started_at = datetime.now()
    app = build_orchestrator()
    
    # Initialize State
    state: AgentState = {
        "messages": [HumanMessage(content=inputs.prompt)],
        "current_objective": inputs.prompt,
        "current_step_id": step_id,
        "active_worker": None,
        "error_history": [],
        "tool_results": [],
        "cumulative_tokens": TokenUsage(),
        "requires_human_approval": False,
        "run_plan": None,
        "current_plan_step": None,
        "agent_selection": None,
        "amp_q_correlation_id": f"current_{run_id}_{step_id}",
        "amp_q_segments": [],
        "amp_q_context": None,
    }
    
    turns_used = 0
    final_output = ""
    tool_calls: List[ToolCallRecord] = []
    
    try:
        # Stream turns specifically to allow turn-granular observation and cancellation
        for event in app.stream(state, config={"recursion_limit": inputs.max_turns}):
            turns_used += 1
            
            # Cooperative Cancellation Check (RFC-0002 Decision 3)
            if cancel_check and cancel_check():
                return InvokeAgentNodeOutput(
                    status="cancelled",
                    output=final_output,
                    tool_calls=tool_calls,
                    turns_used=turns_used,
                    started_at=started_at,
                    completed_at=datetime.now(),
                )
            
            # Extract state update
            # LangGraph stream events are dicts of {node_name: {state_update_key: value}}
            for node_name, output in event.items():
                if "messages" in output:
                    last_msg = output["messages"][-1]
                    if isinstance(last_msg, BaseMessage):
                        final_output = str(last_msg.content)
                
                # Emit turn event (Decision 7)
                if on_event:
                    on_event("current.agent_step.turn_completed", {
                        "runId": run_id,
                        "stepId": step_id,
                        "turn": turns_used,
                        "agentId": node_name,
                        "output": final_output[:200] + "..." if len(final_output) > 200 else final_output
                    })

        return InvokeAgentNodeOutput(
            status="ok",
            output=final_output,
            tool_calls=tool_calls,
            turns_used=turns_used,
            started_at=started_at,
            completed_at=datetime.now(),
        )

    except Exception as exc:
        if "recursion_limit" in str(exc).lower():
            return InvokeAgentNodeOutput(
                status="max_turns_exceeded",
                output=final_output,
                tool_calls=tool_calls,
                turns_used=turns_used,
                started_at=started_at,
                completed_at=datetime.now(),
                error=ErrorDetail(code="max_turns", message=str(exc))
            )
            
        return InvokeAgentNodeOutput(
            status="error",
            output=final_output,
            tool_calls=tool_calls,
            turns_used=turns_used,
            started_at=started_at,
            completed_at=datetime.now(),
            error=ErrorDetail(code="runtime_error", message=str(exc))
        )
