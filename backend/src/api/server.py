from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.auth.rbac import get_rbac_manager, RBACManager, initialize_rbac, RBAC_DISABLED, security, require_memory_read, require_memory_write, require_session_read, require_session_write, require_run_create, require_run_read, require_run_write, require_patch_read, require_patch_write, require_settings_read, require_settings_write, require_user_read, require_user_write, require_apikey_read, require_apikey_write, require_audit_read, require_admin_access
import asyncio
import json
import importlib
import os
import sys
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from langchain_core.messages import HumanMessage, messages_to_dict, messages_from_dict, RemoveMessage
from src.graph.builder import build_orchestrator
from src.core.state import TokenUsage
from src.api.auth_bridge import bind_websocket, reset_active_session, reset_active_user, resolve_auth, resolve_plan_approval, set_active_session, set_active_user, wait_for_plan_approval
from src.core.config import DATA_DIR, ENV_PATH, LOGS_DIR, ROOT_DIR, USER_DATA_DIR, clear_provider_config, config as alos_config, reset_log_session, set_log_session, system_logger, write_env_config
from src.core.policy import public_policy_snapshot
from src.core.setup import setup_status, validate_provider_connection, validate_provider_payload
from src.api.database import (
    assign_session_project,
    create_project,
    create_session,
    delete_project,
    delete_session,
    get_all_projects,
    get_all_sessions,
    get_recent_runs,
    get_session_state,
    update_project,
    update_run,
    update_session,
    get_db_connection,
)
from src.memory.vector_store import MemoryCheckpointStore
from src.memory.retrieval import public_search
from src.planning.planner import approve_plan, create_run_plan, failed_step_label, fail_active_step, has_incomplete_required_verification, public_plan
from src.runtime.events import agent_selected, node_started, record_event, step_completed
from src.runtime.scout import (
    emit_scout_event,
    install_scout_logging,
    list_scout_events,
    register_event_bus_scout,
    subscribe_scout_events,
)
from src.runtime.runs import (
    active_session_run,
    mark_run_cancelled,
    mark_run_completed,
    mark_run_failed,
    mark_run_stuck,
    persist_resume_state,
    replay_run,
    reset_run_context,
    set_run_context,
    start_run,
)
from src.runtime.logic_engine import LogicEngineStuck, normalize_module_context, record_engine_step
from src.tools.patching import apply_patch_by_id, list_patch_proposals, propose_and_save_patch, public_patch_payload, reject_patch_proposal
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from src.auth.role_definitions import Role, Permission
from src.auth.api_key_manager import get_api_key_manager

active_tasks: dict[str, asyncio.Task] = {}


def _make_task_cleanup(session_id: str):
    """Return a done-callback that removes the task from active_tasks when it finishes."""
    def _cleanup(task: asyncio.Task) -> None:
        if active_tasks.get(session_id) is task:
            del active_tasks[session_id]
    return _cleanup


async def safe_send_json(websocket, ws_send_lock: asyncio.Lock, payload: dict) -> bool:
    try:
        async with ws_send_lock:
            await websocket.send_json(payload)
        return True
    except Exception:
        return False


def newly_completed_steps(before_plan: dict, after_plan: dict) -> list[dict]:
    if not before_plan or not after_plan:
        return []
    before = {
        step.get("id"): step.get("status")
        for step in before_plan.get("steps", [])
    }
    completed = []
    for step in after_plan.get("steps", []):
        step_id = step.get("id")
        if step_id and before.get(step_id) != "complete" and step.get("status") == "complete":
            completed.append(step)
    return completed


def serialize_token_usage(tokens):
    if hasattr(tokens, "model_dump"):
        return tokens.model_dump()
    if hasattr(tokens, "dict"):
        return tokens.dict()
    return tokens


class WebSocketLogHandler(logging.Handler):
    def __init__(self, websocket, loop, ws_send_lock, session_id: str):
        super().__init__()
        self.websocket = websocket
        self.loop = loop
        self.ws_send_lock = ws_send_lock
        self.session_id = session_id
        self._is_sending = False

    def emit(self, record):
        if self._is_sending:
            return
        try:
            record_session = getattr(record, "alos_session_id", "-")
            if record_session != self.session_id:
                return
            msg = self.format(record)
            # Skip messages that mention WebSocket sending to prevent infinite loops
            if "websocket" in msg.lower() or "send_json" in msg.lower():
                return

            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._send_to_ws(msg))
            )
        except Exception:
            self.handleError(record)

    async def _send_to_ws(self, msg):
        if self._is_sending:
            return
        async with self.ws_send_lock:
            self._is_sending = True
            try:
                await self.websocket.send_json({"type": "system_log", "content": msg})
            except Exception:
                pass
            finally:
                self._is_sending = False


from src.core.event_bus import autowire_to_stdout
autowire_to_stdout()
install_scout_logging()
register_event_bus_scout()

