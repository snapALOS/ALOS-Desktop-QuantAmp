from langchain_core.messages import ToolMessage, AIMessage
from src.core.config import system_logger
from src.core.state import AgentState
from src.planning.planner import has_incomplete_required_verification, plan_has_remaining_work

def determine_main_route(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "supervisor_node"
        
    last_message = messages[-1]
    
    # If the last message threw a tool call -> route to execute distinct physics tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        system_logger.info("Swarm routing logic passed natively to [tool_execution_node]")
        return "tool_execution_node"
        
    # If it was a ToolMessage -> route strictly back to active specific worker logic globally
    if isinstance(last_message, ToolMessage):
        active_worker = state.get("active_worker")
        system_logger.info(f"Swarm tools completely verified, returning array natively to -> [{active_worker}]")
        return active_worker if active_worker else "supervisor_node"
        
    # If a worker produced a final answer with no tool calls, end this user turn.
    if isinstance(last_message, AIMessage):
        tokens = state.get("cumulative_tokens")
        active = state.get("active_worker")
        if tokens and tokens.total_tokens > 240000 and active != "Memory_Archivist_Agent":
            system_logger.warning(f"Token matrix exceeded 240k array limits ({tokens.total_tokens}). Triggering Native Archivist.")
            return "Memory_Archivist_Agent"

        run_plan = state.get("run_plan")
        if run_plan and plan_has_remaining_work(run_plan):
            if has_incomplete_required_verification(run_plan):
                system_logger.info("Run plan still has required verification work. Returning to supervisor.")
            else:
                system_logger.info("Run plan has remaining work. Returning to supervisor.")
            return "supervisor_node"
            
        if active == "Human_Proxy_Agent":
            system_logger.info("Human Proxy complete. Bypassing supervisor to await the next user turn.")
            return "end"

        system_logger.info("Worker produced a final response with no tool calls. Ending current user turn.")
        return "end"
        
    return "supervisor_node"

def determine_supervisor_route(state: AgentState) -> str:
    next_node = state.get("current_step_id", "FINISH")
    if next_node == "FINISH":
        return "end"
    return next_node
