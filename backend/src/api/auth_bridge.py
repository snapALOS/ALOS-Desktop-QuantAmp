import asyncio
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from src.runtime.events import tool_approved
from src.runtime.runs import current_run_context
from src.auth.api_key_manager import get_api_key_manager

_active_session_id: ContextVar[str] = ContextVar("alos_active_session_id", default="")
_active_user_id: ContextVar[Optional[str]] = ContextVar("alos_active_user_id", default=None)
_websockets: dict[str, Any] = {}
_pending_approvals: dict[str, asyncio.Future] = {}


def bind_websocket(session_id: str, ws):
    if ws is None:
        _websockets.pop(session_id, None)
    else:
        _websockets[session_id] = ws


def set_active_session(session_id: str):
    return _active_session_id.set(session_id)


def get_active_session() -> str:
    """Get the currently active session ID."""
    return _active_session_id.get()


def reset_active_session(token) -> None:
    _active_session_id.reset(token)


def set_active_user(user_id: Optional[str]):
    """Set the active user ID for the current context."""
    return _active_user_id.set(user_id)


def reset_active_user(token) -> None:
    _active_user_id.reset(token)


def get_active_user() -> Optional[str]:
    """Get the currently active user ID."""
    return _active_user_id.get()


async def wait_for_user_approval(file_path: str, content: str, *, diff: str = "", risk: str = "high") -> bool:
    session_id = _active_session_id.get()
    websocket = _websockets.get(session_id)
    
    if websocket:
        approval_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        _pending_approvals[approval_id] = future
        try:
            await websocket.send_json({
                "type": "auth_request",
                "approval_id": approval_id,
                "file_path": file_path,
                "content": content,
                "diff": diff,
                "risk": risk,
            })
            approved = bool(await asyncio.wait_for(future, timeout=900))
            run_id, session_id = current_run_context()
            if run_id and session_id:
                tool_approved(run_id, session_id, "write_system_file", approved, node="auth_bridge")
            return approved
        except Exception:
            return False
        finally:
            _pending_approvals.pop(approval_id, None)
    else:
        print("\\n===========================================================")
        print("!!     CRITICAL AUTHORIZATION REQUIRED: DISK WRITE      !!")
        print(f">> Agent requests physical modification of: {file_path}")
        if diff:
            print(diff[:4000])
        print("-----------------------------------------------------------")
        approved = input(f">> Approve writing logic payload? (y/n): ").strip().lower() == 'y'
        run_id, session_id = current_run_context()
        if run_id and session_id:
            tool_approved(run_id, session_id, "write_system_file", approved, node="auth_bridge")
        return approved


async def wait_for_patch_approval(proposal: dict[str, Any], *, risk: str = "high") -> bool:
    session_id = _active_session_id.get()
    websocket = _websockets.get(session_id)
    if websocket:
        approval_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        _pending_approvals[approval_id] = future
        try:
            await websocket.send_json({
                "type": "patch_request",
                "approval_id": approval_id,
                "proposal": proposal,
                "risk": risk,
            })
            approved = bool(await asyncio.wait_for(future, timeout=900))
            run_id, session_id = current_run_context()
            if run_id and session_id:
                tool_approved(run_id, session_id, "propose_patch", approved, node="auth_bridge")
            return approved
        except Exception:
            return False
        finally:
            _pending_approvals.pop(approval_id, None)

    print("\\n===========================================================")
    print("!!             PATCH APPROVAL REQUIRED                  !!")
    print(f">> Agent proposes patch for: {proposal.get('file')}")
    print(str(proposal.get("diff", ""))[:4000])
    print("-----------------------------------------------------------")
    approved = input(">> Approve applying patch? (y/n): ").strip().lower() == "y"
    run_id, session_id = current_run_context()
    if run_id and session_id:
        tool_approved(run_id, session_id, "propose_patch", approved, node="auth_bridge")
    return approved


async def wait_for_plan_approval(plan: dict[str, Any], *, risk: str = "high") -> bool:
    session_id = _active_session_id.get()
    websocket = _websockets.get(session_id)
    if websocket:
        approval_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        _pending_approvals[approval_id] = future
        try:
            await websocket.send_json({
                "type": "plan_approval_request",
                "approval_id": approval_id,
                "plan": plan,
                "risk": risk,
            })
            return bool(await asyncio.wait_for(future, timeout=900))
        except Exception:
            return False
        finally:
            _pending_approvals.pop(approval_id, None)

    print("\\n===========================================================")
    print("!!              RUN PLAN APPROVAL REQUIRED              !!")
    print(f">> Risk: {risk}")
    print(f">> Objective: {plan.get('objective', '')}")
    for step in plan.get("steps", []):
        print(f" - {step.get('title')} -> {step.get('assigned_agent')}")
    print("-----------------------------------------------------------")
    return input(">> Approve executing this plan? (y/n): ").strip().lower() == "y"


def resolve_auth(approval_id: str, approved: bool):
    future = _pending_approvals.get(approval_id)
    if future and not future.done():
        future.set_result(bool(approved))


def resolve_plan_approval(approval_id: str, approved: bool):
    resolve_auth(approval_id, approved)