initialize_rbac()
rbac_manager = get_rbac_manager()
app = FastAPI(
    title="ALOS API",
    description="Automated Local OS Core Orchestrator API - Enterprise Cognitive Architecture",
    version="1.0.0",
    docs_url=None,  # Disable default docs to customize
    redoc_url=None  # Disable default redoc to customize
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(tauri://localhost|https?://(tauri\.localhost|localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_static_dir() -> Path | None:
    candidates: list[Path] = []
    env_dir = os.environ.get("ALOS_STATIC_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir).expanduser())

    candidates.extend([
        Path.cwd() / "public",
        Path.cwd() / "dist",
        Path(__file__).resolve().parents[3] / "public",
        Path(__file__).resolve().parents[3] / "dist",
    ])

    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


STATIC_DIR = resolve_static_dir()


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )


@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_endpoint():
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )


if STATIC_DIR is not None:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    system_logger.info("No static asset directory found; skipping /static mount.")


def discover_and_mount_modules(app: FastAPI):
    """
    Scans the ../modules directory for ALOS modules and mounts their
    backend routers if they exist.
    """
    module_roots = [
        Path(__file__).resolve().parents[3] / "modules",
        ROOT_DIR.parent / "modules",
        ROOT_DIR.parent.parent / "modules",
        Path.cwd() / "modules",
    ]
    modules_root = next((path for path in module_roots if path.is_dir()), None)
    if modules_root is None:
        candidates = ", ".join(str(path) for path in module_roots)
        system_logger.warning(f"Modules root not found. Checked: {candidates}")
        return

    for module_dir in modules_root.iterdir():
        if not module_dir.is_dir() or module_dir.name.startswith("_"):
            continue

        module_id = module_dir.name
        # Check for module/backend/src/api/router.py
        router_path = module_dir / "backend" / "src" / "api" / "router.py"
        if router_path.exists():
            try:
                # Dynamic import using spec to avoid sys.path pollution and collisions
                # between modules that all use the 'api.router' package name.
                spec = importlib.util.spec_from_file_location(f"alos_module_{module_id}", str(router_path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    backend_src = str(module_dir / "backend" / "src")
                    if backend_src not in sys.path:
                        sys.path.insert(0, backend_src)
                    
                    try:
                        spec.loader.exec_module(module)
                    except Exception as e:
                        system_logger.error(f"Error executing module {module_id}: {e}")
                        continue

                    if hasattr(module, "router"):
                        app.include_router(module.router, prefix=f"/api/{module_id}", tags=[module_id])
                        system_logger.info(f"Mounted module backend: {module_id} -> /api/{module_id}")
                    else:
                        system_logger.warning(f"Module {module_id} has router.py but no 'router' object found.")
            except Exception as e:
                system_logger.error(f"Failed to mount module {module_id}: {e}")


discover_and_mount_modules(app)


@app.get("/")
def get_index():
    if STATIC_DIR is not None:
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
    return {"status": "ok", "service": "ALOS API"}


@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "configured": alos_config.is_configured(),
        "provider": alos_config.llm_provider,
        "model": alos_config.model_name,
    }


@app.get("/api/scout/events")
def api_scout_events(
    limit: int = 500,
    source: Optional[str] = None,
    level: Optional[str] = None,
    module: Optional[str] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    q: Optional[str] = None,
    user_id: str = Depends(require_audit_read),
):
    return {
        "events": list_scout_events(
            limit=limit,
            source=source,
            level=level,
            module=module,
            run_id=run_id,
            session_id=session_id,
            q=q,
        )
    }


@app.post("/api/scout/events")
async def api_scout_record_event(request: Request, user_id: str = Depends(require_audit_read)):
    body = await request.json()
    return emit_scout_event(
        source=str(body.get("source") or "frontend"),
        level=str(body.get("level") or "info"),
        event_type=str(body.get("event_type") or body.get("type") or "event"),
        message=str(body.get("message") or ""),
        module=body.get("module"),
        run_id=body.get("run_id"),
        session_id=body.get("session_id"),
        payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
    )


@app.post("/auth/validate")
async def auth_validate(request: Request):
    """Validate an API key and return user info. Used by frontend on startup."""
    body = await request.json()
    api_key = body.get("api_key", "")
    mgr = get_api_key_manager()
    user_info = mgr.validate_api_key(api_key)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return {"valid": True, "user": user_info}


@app.get("/auth/bootstrap/status")
def auth_bootstrap_status():
    """Public first-run status. Does not reveal keys or sensitive account data."""
    mgr = get_api_key_manager()
    status = mgr.original_admin_bootstrap_status()
    status["data_dir"] = str(USER_DATA_DIR)
    return status


@app.post("/auth/bootstrap/original-admin")
async def auth_bootstrap_original_admin(request: Request):
    """Create the original local admin only before any users exist."""
    body = await request.json()
    username = str(body.get("username") or "admin")
    key_name = body.get("key_name")
    mgr = get_api_key_manager()

    try:
        return mgr.create_original_admin(username=username, key_name=key_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/auth/me")
def auth_me(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Return current authenticated user info."""
    if RBAC_DISABLED:
        return {"user_id": "emergency_access", "role": "admin", "username": "emergency_access"}

    if credentials and credentials.credentials:
        user_info = get_api_key_manager().validate_api_key(credentials.credentials)
        if user_info:
            return {
                "user_id": user_info["user_id"],
                "username": user_info.get("username") or user_info["user_id"],
                "role": user_info.get("role") or "viewer",
            }

    user_id = rbac_manager.authenticate_request(request, credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user_id == "root_admin":
        return {"user_id": "root_admin", "username": "root_admin", "role": "admin"}
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, role FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
    if row:
        return {"user_id": user_id, "username": row[0], "role": row[1]}
    return {"user_id": user_id}


def _first_run_read(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Allow unauthenticated reads of setup status when the system hasn't
    been configured yet. Once configured, fall back to normal RBAC."""
    if not alos_config.is_configured():
        return "__bootstrap__"
    return require_settings_read(request, credentials)


def _first_run_write(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Same as _first_run_read but for the write-side setup endpoints."""
    if not alos_config.is_configured() or not setup_status().get("ready"):
        return "__bootstrap__"
    return require_settings_write(request, credentials)


def _read_app_version() -> str:
    for path in (ROOT_DIR.parent / "package.json", ROOT_DIR / "pyproject.toml"):
        try:
            if path.name == "package.json":
                return str(json.loads(path.read_text(encoding="utf-8")).get("version") or "unknown")
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            continue
    return "unknown"


def _settings_snapshot() -> dict:
    payload = alos_config.public_snapshot()
    payload["policy"] = public_policy_snapshot()
    payload["setup"] = setup_status()
    payload["diagnostics"] = {
        "status": "ok",
        "version": _read_app_version(),
        "data_dir": str(DATA_DIR),
        "logs_dir": str(LOGS_DIR),
        "user_data_dir": str(USER_DATA_DIR),
        "env_path": str(ENV_PATH),
        "backend_dir": str(ROOT_DIR),
        "configured": alos_config.is_configured(),
        "provider": alos_config.llm_provider,
        "model": alos_config.model_name,
    }
    return payload


@app.get("/api/settings")
def api_get_settings(user_id: str = Depends(_first_run_read)):
    return _settings_snapshot()


@app.put("/api/settings")
async def api_update_settings(request: Request, user_id: str = Depends(_first_run_write)):
    payload = await request.json()
    validation = validate_provider_payload(payload)
    if not validation["ok"]:
        raise HTTPException(status_code=400, detail=validation)
    try:
        write_env_config(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"ok": False, "errors": [str(exc)]})
    return _settings_snapshot()


@app.delete("/api/settings/provider")
def api_clear_provider_settings(user_id: str = Depends(_first_run_write)):
    try:
        clear_provider_config()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"ok": False, "errors": [str(exc)]})
    return _settings_snapshot()


@app.get("/api/setup/status")
def api_setup_status():
    """Public readiness probe used before the frontend can decide auth/setup flow."""
    return setup_status()


@app.post("/api/setup/validate")
async def api_setup_validate(request: Request, user_id: str = Depends(_first_run_write)):
    payload = await request.json()
    return validate_provider_connection(payload)


@app.get("/api/patches")
def api_list_patches(status: str = "pending", user_id: str = Depends(require_patch_read)):
    return {"patches": list_patch_proposals(status=status or None)}


@app.post("/api/patches/propose")
async def api_propose_patch(request: Request, user_id: str = Depends(require_patch_write)):
    payload = await request.json()
    try:
        proposal = propose_and_save_patch(
            payload.get("file_path", ""),
            payload.get("proposed_content", ""),
            payload.get("rationale", ""),
        )
        return public_patch_payload(proposal)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/patches/{patch_id}/apply")
def api_apply_patch(
    patch_id: str,
    override_chamber: bool = False,
    user_id: str = Depends(require_patch_write),
):
    try:
        return apply_patch_by_id(patch_id, override_chamber=override_chamber, actor=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/patches/{patch_id}/reject")
def api_reject_patch(patch_id: str, user_id: str = Depends(require_patch_write)):
    try:
        return reject_patch_proposal(patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- Projects ---
@app.get("/api/projects")
def api_get_projects(user_id: str = Depends(require_session_read)):
    return get_all_projects()


@app.post("/api/projects")
async def api_create_project(request: Request, user_id: str = Depends(require_session_write)):
    body = await request.json()
    name = str(body.get("name") or "New Project").strip()
    description = str(body.get("description") or "")
    color = str(body.get("color") or "#6366f1")
    return create_project(name, description, color)


@app.patch("/api/projects/{project_id}")
async def api_update_project(project_id: str, request: Request, user_id: str = Depends(require_session_write)):
    body = await request.json()
    ok = update_project(
        project_id,
        name=body.get("name"),
        description=body.get("description"),
        color=body.get("color"),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "updated"}


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: str, user_id: str = Depends(require_session_write)):
    delete_project(project_id)
    return {"status": "deleted"}


# --- REST APIS FOR SESSION HISTORY HUD ---
@app.post("/api/sessions")
async def api_create_session(request: Request, user_id: str = Depends(require_session_write)):
    try:
        body = await request.json()
        project_id = body.get("project_id") or None
    except Exception:
        project_id = None
    return create_session(project_id=project_id)


@app.get("/api/sessions")
def api_get_sessions(user_id: str = Depends(require_session_read)):
    return get_all_sessions()


@app.patch("/api/sessions/{session_id}/project")
async def api_assign_session_project(session_id: str, request: Request, user_id: str = Depends(require_session_write)):
    body = await request.json()
    project_id = body.get("project_id")  # None to unassign
    assign_session_project(session_id, project_id)
    return {"status": "updated"}


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str, user_id: str = Depends(require_session_write)):
    delete_session(session_id)
    return {"status": "deleted"}


@app.get("/api/sessions/{session_id}")
def api_get_session_data(session_id: str, user_id: str = Depends(require_session_read)):
    state = get_session_state(session_id)
    raw_msgs = state.get("messages", [])
    tokens = state.get("cumulative_tokens", {"total_tokens": 0})
    return {
        "messages": raw_msgs,
        "cumulative_tokens": tokens,
        "runs": get_recent_runs(session_id),
        "active_run": active_session_run(session_id),
        "run_plan": state.get("run_plan"),
        "current_plan_step": state.get("current_plan_step"),
        "module_context": state.get("module_context"),
        "logic_trace": state.get("logic_trace", []),
        "logic_cycle_count": state.get("logic_cycle_count", 0),
        "stuck_reason": state.get("stuck_reason", "")
    }


@app.get("/api/runs/{run_id}/replay")
def api_replay_run(run_id: str, user_id: str = Depends(require_run_read)):
    replay = replay_run(run_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Run not found")
    return replay


@app.get("/api/sessions/{session_id}/active-run")
def api_active_session_run(session_id: str, user_id: str = Depends(require_session_read)):
    return active_session_run(session_id) or {"run": None, "events": [], "last_event": None}


@app.get("/api/memory/search")
def api_memory_search(
    query: str = "",
    memory_type: str = None,
    scope: str = "matters",
    task_type: str = None,
    session_id: str = None,
    limit: int = 10,
    user_id: str = Depends(require_memory_read)
):
    return public_search(
        query,
        session_id=session_id,
        memory_type=memory_type,
        scope=scope,
        task_type=task_type,
        limit=limit,
    )


@app.put("/api/sessions/{session_id}")
async def api_update_session_title(session_id: str, request: Request, user_id: str = Depends(require_session_write)):
    payload = await request.json()
    new_title = payload.get("title", "").strip()[:50]
    if new_title:
        state = get_session_state(session_id)
        update_session(session_id, state, new_title)
    return {"status": "updated", "title": new_title}


# --- ADMIN MANAGEMENT ENDPOINTS (Phase 4) ---
@app.get("/admin/users")
def api_list_users(user_id: str = Depends(require_admin_access)):
    """List all users in the system (Admin only)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, email, role, is_active, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        
        users = []
        for row in rows:
            user_id, username, email, role, is_active, created_at, last_login = row
            users.append({
                "id": user_id,
                "username": username,
                "email": email,
                "role": role,
                "is_active": bool(is_active),
                "created_at": created_at,
                "last_login": last_login
            })
        
        return {"users": users}


@app.post("/admin/users")
def api_create_user(user_id: str = Depends(require_admin_access)):
    """Create a new user (Admin only)"""
    # In a real implementation, this would accept username, email, role, etc.
    # For now, we'll return a placeholder implementation
    return {
        "message": "User creation endpoint - implementation required",
        "note": "This endpoint requires integration with user registration system"
    }


@app.get("/admin/users/{user_id}")
def api_get_user(user_id: str, current_user_id: str = Depends(require_admin_access)):
    """Get a specific user's details (Admin only)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, email, role, is_active, created_at, last_login
            FROM users
            WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id, username, email, role, is_active, created_at, last_login = row
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "role": role,
            "is_active": bool(is_active),
            "created_at": created_at,
            "last_login": last_login
        }


@app.put("/admin/users/{user_id}")
def api_update_user(user_id: str, current_user_id: str = Depends(require_admin_access)):
    """Update a user's details (Admin only)"""
    # In a real implementation, this would accept updates to username, email, role, etc.
    return {
        "message": f"User update endpoint for user {user_id} - implementation required"
    }


@app.delete("/admin/users/{user_id}")
def api_delete_user(user_id: str, current_user_id: str = Depends(require_admin_access)):
    """Delete a user (Admin only)"""
    # Prevent self-deletion
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"message": f"User {user_id} has been deactivated"}


@app.get("/admin/apikeys")
def api_list_all_api_keys(user_id: str = Depends(require_admin_access)):
    """List all API keys in the system (Admin only)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ak.id, ak.user_id, ak.name, ak.expires_at, ak.last_used_at, 
                   ak.created_at, ak.revoked, u.username
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            ORDER BY ak.created_at DESC
        """)
        rows = cursor.fetchall()
        
        api_keys = []
        for row in rows:
            key_id, user_id, name, expires_at, last_used_at, created_at, revoked, username = row
            api_keys.append({
                "id": key_id,
                "user_id": user_id,
                "username": username,
                "name": name,
                "expires_at": expires_at,
                "last_used_at": last_used_at,
                "created_at": created_at,
                "revoked": bool(revoked)
            })
        
        return {"api_keys": api_keys}


@app.post("/admin/apikeys")
def api_create_api_key_for_user(user_id: str = Depends(require_admin_access)):
    """Create an API key for a user (Admin only)"""
    # In a real implementation, this would accept user_id, name, expires_in_days, etc.
    return {
        "message": "API key creation endpoint - implementation required",
        "note": "This endpoint requires parameters for user_id, key name, and expiration"
    }


@app.delete("/admin/apikeys/{key_id}")
def api_revoke_api_key(key_id: str, user_id: str = Depends(require_admin_access)):
    """Revoke an API key (Admin only)"""
    api_key_manager = get_api_key_manager()
    # Note: This would need the actual user_id associated with the key for proper revocation
    # For simplicity, we're allowing admin to revoke any key without user_id verification
    # In production, you'd want to verify the key belongs to a user before allowing revocation
    success = api_key_manager.revoke_api_key(key_id, "admin_override")  # Simplified
    if success:
        return {"message": f"API key {key_id} has been revoked"}
    else:
        raise HTTPException(status_code=404, detail="API key not found")


@app.get("/admin/audit-log")
def api_get_audit_log(
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(require_admin_access)
):
    """Get audit trail entries (Admin only)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, action, resource, outcome, ip_address, user_agent, timestamp
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        
        audit_entries = []
        for row in rows:
            entry_id, user_id, action, resource, outcome, ip_address, user_agent, timestamp = row
            audit_entries.append({
                "id": entry_id,
                "user_id": user_id,
                "action": action,
                "resource": resource,
                "outcome": outcome,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": timestamp
            })
        
        return {
            "audit_log": audit_entries,
            "limit": limit,
            "offset": offset,
            "count": len(audit_entries)
        }


@app.get("/admin/analytics")
def api_get_usage_analytics(user_id: str = Depends(require_admin_access)):
    """Get basic usage analytics (Admin only)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get user count
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Get API key count
        cursor.execute("SELECT COUNT(*) FROM api_keys WHERE revoked = 0")
        active_api_keys = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM api_keys")
        total_api_keys = cursor.fetchone()[0]
        
        # Get session count
        cursor.execute("SELECT COUNT(*) FROM chat_sessions")
        total_sessions = cursor.fetchone()[0]
        
        # Get run count
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        total_runs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM agent_runs WHERE status = 'completed'")
        completed_runs = cursor.fetchone()[0]
        
        # Get recent activity (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) FROM audit_log 
            WHERE timestamp >= datetime('now', '-1 day')
        """)
        recent_actions = cursor.fetchone()[0]
        
        return {
            "users": {
                "active": active_users,
                "total": total_users
            },
            "api_keys": {
                "active": active_api_keys,
                "total": total_api_keys
            },
            "sessions": total_sessions,
            "runs": {
                "total": total_runs,
                "completed": completed_runs,
                "success_rate": round(completed_runs / max(total_runs, 1) * 100, 2) if total_runs > 0 else 0
            },
            "recent_activity_24h": recent_actions
        }


# -----------------------------------------
async def run_swarm_background(websocket, session_id, run_id, user_text, session_state, graph, memory_store, ws_send_lock: asyncio.Lock):
    from langchain_core.messages import messages_to_dict
    from src.api.database import update_session
    from src.core.config import system_logger

    title_update = None
    auth_token = set_active_session(session_id)
    log_token = set_log_session(session_id)
    run_context_tokens = set_run_context(run_id, session_id)
    try:
        max_turns = alos_config.max_agent_turns
        config = {"recursion_limit": max_turns}
        async for output in graph.astream(session_state, config=config, stream_mode="updates"):
            for node_name, node_state in output.items():
                guard = record_engine_step(session_state, node_name, node_state, max_cycles=max_turns)
                before_plan = session_state.get("run_plan")
                active_worker = node_state.get("active_worker", session_state.get("active_worker"))
                session_state["active_worker"] = active_worker
                event = node_started(run_id, session_id, node_name, active_worker=active_worker)
                await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})
                # Diagnostic telemetry — must never kill the run. A single
                # unknown event_type shouldn't torch an otherwise-healthy
                # plan step; log and drop instead.
                try:
                    guard_event = record_event(
                        run_id,
                        session_id,
                        "logic_guard_step",
                        guard,
                        node=node_name,
                        active_worker=active_worker,
                    )
                    await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": guard_event})
                except Exception as guard_exc:  # noqa: BLE001
                    system_logger.warning(
                        f"logic_guard_step emit failed (node={node_name}): {guard_exc}"
                    )
                update_run(run_id, active_worker=active_worker)
                if node_state.get("agent_selection"):
                    selection_event = agent_selected(run_id, session_id, node_state["agent_selection"], node=node_name)
                    await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": selection_event})

                await safe_send_json(websocket, ws_send_lock, {
                    "type": "swarm_update",
                    "node": node_name,
                    "active_worker": active_worker
                })

                tokens = node_state.get("cumulative_tokens")
                if tokens:
                    await safe_send_json(websocket, ws_send_lock, {
                        "type": "token_update",
                        "total": tokens.total_tokens
                    })
                    update_run(run_id, token_total=tokens.total_tokens)

                if node_state.get("run_plan"):
                    await safe_send_json(websocket, ws_send_lock, {
                        "type": "plan_update",
                        "plan": node_state["run_plan"]
                    })

                msgs = node_state.get("messages", [])
                if msgs:
                    latest_msg = msgs[-1] if isinstance(msgs, list) else msgs

                    if getattr(latest_msg, 'type', '') != 'tool':
                        if hasattr(latest_msg, 'content') and latest_msg.content:
                            await safe_send_json(websocket, ws_send_lock, {
                                "type": "chat_output",
                                "sender": node_name,
                                "content": str(latest_msg.content)
                            })

                # --- [PHASE 1 MEMORY CHECKPOINT INTEGRATION] ---
                # Save semantic memory and graph checkpoint during execution
                try:
                    memory_store.log_graph_checkpoint(node_state, node_name)
                    system_logger.debug(f"Memory checkpoint saved for node: {node_name}")
                except Exception as e:
                    system_logger.error(f"Failed to save memory checkpoint: {str(e)}")
                # ---------------------------------------------

                for k, v in node_state.items():
                    if k == "messages":
                        # Filter out RemoveMessage stubs to prevent serialization crashes in UI and DB
                        deltas = [m for m in (v if isinstance(v, list) else [v]) if not isinstance(m, RemoveMessage)]
                        session_state["messages"].extend(deltas)
                    else:
                        session_state[k] = v

                session_state["last_node"] = node_name
                persist_resume_state(run_id, session_id, session_state, active_worker=active_worker, last_node=node_name)
                for completed_step in newly_completed_steps(before_plan, session_state.get("run_plan")):
                    event = step_completed(
                        run_id,
                        session_id,
                        completed_step.get("id", ""),
                        completed_step.get("title", ""),
                        active_worker=active_worker,
                    )
                    await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})

        if has_incomplete_required_verification(session_state.get("run_plan")):
            failed_plan = fail_active_step(
                session_state.get("run_plan"),
                "Run attempted to finish before completing the required verification step."
            )
            if failed_plan:
                session_state["run_plan"] = public_plan(failed_plan)
                await safe_send_json(websocket, ws_send_lock, {"type": "plan_update", "plan": session_state["run_plan"]})
            message = f"Run halted at plan step '{failed_step_label(session_state.get('run_plan'))}': verification is incomplete."
            event = mark_run_failed(run_id, session_id, session_state, message)
            await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})
            await safe_send_json(websocket, ws_send_lock, {
                "type": "chat_output",
                "sender": "System_Error",
                "content": message
            })
            await safe_send_json(websocket, ws_send_lock, {
                "type": "execution_complete"
            })
            return

        event = mark_run_completed(run_id, session_id, session_state)
        await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})
        await safe_send_json(websocket, ws_send_lock, {
            "type": "execution_complete"
        })
    except asyncio.CancelledError:
        system_logger.warning(f"Swarm task for session {session_id} was manually terminated.")
        blocked_plan = fail_active_step(session_state.get("run_plan"), "Execution was halted by the user.")
        if blocked_plan:
            session_state["run_plan"] = public_plan(blocked_plan)
        event = mark_run_cancelled(run_id, session_id, session_state, "Execution halted by user.")
        await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})
        if blocked_plan:
            await safe_send_json(websocket, ws_send_lock, {"type": "plan_update", "plan": session_state["run_plan"]})
        await safe_send_json(websocket, ws_send_lock, {
            "type": "chat_output",
            "sender": "System",
            "content": "_Execution halted by user._"
        })
        await safe_send_json(websocket, ws_send_lock, {
            "type": "execution_complete"
        })
    except LogicEngineStuck as e:
        system_logger.warning(f"Logic engine stopped stuck run for session {session_id}: {e.reason}")
        session_state["stuck_reason"] = e.reason
        failed_plan = fail_active_step(session_state.get("run_plan"), e.reason)
        if failed_plan:
            session_state["run_plan"] = public_plan(failed_plan)
        event = mark_run_stuck(run_id, session_id, session_state, e.reason, node=session_state.get("last_node"))
        await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})
        if failed_plan:
            await safe_send_json(websocket, ws_send_lock, {"type": "plan_update", "plan": session_state["run_plan"]})
        await safe_send_json(websocket, ws_send_lock, {
            "type": "chat_output",
            "sender": "System",
            "content": f"ALOS stopped this run because it looked stuck: {e.reason}"
        })
        await safe_send_json(websocket, ws_send_lock, {
            "type": "execution_complete"
        })
    except Exception as e:
        system_logger.error(f"Background thread crashed dynamically: {str(e)}")
        failed_plan = fail_active_step(session_state.get("run_plan"), str(e))
        if failed_plan:
            session_state["run_plan"] = public_plan(failed_plan)
        step_label = failed_step_label(session_state.get("run_plan"))
        event = mark_run_failed(run_id, session_id, session_state, f"{step_label}: {str(e)}", node=step_label)
        await safe_send_json(websocket, ws_send_lock, {"type": "run_event", "event": event})
        if failed_plan:
            await safe_send_json(websocket, ws_send_lock, {"type": "plan_update", "plan": session_state["run_plan"]})
        await safe_send_json(websocket, ws_send_lock, {
            "type": "chat_output",
            "sender": "System_Error",
            "content": f"Run failed at plan step '{step_label}': `{str(e)}`"
        })
    finally:
        try:
            if session_id in active_tasks:
                del active_tasks[session_id]

            # Guarantee unkillable state dump to SQL natively
            native_array = session_state.get("messages", [])
            tokens = session_state.get("cumulative_tokens", TokenUsage())

            human_count = sum(1 for m in native_array if getattr(m, 'type', '') == 'human')
            if human_count == 1:
                title_update = user_text[:30] + "..." if len(user_text) > 30 else user_text
                try:
                    await safe_send_json(websocket, ws_send_lock, {"type": "title_update", "title": title_update})
                except Exception:
                    pass

            update_session(
                session_id,
                {
                    "messages": messages_to_dict(native_array),
                    "cumulative_tokens": serialize_token_usage(tokens),
                    "run_plan": session_state.get("run_plan"),
                    "current_plan_step": session_state.get("current_plan_step"),
                    "module_context": session_state.get("module_context"),
                    "logic_trace": session_state.get("logic_trace", []),
                    "logic_cycle_count": session_state.get("logic_cycle_count", 0),
                    "stuck_reason": session_state.get("stuck_reason", "")
                },
                title_update
            )

            # Checkpoints stay first-class; consolidation adds higher-signal memory next to them.
            try:
                consolidation_result = memory_store.consolidate_session()
                system_logger.info(f"Session consolidation completed: {consolidation_result.get('total_memories', 0)} memories processed")
            except Exception as e:
                system_logger.error(f"Failed to consolidate session memories: {str(e)}")
        finally:
            reset_run_context(run_context_tokens)


@app.websocket("/ws/scout")
async def scout_websocket(websocket: WebSocket, api_key: str = ""):
    if not RBAC_DISABLED:
        mgr = get_api_key_manager()
        user_info = mgr.validate_api_key(api_key) if api_key else None
        if not user_info:
            await websocket.close(code=4401, reason="Unauthorized")
            return
    await websocket.accept()
    queue, unsubscribe = subscribe_scout_events()
    try:
        await websocket.send_json({
            "type": "scout_snapshot",
            "events": list_scout_events(limit=300),
        })
        while True:
            event = await queue.get()
            await websocket.send_json({"type": "scout_event", "event": event})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        unsubscribe()


@app.websocket("/ws/{session_id}")
async def websocket_hub(websocket: WebSocket, session_id: str, api_key: str = ""):
    ws_user_id: str | None = None
    active_user_token = None
    if not RBAC_DISABLED:
        mgr = get_api_key_manager()
        user_info = mgr.validate_api_key(api_key) if api_key else None
        if not user_info:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        ws_user_id = user_info["user_id"]
        active_user_token = set_active_user(ws_user_id)
    await websocket.accept()
    bind_websocket(session_id, websocket)
    log_token = set_log_session(session_id)
    graph = build_orchestrator()

    # --- [SERIALIZATION LOCK] ---
    ws_send_lock = asyncio.Lock()

    # Declare outside try so finally block can access them
    session_state = None
    memory_store = None

    # --- [SECURE LOG TRACE ATTACHMENT] ---
    loop = asyncio.get_event_loop()
    log_handler = WebSocketLogHandler(websocket, loop, ws_send_lock, session_id)
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    system_logger.addHandler(log_handler)

    try:
        # Pre-load context directly from exact physical DB array
        raw_state = get_session_state(session_id)
        raw_msgs = raw_state.get("messages", [])
        raw_tokens = raw_state.get("cumulative_tokens", {})
        raw_plan = raw_state.get("run_plan")

        session_state = {
            "messages": messages_from_dict(raw_msgs) if raw_msgs else [],
            "current_objective": "",
            "current_step_id": "engine_start",
            "active_worker": "",
            "error_history": [],
            "tool_results": [],
            "cumulative_tokens": TokenUsage(**raw_tokens) if raw_tokens else TokenUsage(),
            "requires_human_approval": False,
            "run_plan": raw_plan,
            "current_plan_step": raw_state.get("current_plan_step"),
            "module_context": normalize_module_context(raw_state.get("module_context")),
            "logic_trace": [],
            "logic_cycle_count": 0,
            "stuck_reason": ""
        }

        # Initial token update for UI
        async with ws_send_lock:
            await websocket.send_json({
                "type": "token_update",
                "total": session_state["cumulative_tokens"].total_tokens
            })

        # --- [PHASE 1 MEMORY STORE INITIALIZATION] ---
        memory_store = MemoryCheckpointStore(session_id)
        system_logger.info(f"MemoryCheckpointStore initialized for session: [{session_id}]")

        active_replay = active_session_run(session_id)
        if active_replay:
            async with ws_send_lock:
                await websocket.send_json({"type": "run_resume", "replay": active_replay})

        async def start_planned_run(user_text: str):
            session_state["messages"].append(HumanMessage(content=user_text))

            human_count = sum(1 for m in session_state["messages"] if getattr(m, 'type', '') == 'human')
            if human_count == 1:
                title_update = user_text[:30] + "..." if len(user_text) > 30 else user_text
                async with ws_send_lock:
                    await websocket.send_json({"type": "title_update", "title": title_update})

            async with ws_send_lock:
                await websocket.send_json({"type": "status", "message": "Executing Swarm matrix natively..."})

            run_id = start_run(session_id, user_text, session_state)
            async with ws_send_lock:
                await websocket.send_json({"type": "run_started", "run_id": run_id})
                replay = replay_run(run_id)
                if replay.get("last_event"):
                    await websocket.send_json({"type": "run_event", "event": replay["last_event"]})

            task = asyncio.create_task(
                run_swarm_background(websocket, session_id, run_id, user_text, session_state, graph, memory_store, ws_send_lock)
            )
            task.add_done_callback(_make_task_cleanup(session_id))
            active_tasks[session_id] = task

        async def gate_plan_and_start(user_text: str, pending_plan):
            approval_token = set_active_session(session_id)
            try:
                approved = await wait_for_plan_approval(public_plan(pending_plan), risk=pending_plan.risk)
                if not approved:
                    rejected_plan = fail_active_step(pending_plan, "User rejected the high-risk plan before execution.")
                    session_state["run_plan"] = public_plan(rejected_plan)
                    session_state["current_plan_step"] = rejected_plan.current_step_id
                    async with ws_send_lock:
                        await websocket.send_json({"type": "plan_update", "plan": session_state["run_plan"]})
                        await websocket.send_json({
                            "type": "plan_rejected",
                            "message": "Plan rejected. No run was created and no agent acted."
                        })
                        await websocket.send_json({"type": "execution_complete"})
                    return

                approved_plan = approve_plan(pending_plan)
                session_state["run_plan"] = public_plan(approved_plan)
                session_state["current_plan_step"] = approved_plan.current_step_id
                async with ws_send_lock:
                    await websocket.send_json({"type": "plan_update", "plan": session_state["run_plan"]})
                await start_planned_run(user_text)
            except asyncio.CancelledError:
                blocked_plan = fail_active_step(pending_plan, "Plan approval was cancelled before execution.")
                session_state["run_plan"] = public_plan(blocked_plan)
                session_state["current_plan_step"] = blocked_plan.current_step_id
                try:
                    async with ws_send_lock:
                        await websocket.send_json({"type": "plan_update", "plan": session_state["run_plan"]})
                        await websocket.send_json({"type": "execution_complete"})
                except Exception:
                    pass
            finally:
                if active_tasks.get(session_id) is asyncio.current_task():
                    del active_tasks[session_id]
                reset_active_session(approval_token)

        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "chat_input":
                existing = active_tasks.get(session_id)
                if existing and not existing.done():
                    async with ws_send_lock:
                        await websocket.send_json({
                            "type": "chat_output",
                            "sender": "System",
                            "content": "A run is already active. Stop it before starting a new objective."
                        })
                    continue

                if not alos_config.is_configured():
                    async with ws_send_lock:
                        await websocket.send_json({
                            "type": "setup_required",
                            "message": "Provider setup is required before ALOS can run the swarm."
                        })
                    continue

                user_text = payload.get("text", "")
                module_context = normalize_module_context(payload.get("module_context"))
                if module_context:
                    session_state["module_context"] = module_context
                plan = create_run_plan(user_text)
                session_state["run_plan"] = public_plan(plan)
                session_state["current_plan_step"] = plan.current_step_id
                async with ws_send_lock:
                    await websocket.send_json({"type": "plan_update", "plan": session_state["run_plan"]})

                if plan.needs_approval:
                    task = asyncio.create_task(gate_plan_and_start(user_text, plan))
                    task.add_done_callback(_make_task_cleanup(session_id))
                    active_tasks[session_id] = task
                    continue

                await start_planned_run(user_text)

            elif payload.get("type") == "stop_execution":
                task = active_tasks.get(session_id)
                if task and not task.done():
                    task.cancel()
                    async with ws_send_lock:
                        await websocket.send_json({"type": "status", "message": "Stop requested. Cancelling active run..."})
                else:
                    async with ws_send_lock:
                        await websocket.send_json({"type": "status", "message": "No active run to stop."})
                        await websocket.send_json({"type": "execution_complete"})

            elif payload.get("type") == "auth_response":
                resolve_auth(payload.get("approval_id", ""), payload.get("approved", False))

            elif payload.get("type") == "plan_response":
                resolve_plan_approval(payload.get("approval_id", ""), payload.get("approved", False))

    except Exception as e:
        bind_websocket(session_id, None)
        close_detail = str(e)
        if "NO_STATUS_RCVD" in close_detail or "1005" in close_detail or "1006" in close_detail:
            system_logger.info(f"Websocket closed by client for session {session_id}: {close_detail}")
        else:
            system_logger.error(f"Websocket closure or exception dynamically intercepted: {close_detail}")
    finally:
        system_logger.removeHandler(log_handler)
        bind_websocket(session_id, None)
        system_logger.warning(f"Websocket array terminated seamlessly for session {session_id}. Checkpointing native memory.")
        if session_state and session_state.get("messages"):
            native_array = session_state["messages"]
            tokens = session_state.get("cumulative_tokens", TokenUsage())
            update_session(session_id, {
                "messages": messages_to_dict(native_array),
                "cumulative_tokens": serialize_token_usage(tokens),
                "run_plan": session_state.get("run_plan"),
                "current_plan_step": session_state.get("current_plan_step"),
                "module_context": session_state.get("module_context"),
                "logic_trace": session_state.get("logic_trace", []),
                "logic_cycle_count": session_state.get("logic_cycle_count", 0),
                "stuck_reason": session_state.get("stuck_reason", "")
            })
        reset_log_session(log_token)
        if active_user_token is not None:
            reset_active_user(active_user_token)
