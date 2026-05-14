from typing import Any
from langchain_core.messages import SystemMessage, RemoveMessage
from src.core.state import AgentState
from src.core.llm_factory import get_llm
from src.core.config import system_logger
from src.agents.swarm_manifest import SWARM_REGISTRY
from src.agents.capabilities import (
    explain_agent_choice,
    filter_tools_for_agent,
    policy_for_agent,
    record_agent_completion,
)
from src.planning.planner import active_plan_step, complete_active_step, public_plan
from src.core.quant_amp.doctrine import AtomicManager
from src.runtime.aps import PrecisionManager
from src.runtime.logic_engine import context_directive

def create_worker_node(agent_name: str):
    blueprint = SWARM_REGISTRY[agent_name]
    
    def worker_node(state: AgentState) -> dict[str, Any]:
        system_logger.info(f"Swarm Engagement -> [{agent_name}] activated specifically.")
        
        project_invariants = (
            "\n\nPROJECT INVARIANTS:\n"
            "- The product is branded ALOS, short for Automated Local OS. Do not use the legacy project name in user-facing text or generated code.\n"
            "- The memory implementation lives in src/memory/vector_store.py. Do not recreate src/memory/store.py unless the human explicitly asks for that file.\n"
            "- Finish the current turn once the requested work is complete. Only call tools when additional evidence or a physical change is required."
        )
        plan_directive = ""
        active_step = active_plan_step(state.get("run_plan"))
        run_risk = str((state.get("run_plan") or {}).get("risk", "low")) if isinstance(state.get("run_plan"), dict) else "low"
        if active_step:
            criteria = "; ".join(criterion.description for criterion in active_step.exit_criteria) or "Complete the assigned step."
            plan_directive = (
                "\n\nACTIVE RUN PLAN STEP:\n"
                f"- Step: {active_step.title}\n"
                f"- Assigned agent: {active_step.assigned_agent}\n"
                f"- Description: {active_step.description}\n"
                f"- Exit criteria: {criteria}\n"
                "- Do not perform future plan steps early. Return only the result of this assigned step."
            )
        policy = policy_for_agent(agent_name)
        policy_directive = (
            "\n\nCAPABILITY POLICY:\n"
            f"- Capability tags: {', '.join(policy.capabilities) or 'none'}\n"
            f"- Maximum authorized risk: {policy.max_risk}\n"
            f"- Permitted tools: {', '.join(policy.allowed_tools) or 'none'}\n"
            "- Do not request a tool that is not explicitly listed here."
        )
        identity_anchor = (
            f"STRICT IDENTITY: You are the {agent_name.replace('_', ' ')}. You are NOT a general 'Human Proxy Agent' or a basic conversational assistant. "
            f"Your active toolkit consists of: [{', '.join(policy.allowed_tools) or 'none'}]. "
            "You MUST use these tools whenever technical evidence or physical file analysis is required. "
            "Never claim you are unable to see the codebase or perform actions if your tools permit it. "
            "If you are requested to analyze code, use your 'read_file_content' or 'read_local_directory' tools immediately.\n\n"
        )
        module_directive = context_directive(state.get("module_context"))
        evidence_directive = (
            "\n\nEVIDENCE-FIRST EXECUTION:\n"
            "- For serious coding, workflow, dependency, or operational work, gather concrete evidence before final claims.\n"
            "- Use Atlas tools for code/dependency impact when available and relevant.\n"
            "- Use scout_query when debugging runtime behavior, frontend failures, backend logs, or previous agent-run errors.\n"
            "- Do not complete a plan step unless its exit criteria can be backed by observed evidence.\n"
        )
        agent_sys = SystemMessage(
            content=identity_anchor
            + blueprint.system_prompt
            + project_invariants
            + module_directive
            + plan_directive
            + policy_directive
            + evidence_directive
        )
        llm = get_llm()
        
        permitted_tools = filter_tools_for_agent(agent_name, blueprint.tools, risk=run_risk)
        if permitted_tools:
            agent_llm = llm.bind_tools(permitted_tools)
        else:
            agent_llm = llm

        # --- NATIVE ARCHIVIST COMPRESSION LOGIC ---
        if agent_name == "Memory_Archivist_Agent":
            from src.core.state import TokenUsage
            system_logger.warning("Executing mechanical token condensation arrays.")
            msgs = state.get("messages", [])
            # Condense the array specifically if history tracks long enough
            if len(msgs) > 10:
                # Target the oldest context logic specifically bypassing immediate loops
                to_summarize = msgs[1:10]
                removals = [RemoveMessage(id=m.id) for m in to_summarize if getattr(m, "id", None)]
                
                sys_prompt = SystemMessage(content="Mathematically condense this massive trace omitting code specifically for context limits.")
                summary_string = agent_llm.invoke([sys_prompt] + to_summarize)
                cache_message = SystemMessage(content=f"CACHE COMPRESSION: {summary_string.content}")
                record_agent_completion(agent_name, success=True)
                
                return {
                    "messages": removals + [cache_message],
                    "active_worker": agent_name,
                    "cumulative_tokens": TokenUsage() # Reset limits natively
                }
            record_agent_completion(agent_name, success=True)
            return {"active_worker": agent_name, "messages": []}
        # ----------------------------------------------------

        # Filter out existing SystemMessages and Deletion Stubs to prevent token bloat and serialization crashes
        filtered_messages = [m for m in state.get("messages", []) if not isinstance(m, (SystemMessage, RemoveMessage))]
        
        # --- [HARDENING: IDENTITY ENRICHMENT] ---
        # Append a "Last Thought" identity anchor at the end of the history to prevent drift.
        # This ensures the model's immediate context is its specialized identity and active toolset.
        final_reminder = SystemMessage(content=(
            f"REMINDER: You are the {agent_name.replace('_', ' ')}. "
            f"Your active tools are: [{', '.join(policy.allowed_tools) or 'none'}]. "
            "Use them immediately if technical evidence is needed."
        ))
        
        # --- [QUANTAMP INTEGRATION: APS] ---
        # Sense environment before execution
        aps_state = PrecisionManager.sense_environment()
        aps_weights = PrecisionManager.get_pulse_weights(aps_state)
        duty_cycle = PrecisionManager.biological_duty_cycle(aps_state)
        
        system_logger.info(f"APS RESOURCE SENSE: state={aps_state} duty_cycle={duty_cycle}s")
        # NOTE: Blocking time.sleep() removed — it was injecting 0.2–2.0s of pure
        # delay on every worker turn. APS weights are still forwarded to the prompt
        # for the model to self-regulate; hardware-level throttling belongs in the
        # infrastructure layer, not inside the LLM invocation hot path.

        # --- [QUANTAMP INTEGRATION: AMP-Q] ---
        if state.get("amp_q_correlation_id"):
            correlation_id = state["amp_q_correlation_id"]
            running_context = state.get("amp_q_context") or ""
            # Prepare the atomic segment prompt
            segment_task = AtomicManager.create_atomic_task(
                segment=blueprint.system_prompt,
                current=1, total=1, 
                correlation_id=correlation_id,
                running_context=running_context
            )
            # Inject APS weights into the segment directive if needed
            aps_directive = f"\nAPS_PRECISION_RIPPLE: {aps_state}\n"
            agent_sys = SystemMessage(
                content=aps_directive
                + segment_task
                + identity_anchor
                + project_invariants
                + module_directive
                + plan_directive
                + policy_directive
                + evidence_directive
            )

        try:
            response = agent_llm.invoke([agent_sys] + filtered_messages + [final_reminder])
        except Exception:
            record_agent_completion(agent_name, success=False)
            raise
        record_agent_completion(agent_name, success=True)
        
        from src.core.state import TokenUsage
        current_tokens = state.get('cumulative_tokens') or TokenUsage()
        new_total = current_tokens.total_tokens
        
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            new_total += response.usage_metadata.get('total_tokens', 0)
        elif hasattr(response, 'response_metadata') and response.response_metadata:
            new_total += response.response_metadata.get('token_usage', {}).get('total_tokens', 0)
        
        result = {
            "messages": [response],
            "active_worker": agent_name,
            "current_step_id": agent_name,
            "cumulative_tokens": TokenUsage(total_tokens=new_total),
            "agent_selection": explain_agent_choice(
                agent_name,
                [capability.name for capability in active_step.required_capabilities] if active_step else policy.capabilities,
                risk=run_risk,
                reason="Worker executed under capability policy.",
            ),
        }
        if state.get("run_plan") and not getattr(response, "tool_calls", None):
            updated_plan = complete_active_step(state.get("run_plan"), agent_name)
            if updated_plan:
                result["run_plan"] = public_plan(updated_plan)
                result["current_plan_step"] = updated_plan.current_step_id
        return result
    return worker_node
