from src.api import database
from src.runtime import scout
from src.tools.registry import scout_query
from src.agents.capabilities import policy_for_agent, tool_allowed


def test_scout_events_are_recorded_listed_and_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "alos.db"))
    database.init_db()

    event = scout.emit_scout_event(
        source="test",
        level="error",
        event_type="unit.failure",
        message="token sk-testsecretsecretsecretsecret",
        module="unit",
        payload={"api_key": "abc123456789"},
    )

    assert event["source"] == "test"
    assert event["level"] == "error"
    assert "[REDACTED_SECRET]" in event["message"]

    events = scout.list_scout_events(limit=10, level="error")
    assert len(events) == 1
    assert events[0]["event_type"] == "unit.failure"
    assert events[0]["payload"]["api_key"] == "[REDACTED_SECRET]"


def test_agents_can_query_scout(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "alos.db"))
    database.init_db()
    scout.emit_scout_event(
        source="backend.run",
        level="error",
        event_type="run_failed",
        message="exploded in forge",
        module="forge",
    )

    result = scout_query.invoke({"q": "exploded", "level": "error", "limit": 5})

    assert result["status"] == "success"
    assert result["count"] == 1
    assert result["events"][0]["event_type"] == "run_failed"
    assert tool_allowed("Human_Proxy_Agent", "scout_query")
    assert "scout_query" in policy_for_agent("Python_Backend_Agent").allowed_tools
