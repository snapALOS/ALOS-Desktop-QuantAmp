from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from alos_current.service import AlosCurrentService
from alos_current.storage import AlosCurrentStore
from src.auth.api_key_manager import get_api_key_manager
from src.auth.rbac import RBAC_DISABLED, require_audit_read, require_run_create, require_run_read, require_run_write
from src.core.config import USER_DATA_DIR

router = APIRouter()

store = AlosCurrentStore(Path(USER_DATA_DIR) / "current")
service = AlosCurrentService(store)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, (KeyError, ValueError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _stream_authorized(api_key: str | None) -> str:
    if RBAC_DISABLED:
        return "emergency_access"
    if not api_key:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_info = get_api_key_manager().validate_api_key(api_key)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return str(user_info["user_id"])


@router.get("/health")
def health(_: str = Depends(require_run_read)):
    return service.health()


@router.get("/nodes")
def list_nodes(_: str = Depends(require_run_read)):
    return service.nodes()


@router.get("/workflows")
def list_workflows(_: str = Depends(require_run_read)):
    return service.list_workflows()


@router.post("/workflows")
def create_workflow(payload: dict[str, Any] = Body(...), _: str = Depends(require_run_write)):
    try:
        return service.create_workflow(payload)
    except Exception as exc:
        _handle_error(exc)


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, _: str = Depends(require_run_read)):
    try:
        return {"workflow": service.get_workflow(workflow_id)}
    except Exception as exc:
        _handle_error(exc)


@router.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, payload: dict[str, Any] = Body(...), _: str = Depends(require_run_write)):
    try:
        return service.update_workflow(workflow_id, payload)
    except Exception as exc:
        _handle_error(exc)


