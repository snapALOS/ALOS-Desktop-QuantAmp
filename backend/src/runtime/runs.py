from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple
from langchain_core.messages import RemoveMessage

from src.api.database import (
    create_run_checkpoint,
    create_run,
    get_active_run_for_session,
    get_run,
    get_run_checkpoints,
    get_run_events,
    update_run,
)
from src.runtime.events import record_event

_active_run_id: ContextVar[str] = ContextVar("alos_active_run_id", default="")
_active_run_session_id: ContextVar[str] = ContextVar("alos_active_run_session_id", default="")


def set_run_context(run_id: str, session_id: str):
    return (
        _active_run_id.set(run_id or ""),
        _active_run_session_id.set(session_id or ""),
    )


def reset_run_context(tokens) -> None:
    run_token, session_token = tokens
    _active_run_id.reset(run_token)
    _active_run_session_id.reset(session_token)


def current_run_context() -> Tuple[str, str]:
    return _active_run_id.get(), _active_run_session_id.get()


def _token_total(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return int(value.get("total_tokens", 0) or 0)
    return int(getattr(value, "total_tokens", 0) or 0)


def build_resume_metadata(state: Dict[str, Any], *, active_worker: str = None, last_node: str = None) -> Dict[str, Any]:
    run_plan = state.get("run_plan")
    # Filter out RemoveMessage stubs before calculating metadata/count to prevent serialization poisoning
    raw_messages = state.get("messages", []) or []
    filtered_messages = [m for m in raw_messages if not isinstance(m, RemoveMessage)]
    
    return {
        "active_worker": active_worker or state.get("active_worker") or "",
        "current_step_id": state.get("current_step_id") or "",
        "current_plan_step": state.get("current_plan_step") or "",
        "last_node": last_node or state.get("last_node") or "",
        "run_plan": run_plan,
        "module_context": state.get("module_context") or {},
        "logic_cycle_count": int(state.get("logic_cycle_count") or 0),
        "logic_trace": list(state.get("logic_trace") or [])[-20:],
        "stuck_reason": state.get("stuck_reason") or "",
        "token_total": _token_total(state.get("cumulative_tokens")),
        "message_count": len(filtered_messages),
    }


def start_run(session_id: str, objective: str, state: Optional[Dict[str, Any]] = None) -> str:
    resume_state = build_resume_metadata(state or {}, active_worker=(state or {}).get("active_worker"))
    run_id = create_run(session_id, objective, resume_state=resume_state)
    record_event(
        run_id,
        session_id,
        "run_started",
        {"objective": objective},
        active_worker=resume_state.get("active_worker"),
    )
    return run_id


def persist_resume_state(run_id: str, session_id: str, state: Dict[str, Any], *, active_worker: str = None, last_node: str = None) -> Dict[str, Any]:
    metadata = build_resume_metadata(state, active_worker=active_worker, last_node=last_node)
    checkpoint = create_run_checkpoint(run_id, session_id, node=last_node, state=metadata)
    metadata["last_checkpoint_id"] = checkpoint["id"]
    metadata["checkpoint_sequence"] = checkpoint["sequence"]
    update_run(
        run_id,
        active_worker=metadata.get("active_worker"),
        token_total=metadata.get("token_total"),
        resume_state=metadata,
    )
    return metadata


def mark_run_completed(run_id: str, session_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    metadata = persist_resume_state(run_id, session_id, state)
    event = record_event(run_id, session_id, "run_completed", {"status": "completed"}, active_worker=metadata.get("active_worker"))
    update_run(run_id, status="completed", resume_state=metadata)
    return event


def mark_run_failed(run_id: str, session_id: str, state: Dict[str, Any], reason: str, *, node: str = None) -> Dict[str, Any]:
    metadata = persist_resume_state(run_id, session_id, state, last_node=node)
    event = record_event(
        run_id,
        session_id,
        "run_failed",
        {"reason": reason, "last_node": node or metadata.get("last_node", "")},
        node=node,
        active_worker=metadata.get("active_worker"),
    )
    update_run(run_id, status="failed", error=reason, resume_state=metadata)
    return event


def mark_run_stuck(run_id: str, session_id: str, state: Dict[str, Any], reason: str, *, node: str = None) -> Dict[str, Any]:
    state["stuck_reason"] = reason
    metadata = persist_resume_state(run_id, session_id, state, last_node=node)
    event = record_event(
        run_id,
        session_id,
        "run_stuck",
        {
            "reason": reason,
            "last_node": node or metadata.get("last_node", ""),
            "recovery": ["stop", "revise_request", "resume_after_review"],
        },
        node=node,
        active_worker=metadata.get("active_worker"),
    )
    update_run(run_id, status="stuck", error=reason, resume_state=metadata)
    return event


def mark_run_cancelled(run_id: str, session_id: str, state: Dict[str, Any], reason: str) -> Dict[str, Any]:
    metadata = persist_resume_state(run_id, session_id, state)
    event = record_event(run_id, session_id, "run_cancelled", {"reason": reason}, active_worker=metadata.get("active_worker"))
    update_run(
        run_id,
        status="cancelled",
        error=reason,
        resume_state=metadata,
        cancellation_reason=reason,
    )
    return event


def replay_run(run_id: str) -> Dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {}
    events = get_run_events(run_id)
    checkpoints = get_run_checkpoints(run_id)
    last_event = events[-1] if events else None
    return {
        "run": run,
        "events": events,
        "checkpoints": checkpoints,
        "last_event": last_event,
        "active_worker": run.get("active_worker") or (last_event or {}).get("active_worker"),
        "resume_state": run.get("resume_state") or {},
    }


def active_session_run(session_id: str) -> Dict[str, Any]:
    run = get_active_run_for_session(session_id)
    if not run:
        return {}
    replay = replay_run(run["id"])
    return replay or {"run": run, "events": [], "last_event": None, "resume_state": run.get("resume_state") or {}}
