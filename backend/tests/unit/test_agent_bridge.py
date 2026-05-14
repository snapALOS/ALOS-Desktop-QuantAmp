import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from src.agents.invoke import run_agent_step
from modules.current.contracts.nodes.invoke_agent import InvokeAgentNodeInput

def test_run_agent_step_happy_path():
    """Verify that run_agent_step streams turns and emits events."""
    mock_input = InvokeAgentNodeInput(prompt="test prompt", max_turns=2)
    
    # Mock stream data
    mock_events = [
        {"agent_one": {"messages": [AIMessage(content="Turn one")]}},
        {"agent_two": {"messages": [AIMessage(content="Final answer")]}}
    ]
    
    mock_app = MagicMock()
    mock_app.stream.return_value = mock_events
    
    events_emitted = []
    def on_event(etype, payload):
        events_emitted.append((etype, payload))
        
    with patch("src.agents.invoke.build_orchestrator", return_value=mock_app):
        output = run_agent_step(
            mock_input,
            on_event=on_event,
            run_id="run123",
            step_id="step456"
        )
        
    assert output.status == "ok"
    assert output.output == "Final answer"
    assert output.turns_used == 2
    assert len(events_emitted) == 2
    assert events_emitted[0][0] == "current.agent_step.turn_completed"
    assert events_emitted[1][1]["agentId"] == "agent_two"

def test_run_agent_step_cancellation():
    """Verify that run_agent_step obeys the cancel_check."""
    mock_input = InvokeAgentNodeInput(prompt="long task", max_turns=10)
    
    # Infinite turns mock
    def infinite_stream(*args, **kwargs):
        while True:
            yield {"busy_agent": {"messages": [AIMessage(content="Still working...")]}}
            
    mock_app = MagicMock()
    mock_app.stream.side_effect = infinite_stream
    
    # Cancel after 3 turns
    turn_count = [0]
    def cancel_check():
        turn_count[0] += 1
        return turn_count[0] >= 3
        
    with patch("src.agents.invoke.build_orchestrator", return_value=mock_app):
        output = run_agent_step(
            mock_input,
            cancel_check=cancel_check
        )
        
    assert output.status == "cancelled"
    assert output.turns_used == 3
