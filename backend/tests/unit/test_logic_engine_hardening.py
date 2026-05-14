from __future__ import annotations

from langchain_core.messages import AIMessage

from src.api import database
from src.planning.planner import create_run_plan
from src.runtime import runs
from src.runtime.logic_engine import (
    LogicEngineStuck,
    normalize_module_context,
    record_engine_step,
    tool_idempotency_key,
)


def test_serious_plan_is_evidence_first():
    plan = create_run_plan("Fix the Forge backend API and verify with tests")
    data = plan.model_dump()

    assert data["verification_required"] is True
    assert data["evidence_requirements"]
    assert any("Atlas" in item for item in data["evidence_requirements"])
    assert "Verification evidence is produced before completion." in data["acceptance_criteria"]
    assert any("Forge" in item or "Backend" in item for item in data["affected_surfaces"])


def test_module_context_is_bounded_and_structured():
    context = normalize_module_context({
        "moduleId": "atlas",
        "moduleName": "Atlas",
        "payload": {"huge": "x" * 20000},
    })

    assert context["module_id"] == "atlas"
    assert context["module_name"] == "Atlas"
    assert context["payload"]["truncated"] is True
    assert context["payload"]["original_chars"] > 12000


def test_logic_guard_stops_repeated_agent_output():
    state = {"logic_trace": [], "logic_cycle_count": 0}
    node_state = {
        "active_worker": "Human_Proxy_Agent",
        "messages": [AIMessage(content="same answer")],
    }

    for _ in range(5):
        record_engine_step(state, "Human_Proxy_Agent", node_state)

    try:
        record_engine_step(state, "Human_Proxy_Agent", node_state)
    except LogicEngineStuck as exc:
        assert "repeated the same route/action signature" in exc.reason
    else:
        raise AssertionError("Expected repeated route/action detection")


def test_run_checkpoints_and_idempotency_records_are_replayable(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "alos.db"))
    database.init_db()

    session_id = database.create_session()["id"]
    run_id = runs.start_run(session_id, "Test durable run", {
        "module_context": {"module_id": "chat", "payload": {}},
    })

    metadata = runs.persist_resume_state(
        run_id,
        session_id,
        {
            "messages": [],
            "active_worker": "Unit_Tester_Agent",
            "module_context": {"module_id": "chat", "payload": {}},
            "logic_trace": [{"node": "Unit_Tester_Agent"}],
            "logic_cycle_count": 1,
        },
        active_worker="Unit_Tester_Agent",
        last_node="Unit_Tester_Agent",
    )

    key = tool_idempotency_key(run_id, "read_file_content", "tool-1", {"file_path": "README.md"})
    database.record_tool_idempotency(
        key,
        run_id,
        session_id,
        "read_file_content",
        status="completed",
        result={"content": "cached"},
    )

    replay = runs.replay_run(run_id)
    cached = database.get_tool_idempotency(key)

    assert metadata["last_checkpoint_id"]
    assert replay["checkpoints"]
    assert replay["resume_state"]["active_worker"] == "Unit_Tester_Agent"
    assert cached["result"]["content"] == "cached"

