from typing import Any, Dict, Optional

from src.api.database import record_run_event


RUN_EVENT_TYPES = {
    "run_started",
    "node_started",
    "tool_requested",
    "tool_approved",
    "tool_completed",
    "step_completed",
    "run_failed",
    "run_cancelled",
    "run_completed",
    "resume_state_saved",
    "agent_selected",
    "tool_denied",
    # Logic engine diagnostic emitted from run_swarm_background after every
    # node step (see src/api/server.py ~L822). Payload is the output of
    # record_engine_step — cycle_count + node signature — used by the UI
    # to show loop-detection telemetry. Must be whitelisted here or the
    # whole run fails with "Unsupported run event type: logic_guard_step".
    "logic_guard_step",
    # Emitted by mark_run_stuck (src/runtime/runs.py) when the logic engine
    # detects a plan loop / cycle exhaustion. Missing from the whitelist
    # would mask the real "stuck" error with the secondary ValueError.
    "run_stuck",
}


def _safe_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cleaned = {}
    for key, value in (payload or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        elif isinstance(value, list):
            cleaned[key] = [
                item if isinstance(item, (str, int, float, bool)) or item is None else str(item)
                for item in value[:50]
            ]
        elif isinstance(value, dict):
            cleaned[key] = {
                str(child_key): child_value if isinstance(child_value, (str, int, float, bool)) or child_value is None else str(child_value)
                for child_key, child_value in list(value.items())[:50]
            }
        else:
            cleaned[key] = str(value)
    return cleaned


def record_event(
    run_id: str,
    session_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    node: str = None,
    active_worker: str = None,
) -> Dict[str, Any]:
    if not run_id or not session_id:
        return {}
    if event_type not in RUN_EVENT_TYPES:
        raise ValueError(f"Unsupported run event type: {event_type}")
    event = record_run_event(
        run_id,
        session_id,
        event_type,
        _safe_payload(payload),
        node=node,
        active_worker=active_worker,
    )
    try:
        from src.runtime.scout import emit_scout_event

        emit_scout_event(
            source="backend.run",
            level="error" if event_type in {"run_failed", "run_stuck"} else "info",
            event_type=event_type,
            message=f"{event_type} {node or active_worker or ''}".strip(),
            module=node,
            run_id=run_id,
            session_id=session_id,
            payload=event,
        )
    except Exception:
        pass
    return event


def node_started(run_id: str, session_id: str, node: str, active_worker: str = None) -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "node_started",
        {"node": node},
        node=node,
        active_worker=active_worker,
    )


def agent_selected(run_id: str, session_id: str, selection: Dict[str, Any], node: str = "supervisor_node") -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "agent_selected",
        selection or {},
        node=node,
        active_worker=(selection or {}).get("agent"),
    )


def tool_requested(run_id: str, session_id: str, tool_name: str, tool_id: str = "", node: str = None) -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "tool_requested",
        {"tool_name": tool_name, "tool_id": tool_id},
        node=node,
    )


def tool_approved(run_id: str, session_id: str, tool_name: str, approved: bool, node: str = None) -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "tool_approved",
        {"tool_name": tool_name, "approved": approved},
        node=node,
    )


def tool_denied(
    run_id: str,
    session_id: str,
    tool_name: str,
    tool_id: str = "",
    *,
    active_worker: str = None,
    reason: str = "",
    node: str = None,
) -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "tool_denied",
        {"tool_name": tool_name, "tool_id": tool_id, "reason": reason},
        node=node,
        active_worker=active_worker,
    )


def tool_completed(run_id: str, session_id: str, tool_name: str, tool_id: str = "", ok: bool = True, node: str = None) -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "tool_completed",
        {"tool_name": tool_name, "tool_id": tool_id, "ok": ok},
        node=node,
    )


def step_completed(run_id: str, session_id: str, step_id: str, step_title: str, active_worker: str = None) -> Dict[str, Any]:
    return record_event(
        run_id,
        session_id,
        "step_completed",
        {"step_id": step_id, "step_title": step_title},
        active_worker=active_worker,
    )
