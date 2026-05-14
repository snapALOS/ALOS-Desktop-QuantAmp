from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


DEFAULT_REXHUB_API_BASE = "http://127.0.0.1:3000"


class ALOSHubAdapter:
    def __init__(self) -> None:
        configured_base = os.environ.get("REXHUB_API_BASE") or os.environ.get("REXHUB_URL") or ""
        self.base_url = (configured_base or DEFAULT_REXHUB_API_BASE).rstrip("/")
        self.autodiscovered = not bool(configured_base)
        self.token = os.environ.get("REXHUB_API_TOKEN") or os.environ.get("REXHUB_REXFLOW_TOKEN") or ""

    @property
    def configured(self) -> bool:
        return self._can_deliver()

    def health(self) -> dict[str, Any]:
        if not self.base_url:
            return {"configured": False, "status": "local_only"}
        try:
            self._get("/health")
            mode = "autodiscovered" if self.autodiscovered else "configured"
            return {"configured": True, "status": "reachable", "mode": mode, "baseUrl": self.base_url}
        except Exception:
            if self.autodiscovered:
                return {"configured": False, "status": "local_only", "baseUrl": self.base_url}
            return {"configured": True, "status": "unreachable"}

    def publish_workflow(self, workflow: dict[str, Any], version: dict[str, Any]) -> str:
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/workflows", {"workflow": workflow, "version": version})
            return "delivered"
        except Exception:
            return "delivery_failed"

    def emit_event(self, event: dict[str, Any]) -> str:
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/events", event)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def emit_execution_event(self, event: dict[str, Any]) -> str:
        return self.emit_event(event)

    def create_task(self, task: dict[str, Any]) -> str:
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/tasks", task)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def update_task(self, task_id: str, patch: dict[str, Any]) -> str:
        if not self._can_deliver():
            return "local_only"
        try:
            self._post(f"/api/alos_current/tasks/{task_id}", patch)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def assign_department_head(self, task_id: str | None, department_id: str, assignee_id: str) -> str:
        payload = {"taskId": task_id, "departmentId": department_id, "assigneeId": assignee_id}
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/assignments/department-head", payload)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def assign_sub_agent(self, task_id: str | None, agent_id: str) -> str:
        payload = {"taskId": task_id, "agentId": agent_id}
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/assignments/sub-agent", payload)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def request_approval(self, execution_id: str, node_id: str, assignee_id: str | None) -> str:
        payload = {"executionId": execution_id, "nodeId": node_id, "assigneeId": assignee_id}
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/approvals", payload)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def create_escalation(self, execution_id: str, node_id: str, reason: str) -> str:
        payload = {"executionId": execution_id, "nodeId": node_id, "reason": reason}
        if not self._can_deliver():
            return "local_only"
        try:
            self._post("/api/alos_current/escalations", payload)
            return "delivered"
        except Exception:
            return "delivery_failed"

    def _can_deliver(self) -> bool:
        if not self.base_url:
            return False
        if not self.autodiscovered:
            return True
        try:
            self._get("/health", timeout=2)
            return True
        except Exception:
            return False

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if content_type:
            headers["content-type"] = content_type
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, path: str, timeout: int = 8) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            method="GET",
            headers=self._headers(),
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method="POST",
            headers=self._headers("application/json"),
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"ALOSHub returned {exc.code}") from exc
