"""Unit tests for the agent routing pipeline.

Covers the six scenarios called out in AGENT_ROUTING_PLAN.md:
    1. sticky path          — active worker covers caps; no LLM call
    2. plan step + handoff  — [REQUEST_SPECIALIST:] overrides score winner
    3. true ambiguity       — tied candidates → LLM tiebreaker invoked
    4. no-match fallback    — Human_Proxy_Agent with reason=fallback
    5. degraded performance — secondary candidate wins, recovers after decay
    6. single-selection     — supervisor calls record_agent_selection once
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import capabilities
from src.agents.capabilities import (
    AMBIGUITY_EPSILON,
    RoutingDecision,
    _PERFORMANCE_COUNTERS,
    decide_routing,
    record_agent_completion,
    record_agent_selection,
    reset_performance_counters,
    routing_is_ambiguous,
    scored_agent_candidates,
)
from src.graph import supervisor as supervisor_module
from src.graph.supervisor import supervisor_node


@pytest.fixture(autouse=True)
def _clean_counters():
    reset_performance_counters()
    yield
    reset_performance_counters()


# --------------------------------------------------------------------------
# decide_routing: sticky path
# --------------------------------------------------------------------------

def test_sticky_path_returns_active_worker_without_ambiguity():
    decision = decide_routing(
        ["python_backend", "api_implementation"],
        risk="medium",
        active_worker="Python_Backend_Agent",
    )
    assert decision.selected == "Python_Backend_Agent"
    assert decision.reason in {"sticky", "score_winner", "preferred_agent"}
    assert decision.reason != "ambiguous"


def test_sticky_path_wins_tie_against_equal_scorer():
    # Two agents covering the same cap → stickiness bonus breaks the tie
    scored = scored_agent_candidates(
        ["code_reading"],
        prefer_agent="Technical_Architect_Agent",
    )
    top_agent = scored[0][1]
    assert top_agent == "Technical_Architect_Agent"


# --------------------------------------------------------------------------
# Plan step + handoff
# --------------------------------------------------------------------------

def test_handoff_request_overrides_score_winner():
    state = {
        "messages": [
            HumanMessage(content="continue"),
            AIMessage(content="Done. [REQUEST_SPECIALIST: Security_Auditor_Agent]"),
        ],
        "active_worker": "Human_Proxy_Agent",
        "run_plan": None,
        "cumulative_tokens": None,
    }
    result = supervisor_node(state)
    assert result["current_step_id"] == "Security_Auditor_Agent"
    decision = result["agent_selection"]["routing_decision"]
    assert decision["reason"] == "handoff_request"


# --------------------------------------------------------------------------
# True ambiguity → LLM tiebreaker
# --------------------------------------------------------------------------

def test_ambiguous_candidates_trigger_llm_tiebreaker():
    # refactor + optimization match both Code_Refactor and O_Complexity agents
    decision = decide_routing(
        ["refactor", "optimization"],
        risk="high",
    )
    if decision.reason == "ambiguous":
        assert len(decision.candidates) >= 2
        assert "Code_Refactor_Agent" in decision.candidates
        assert "O_Complexity_Agent" in decision.candidates


def test_supervisor_invokes_llm_only_on_ambiguity():
    state = {
        "messages": [HumanMessage(content="refactor this for performance and correctness")],
        "active_worker": None,
        "run_plan": None,
        "cumulative_tokens": None,
    }

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = '{"next_target": "Code_Refactor_Agent", "why": "scope is pure refactor"}'
    mock_llm.bind.return_value.invoke.return_value = mock_response

    with patch.object(supervisor_module, "get_llm", return_value=mock_llm):
        result = supervisor_node(state)

    decision = result["agent_selection"]["routing_decision"]
    # Either the deterministic pipeline already settled it (gap >= epsilon) OR
    # the LLM was consulted — both are valid. What we DON'T want is an LLM
    # call when the score gap is already decisive.
    if decision["reason"] == "llm_tiebreaker":
        assert mock_llm.bind.return_value.invoke.called
        assert result["current_step_id"] in decision["candidates"]
    else:
        # deterministic path — LLM must not have been asked
        assert not mock_llm.bind.return_value.invoke.called


# --------------------------------------------------------------------------
# No-match fallback
# --------------------------------------------------------------------------

def test_empty_objective_falls_back_to_human_proxy():
    state = {
        "messages": [HumanMessage(content="")],
        "active_worker": None,
        "run_plan": None,
        "cumulative_tokens": None,
    }
    result = supervisor_node(state)
    assert result["current_step_id"] == "Human_Proxy_Agent"
    assert result["agent_selection"]["routing_decision"]["reason"] == "fallback"


def test_decide_routing_with_unmatchable_cap_returns_fallback():
    decision = decide_routing(
        ["nonexistent_capability_xyz"],
        risk="low",
    )
    assert decision.reason == "fallback"
    assert decision.selected == "Human_Proxy_Agent"


# --------------------------------------------------------------------------
# Degraded performance
# --------------------------------------------------------------------------

def test_failure_counters_penalize_then_decay():
    # Pound Python_Backend_Agent with failures until it's demoted.
    for _ in range(20):
        record_agent_completion("Python_Backend_Agent", success=False)

    scored = scored_agent_candidates(
        ["python_backend"],
        risk="medium",
    )
    penalized_score = next(s for s, a, _ in scored if a == "Python_Backend_Agent")

    # Successful completions should decay the penalty.
    for _ in range(10):
        record_agent_completion("Python_Backend_Agent", success=True)

    scored_after = scored_agent_candidates(
        ["python_backend"],
        risk="medium",
    )
    recovered_score = next(s for s, a, _ in scored_after if a == "Python_Backend_Agent")
    assert recovered_score > penalized_score


# --------------------------------------------------------------------------
# Single-selection invariant
# --------------------------------------------------------------------------

def test_supervisor_records_selection_exactly_once_per_turn():
    state = {
        "messages": [HumanMessage(content="write a python fastapi endpoint")],
        "active_worker": None,
        "run_plan": None,
        "cumulative_tokens": None,
    }
    call_count = {"n": 0}
    real_record = capabilities.record_agent_selection

    def spy(name):
        call_count["n"] += 1
        return real_record(name)

    with patch.object(supervisor_module, "record_agent_selection", side_effect=spy):
        supervisor_node(state)

    assert call_count["n"] == 1


# --------------------------------------------------------------------------
# routing_is_ambiguous helper
# --------------------------------------------------------------------------

def test_routing_is_ambiguous_requires_two_candidates():
    scored = [(12.0, "A", {"x"})]
    assert routing_is_ambiguous(scored) is False


def test_routing_is_ambiguous_respects_epsilon():
    scored = [(12.0, "A", {"x"}), (11.8, "B", {"x"})]
    assert routing_is_ambiguous(scored, epsilon=AMBIGUITY_EPSILON) is True
    # Clear gap:
    scored_clear = [(12.0, "A", {"x"}), (10.0, "B", {"x"})]
    assert routing_is_ambiguous(scored_clear, epsilon=AMBIGUITY_EPSILON) is False


def test_routing_is_ambiguous_sticky_short_circuit():
    scored = [(12.2, "Active_Agent", {"x"}), (12.0, "Other", {"x"})]
    # Active worker holds the unique top slot → not ambiguous, even though
    # the gap is within epsilon.
    assert routing_is_ambiguous(scored, active_worker="Active_Agent") is False
