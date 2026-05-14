#!/usr/bin/env python3
"""Live contract verification for planning task 0149.

This starts an isolated ALOS backend on a random localhost port with a
temporary data directory and a fake swarm graph. It verifies the actual REST
and WebSocket contracts used by Chat without touching the user's real app data
or any service already using port 8000.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import websockets


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


FAKE_APP = r'''
import asyncio
from copy import deepcopy

from langchain_core.messages import AIMessage

from src.core.state import TokenUsage
import src.api.server as server


class NoopMemoryStore:
    def __init__(self, session_identifier, user_id=None):
        self.session_id = session_identifier

    def log_graph_checkpoint(self, state_snapshot, triggering_node):
        return None

    def consolidate_session(self):
        return {"total_memories": 0}


def completed_plan(raw_plan):
    if not isinstance(raw_plan, dict):
        return raw_plan
    plan = deepcopy(raw_plan)
    plan["status"] = "complete"
    plan["approved"] = True
    plan["needs_approval"] = False
    plan["current_step_id"] = None
    for step in plan.get("steps", []):
        step["status"] = "complete"
        step["failure_reason"] = None
        for criterion in step.get("exit_criteria", []):
            criterion["satisfied"] = True
    return plan


class FakeGraph:
    async def astream(self, session_state, config=None, stream_mode=None):
        messages = session_state.get("messages") or []
        latest = messages[-1].content if messages else ""
        if "slow" in latest.lower():
            yield {
                "Fake_Long_Running_Agent": {
                    "active_worker": "Fake_Long_Running_Agent",
                    "messages": [AIMessage(content="Long run started.")],
                    "cumulative_tokens": TokenUsage(prompt_tokens=2, completion_tokens=2, total_tokens=4),
                    "run_plan": session_state.get("run_plan"),
                    "current_plan_step": session_state.get("current_plan_step"),
                }
            }
            await asyncio.sleep(30)
            return

        yield {
            "Fake_Chat_Agent": {
                "active_worker": "Fake_Chat_Agent",
                "messages": [AIMessage(content="ALOS live verification response.")],
                "cumulative_tokens": TokenUsage(prompt_tokens=3, completion_tokens=5, total_tokens=8),
                "run_plan": completed_plan(session_state.get("run_plan")),
                "current_plan_step": None,
            }
        }


server.MemoryCheckpointStore = NoopMemoryStore
server.build_orchestrator = lambda: FakeGraph()
app = server.app
'''


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> dict[str, Any] | list[Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        text = res.read().decode("utf-8")
    return json.loads(text) if text else {}


def wait_for_health(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 20
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"backend exited early with code {process.returncode}")
        try:
            health = request_json(base_url, "GET", "/api/health")
            if health.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - diagnostic loop
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"backend did not become healthy: {last_error}")


async def recv_until(ws, predicate, label: str, timeout: float = 10) -> dict[str, Any]:
    deadline = time.time() + timeout
    frames: list[dict[str, Any]] = []
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        frame = json.loads(raw)
        frames.append(frame)
        if predicate(frame):
            return frame
    raise AssertionError(f"Timed out waiting for {label}. Frames: {frames}")


async def verify_websocket_contract(base_url: str, port: int, api_key: str) -> dict[str, Any]:
    ws_base = f"ws://127.0.0.1:{port}"
    evidence: dict[str, Any] = {}

    session = request_json(base_url, "POST", "/api/sessions", {"name": "0149 setup gate"}, api_key)
    session_id = str(session["id"])

    try:
        async with websockets.connect(f"{ws_base}/ws/{session_id}?api_key=alos_invalid") as ws:
            await ws.recv()
        raise AssertionError("invalid websocket API key was accepted")
    except Exception:
        evidence["invalid_ws_auth_rejected"] = True

    async with websockets.connect(f"{ws_base}/ws/{session_id}?api_key={api_key}") as ws:
        await recv_until(ws, lambda f: f.get("type") == "token_update", "initial token update")
        await ws.send(json.dumps({"type": "chat_input", "text": "hello"}))
        setup = await recv_until(ws, lambda f: f.get("type") == "setup_required", "setup_required")
        evidence["setup_required"] = setup.get("message")

    request_json(
        base_url,
        "PUT",
        "/api/settings",
        {"llm_provider": "ollama", "model_name": "alos-0149-live-test", "base_url": "http://127.0.0.1:11434/v1"},
        api_key,
    )
    health = request_json(base_url, "GET", "/api/health")
    assert health.get("configured") is True, health
    evidence["provider_recovery_configured"] = True

    simple = request_json(base_url, "POST", "/api/sessions", {"name": "0149 simple chat"}, api_key)
    simple_id = str(simple["id"])
    async with websockets.connect(f"{ws_base}/ws/{simple_id}?api_key={api_key}") as ws:
        await recv_until(ws, lambda f: f.get("type") == "token_update", "initial token update")
        await ws.send(json.dumps({"type": "chat_input", "text": "hello"}))
        await recv_until(ws, lambda f: f.get("type") == "plan_update" and f.get("plan", {}).get("risk") == "low", "low-risk plan")
        await recv_until(ws, lambda f: f.get("type") == "run_started", "run_started")
        output = await recv_until(ws, lambda f: f.get("type") == "chat_output" and "verification response" in f.get("content", ""), "chat output")
        await recv_until(ws, lambda f: f.get("type") == "execution_complete", "execution_complete")
        evidence["simple_chat_output"] = output["content"]

    state = request_json(base_url, "GET", f"/api/sessions/{simple_id}", api_key=api_key)
    persisted = " ".join(str((m.get("data") or {}).get("content", "")) for m in state.get("messages", []))
    assert "hello" in persisted and "verification response" in persisted, state
    evidence["reload_history_messages"] = len(state.get("messages", []))

    high = request_json(base_url, "POST", "/api/sessions", {"name": "0149 high risk"}, api_key)
    high_id = str(high["id"])
    async with websockets.connect(f"{ws_base}/ws/{high_id}?api_key={api_key}") as ws:
        await recv_until(ws, lambda f: f.get("type") == "token_update", "initial token update")
        await ws.send(json.dumps({"type": "chat_input", "text": "modify a backend file"}))
        plan = await recv_until(
            ws,
            lambda f: f.get("type") == "plan_update"
            and f.get("plan", {}).get("risk") == "high"
            and f.get("plan", {}).get("needs_approval") is True,
            "high-risk plan",
        )
        approval = await recv_until(ws, lambda f: f.get("type") == "plan_approval_request", "plan approval request")
        await ws.send(json.dumps({"type": "plan_response", "approval_id": approval["approval_id"], "approved": True}))
        await recv_until(ws, lambda f: f.get("type") == "run_started", "approved run_started")
        await recv_until(ws, lambda f: f.get("type") == "execution_complete", "approved execution_complete")
        evidence["high_risk_plan_steps"] = len(plan.get("plan", {}).get("steps", []))
        evidence["plan_approval_request"] = True

    slow = request_json(base_url, "POST", "/api/sessions", {"name": "0149 stop"}, api_key)
    slow_id = str(slow["id"])
    async with websockets.connect(f"{ws_base}/ws/{slow_id}?api_key={api_key}") as ws:
        await recv_until(ws, lambda f: f.get("type") == "token_update", "initial token update")
        await ws.send(json.dumps({"type": "chat_input", "text": "test slow response"}))
        await recv_until(ws, lambda f: f.get("type") == "run_started", "slow run_started")
        await recv_until(ws, lambda f: f.get("type") == "chat_output" and "Long run started" in f.get("content", ""), "slow run output")
        await ws.send(json.dumps({"type": "stop_execution"}))
        await recv_until(ws, lambda f: f.get("type") == "run_event" and f.get("event", {}).get("event_type") == "run_cancelled", "run_cancelled")
        await recv_until(ws, lambda f: f.get("type") == "execution_complete", "cancel execution_complete")
        evidence["stop_returns_execution_complete"] = True

    return evidence


async def main() -> int:
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="alos-0149-data-") as data_dir, tempfile.TemporaryDirectory(prefix="alos-0149-app-") as app_dir:
        module_path = Path(app_dir) / "alos0149_live_app.py"
        module_path.write_text(FAKE_APP, encoding="utf-8")
        env = os.environ.copy()
        env["ALOS_DATA_DIR"] = data_dir
        env["ALOS_DB_PATH"] = str(Path(data_dir) / "alos_memory.db")
        env["PYTHONPATH"] = os.pathsep.join([app_dir, str(ROOT), str(BACKEND), env.get("PYTHONPATH", "")])
        env["PYTHONUNBUFFERED"] = "1"

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "alos0149_live_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ]
        process = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            wait_for_health(base_url, process)
            bootstrap_status = request_json(base_url, "GET", "/auth/bootstrap/status")
            assert bootstrap_status.get("can_bootstrap") is True, bootstrap_status
            bootstrap = request_json(base_url, "POST", "/auth/bootstrap/original-admin", {"username": "0149-admin"})
            api_key = str(bootstrap["api_key"])
            validation = request_json(base_url, "POST", "/auth/validate", {"api_key": api_key})
            assert validation.get("valid") is True, validation
            evidence = await verify_websocket_contract(base_url, port, api_key)
            evidence["port"] = port
            evidence["data_dir_isolated"] = data_dir
            print(json.dumps({"ok": True, "evidence": evidence}, indent=2, sort_keys=True))
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            stderr = process.stderr.read() if process.stderr else ""
            if process.returncode not in (0, -15, None) and stderr:
                print(textwrap.indent(stderr, "backend stderr: "), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