@router.delete("/workflows/{workflow_id}")
def archive_workflow(workflow_id: str, _: str = Depends(require_run_write)):
    try:
        return service.archive_workflow(workflow_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/workflows/{workflow_id}/duplicate")
def duplicate_workflow(workflow_id: str, _: str = Depends(require_run_write)):
    try:
        return service.duplicate_workflow(workflow_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/workflows/{workflow_id}/validate")
def validate_workflow(workflow_id: str, _: str = Depends(require_run_read)):
    try:
        return service.validate_workflow(workflow_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/validate")
def validate_graph(payload: dict[str, Any] = Body(...), _: str = Depends(require_run_read)):
    graph = payload.get("graph")
    if not isinstance(graph, dict):
        raise HTTPException(status_code=400, detail="graph object required")
    try:
        return service.validate_workflow(graph=graph)
    except Exception as exc:
        _handle_error(exc)


@router.post("/workflows/{workflow_id}/publish")
def publish_workflow(workflow_id: str, user_id: str = Depends(require_run_write)):
    try:
        return service.publish_workflow(workflow_id, actor=user_id)
    except Exception as exc:
        _handle_error(exc)


@router.get("/workflows/{workflow_id}/versions")
def workflow_versions(workflow_id: str, _: str = Depends(require_run_read)):
    try:
        return service.versions(workflow_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/workflows/{workflow_id}/execute")
def execute_workflow(workflow_id: str, payload: dict[str, Any] = Body(default={}), _: str = Depends(require_run_create)):
    try:
        variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
        if payload.get("async", True):
            created = service.begin_execution(workflow_id, variables=variables)
            service.start_execution_async(created["execution"]["id"])
            return created
        return service.execute_workflow(workflow_id, variables=variables)
    except Exception as exc:
        _handle_error(exc)


@router.get("/executions")
def list_executions(_: str = Depends(require_run_read)):
    return service.executions()


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str, _: str = Depends(require_run_read)):
    try:
        return {"execution": service.get_execution(execution_id), "steps": service.steps(execution_id)["steps"]}
    except Exception as exc:
        _handle_error(exc)


@router.get("/executions/{execution_id}/steps")
def execution_steps(execution_id: str, _: str = Depends(require_run_read)):
    try:
        return service.steps(execution_id)
    except Exception as exc:
        _handle_error(exc)


@router.get("/executions/{execution_id}/events")
def execution_events(execution_id: str, _: str = Depends(require_run_read)):
    return service.events(execution_id=execution_id)


@router.post("/executions/{execution_id}/resume")
def resume_execution(execution_id: str, payload: dict[str, Any] = Body(default={}), _: str = Depends(require_run_write)):
    try:
        if payload.get("async", True):
            return service.start_execution_async(execution_id)
        return service.resume_execution(execution_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/executions/{execution_id}/retry")
def retry_execution(execution_id: str, payload: dict[str, Any] = Body(default={}), _: str = Depends(require_run_write)):
    try:
        if payload.get("async", True):
            service.store.execute("UPDATE executions SET status = ?, error = NULL, ended_at = NULL WHERE id = ?", ("pending", execution_id))
            return service.start_execution_async(execution_id)
        return service.retry_execution(execution_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/executions/{execution_id}/cancel")
def cancel_execution(execution_id: str, _: str = Depends(require_run_write)):
    try:
        return service.cancel_execution(execution_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/executions/{execution_id}/approve")
def approve_execution(execution_id: str, payload: dict[str, Any] = Body(...), _: str = Depends(require_run_write)):
    node_id = str(payload.get("nodeId") or "")
    if not node_id:
        raise HTTPException(status_code=400, detail="nodeId required")
    try:
        if payload.get("async", True):
            resolved = service.record_approval(execution_id, node_id=node_id, approved=bool(payload.get("approved", True)))
            service.start_execution_async(execution_id)
            return resolved
        return service.approve_execution(execution_id, node_id=node_id, approved=bool(payload.get("approved", True)))
    except Exception as exc:
        _handle_error(exc)


@router.post("/recover")
def recover_executions(_: str = Depends(require_run_write)):
    try:
        return service.recover()
    except Exception as exc:
        _handle_error(exc)


@router.post("/triggers/alos-hub")
def trigger_alos_hub(payload: dict[str, Any] = Body(...), _: str = Depends(require_run_create)):
    event_type = str(payload.get("eventType") or payload.get("type") or "")
    if not event_type:
        raise HTTPException(status_code=400, detail="eventType required")
    return service.execute_rexhub_event(event_type, payload)


@router.post("/schedules/run")
def run_schedules(payload: dict[str, Any] = Body(default={}), _: str = Depends(require_run_create)):
    schedule = payload.get("schedule")
    return service.run_schedules(str(schedule) if schedule else None)


@router.get("/events")
def list_events(executionId: str | None = Query(default=None), _: str = Depends(require_run_read)):
    return service.events(execution_id=executionId)


@router.get("/events/stream")
def stream_events(executionId: str | None = Query(default=None), api_key: str | None = Query(default=None)):
    _stream_authorized(api_key)

    async def event_generator():
        seen: set[str] = set()
        for _ in range(120):
            events = service.events(execution_id=executionId, limit=50)["events"]
            fresh = [event for event in reversed(events) if event["id"] not in seen]
            for event in fresh:
                seen.add(event["id"])
                payload = json.dumps(event, sort_keys=True)
                yield f"id: {event['id']}\nevent: alos_current\ndata: {payload}\n\n"
            if not fresh:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/tasks")
def list_tasks(_: str = Depends(require_run_read)):
    return service.tasks()


@router.post("/tasks")
def create_task(payload: dict[str, Any] = Body(...), _: str = Depends(require_run_write)):
    return service.create_task(payload)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, _: str = Depends(require_run_read)):
    try:
        return {"task": service.get_task(task_id)}
    except Exception as exc:
        _handle_error(exc)


@router.put("/tasks/{task_id}")
def update_task(task_id: str, payload: dict[str, Any] = Body(...), _: str = Depends(require_run_write)):
    try:
        return service.update_task(task_id, payload)
    except Exception as exc:
        _handle_error(exc)


@router.get("/swarm")
def swarm(_: str = Depends(require_run_read)):
    return service.swarm()


@router.get("/audit")
def audit(_: str = Depends(require_audit_read)):
    return service.audit_log()
