from langgraph.graph import StateGraph, END
from src.core.state import AgentState
from src.core.config import system_logger
from src.graph.nodes import reflection_node, tool_execution_node
from src.graph.supervisor import supervisor_node
from src.agents.worker import create_worker_node
from src.agents.swarm_manifest import SWARM_REGISTRY
from src.graph.edges import determine_main_route, determine_supervisor_route

def build_orchestrator():
    system_logger.info("Initiating massive 27-Agent Swarm compilation strictly natively.")
    try:
        workflow = StateGraph(AgentState)
        
        # Fundamental Utility Core Nodes
        workflow.add_node("supervisor_node", supervisor_node)
        workflow.add_node("tool_execution_node", tool_execution_node)
        workflow.add_node("reflection_node", reflection_node)
        
        # Dynamically mount ALL 27 agents strictly mapping their execution rules natively 
        for agent_name in SWARM_REGISTRY.keys():
            workflow.add_node(agent_name, create_worker_node(agent_name))
            
            # Every distinct worker conditionally edges based natively logically 
            # (routing to tool node or back to supervisor evaluating loop completion)
            workflow.add_conditional_edges(
                agent_name,
                determine_main_route,
                {
                    "tool_execution_node": "tool_execution_node",
                    "supervisor_node": "supervisor_node",
                    "Memory_Archivist_Agent": "Memory_Archivist_Agent",
                    "end": END
                }
            )
            
        # Tool node natively conditionally edges back to the mapped active_worker seamlessly
        route_map = {"supervisor_node": "supervisor_node"}
        for agent_name in SWARM_REGISTRY.keys():
            route_map[agent_name] = agent_name
            
        workflow.add_conditional_edges(
            "tool_execution_node",
            determine_main_route,
            route_map
        )
        
        # Supervisor evaluates the payload and routes natively cleanly strictly 
        supervisor_map = {"end": END}
        for agent_name in SWARM_REGISTRY.keys():
            supervisor_map[agent_name] = agent_name
            
        workflow.add_conditional_edges(
            "supervisor_node",
            determine_supervisor_route,
            supervisor_map
        )
        
        workflow.set_entry_point("supervisor_node")
        
        app = workflow.compile()
        system_logger.info("Swarm structural compilation entirely passed architectural checks natively.")
        return app
        
    except Exception as e:
        system_logger.critical(f"Fatal Swarm layout graph crash natively: {str(e)}")
        raise e
