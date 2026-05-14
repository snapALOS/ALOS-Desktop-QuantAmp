import traceback
from typing import Dict, Any
from pathlib import Path
from langchain_core.messages import ToolMessage
from src.core.state import AgentState, TokenUsage
from src.core.config import system_logger
from src.tools.registry import get_core_tools
from src.graph.supervisor import supervisor_node
from src.agents.worker import create_worker_node
from src.agents.capabilities import CapabilityPolicyViolation, enforce_tool_permission, record_agent_tool
from src.runtime.events import tool_completed, tool_denied, tool_requested
from src.runtime.runs import current_run_context
from src.runtime.logic_engine import tool_idempotency_key
from src.api.database import get_tool_idempotency, record_tool_idempotency

async def tool_execution_node(state: AgentState) -> dict[str, Any]:
    system_logger.info("Executing -> [tool_execution_node]")
    messages = state.get("messages", [])
    if not messages:
        return {}
    
    last_message = messages[-1]
    results = []
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        system_logger.info(f"Swarm requested {len(last_message.tool_calls)} external boundaries natively.")
        tools = get_core_tools()
        tool_map = {t.name: t for t in tools}
        
        for t_call in last_message.tool_calls:
            tool_name = t_call["name"]
            tool_args = t_call["args"]
            tool_id = t_call["id"]
            active_worker = str(state.get("active_worker") or "Unknown_Agent")
            
            system_logger.info(f"Executing Mechanical Link: [{tool_name}]")
            run_id, session_id = current_run_context()
            if run_id and session_id:
                tool_requested(run_id, session_id, tool_name, tool_id, node="tool_execution_node")
            
            try:
                if tool_name not in tool_map:
                    raise ValueError(f"Tool '{tool_name}' is not registered in the ALOS policy registry.")
                enforce_tool_permission(active_worker, tool_name)
                record_agent_tool(active_worker, allowed=True)
                cached = {}
                idem_key = ""
                if run_id and session_id:
                    idem_key = tool_idempotency_key(run_id, tool_name, tool_id, tool_args)
                    cached = get_tool_idempotency(idem_key)
                if cached:
                    cached_result = cached.get("result") or {}
                    results.append(ToolMessage(content=str(cached_result.get("content", "")), tool_call_id=tool_id))
                    if run_id and session_id:
                        tool_completed(run_id, session_id, tool_name, tool_id, ok=True, node="tool_execution_node")
                    continue
                # Dynamically fire exactly restricted tool calls asynchronously.
                res = await tool_map[tool_name].ainvoke(tool_args)
                results.append(ToolMessage(content=str(res), tool_call_id=tool_id))
                if run_id and session_id:
                    record_tool_idempotency(
                        idem_key,
                        run_id,
                        session_id,
                        tool_name,
                        status="completed",
                        result={"content": str(res)},
                    )
                    tool_completed(run_id, session_id, tool_name, tool_id, ok=True, node="tool_execution_node")
            except CapabilityPolicyViolation as e:
                record_agent_tool(active_worker, allowed=False)
                system_logger.warning(f"Capability tool policy denied [{active_worker}] -> [{tool_name}]: {str(e)}")
                results.append(ToolMessage(content=f"Policy denied: {str(e)}", tool_call_id=tool_id))
                if run_id and session_id:
                    tool_denied(run_id, session_id, tool_name, tool_id, active_worker=active_worker, reason=str(e), node="tool_execution_node")
            except Exception as e:
                system_logger.error(f"Native execution trap logic failed natively: {str(e)}")
                results.append(ToolMessage(content=f"Error: {str(e)}", tool_call_id=tool_id))
                if run_id and session_id:
                    tool_completed(run_id, session_id, tool_name, tool_id, ok=False, node="tool_execution_node")
    
    return {"messages": results}

def reflection_node(state: AgentState) -> dict[str, Any]:
    system_logger.info("Executing -> [reflection_node]")
    system_logger.warning("Isolating system fault code string...")
    
    # Drops explicit recursive loop traps identically onto the error logic trace natively
    return {
        "error_history": [f"Execution Engine Fault: {traceback.format_exc()[:500]}"]
    }
