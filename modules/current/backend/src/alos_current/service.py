from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .compiler import ValidationError, compile_graph, validate_graph
from .ids import new_id, now, stable_hash
from .nodes import NODE_BY_TYPE, default_config, list_node_types
from .rexhub import ALOSHubAdapter
from .storage import AlosCurrentStore


class AlosCurrentService:
    def __init__(self, store: AlosCurrentStore) -> None:
        self.store = store
        self.rexhub = ALOSHubAdapter()
        self.store.init()
        # [RFC-0002] Shared agent execution pool (4 workers by default)
        self.agent_pool = ThreadPoolExecutor(max_workers=4)
        self.workflow_pool = ThreadPoolExecutor(max_workers=4)
        self._active_workflows: dict[str, Any] = {}
        self._active_workflows_lock = Lock()

    def health(self) -> dict[str, Any]:
        return {"ok": True, "product": "AlosCurrent", "node_types": len(list_node_types()), "rexhub": self.rexhub.health()}

    def nodes(self) -> dict[str, Any]:
        return {"nodes": list_node_types()}

    def starter_graph(self) -> dict[str, Any]:
        return {
            "nodes": [
                self.new_node("manual_trigger", 90, 100, "Manual Start"),
                self.new_node("create_task", 360, 100, "Create Review Task"),
                self.new_node("approval_gate", 630, 100, "Department Approval"),
                self.new_node("output", 900, 100, "Complete"),
            ],
            "edges": [
                {"id": new_id("edge"), "sourceNodeId": "node_manual_start", "sourcePort": "next", "targetNodeId": "node_create_review_task", "targetPort": "in"},
                {"id": new_id("edge"), "sourceNodeId": "node_create_review_task", "sourcePort": "next", "targetNodeId": "node_department_approval", "targetPort": "in"},
                {"id": new_id("edge"), "sourceNodeId": "node_department_approval", "sourcePort": "approved", "targetNodeId": "node_complete", "targetPort": "in"},
            ],
            "variables": {},
        }

    def new_node(self, node_type: str, x: int, y: int, name: str | None = None) -> dict[str, Any]:
        spec = NODE_BY_TYPE[node_type]
        base_id = "node_" + (name or spec["label"]).lower().replace(" ", "_").replace("-", "_")
        return {
            "id": base_id,
            "type": node_type,
            "name": name or spec["label"],
            "position": {"x": x, "y": y},
            "config": default_config(node_type),
            "status": "idle",
        }

    def create_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = payload.get("id") or new_id("wf")
        timestamp = now()
        draft = payload.get("draft") or self.starter_graph()
        workflow = {
            "id": workflow_id,
            "name": payload.get("name") or "Untitled Workflow",
            "description": payload.get("description") or "",
            "status": "draft",
            "active_version_id": None,
            "draft": draft,
            "metadata": {
                "createdAt": timestamp,
                "updatedAt": timestamp,
                "createdBy": payload.get("createdBy") or "local",
                "tags": payload.get("tags") or [],
            },
            "settings": payload.get("settings") or {"timeout": 30000, "retries": 3, "concurrencyLimit": 1},
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.store.execute(
            """
            INSERT INTO workflows(id, name, description, status, active_version_id, draft_json, metadata_json, settings_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow["id"],
                workflow["name"],
                workflow["description"],
                workflow["status"],
                workflow["active_version_id"],
                json.dumps(workflow["draft"]),
                json.dumps(workflow["metadata"]),
                json.dumps(workflow["settings"]),
                workflow["created_at"],
                workflow["updated_at"],
            ),
        )
        self.event("workflow.created", workflow_id=workflow_id, message=f"Workflow created: {workflow['name']}", payload={"workflow": workflow})
        self.store.audit(new_id("audit"), "workflow.created", "workflow", workflow_id, {"name": workflow["name"]})
        return {"workflow": self.get_workflow(workflow_id)}

    def list_workflows(self) -> dict[str, Any]:
        rows = self.store.rows("SELECT * FROM workflows WHERE status != 'archived' ORDER BY updated_at DESC")
        return {"workflows": rows}

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        row = self.store.row("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        if not row:
            raise KeyError(f"workflow not found: {workflow_id}")
        row["activeVersionId"] = row.pop("active_version_id")
        row["createdAt"] = row.pop("created_at")
        row["updatedAt"] = row.pop("updated_at")
        return row

    def update_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_workflow(workflow_id)
        draft = payload.get("draft", current["draft"])
        metadata = current["metadata"]
        metadata["updatedAt"] = now()
        if "tags" in payload:
            metadata["tags"] = payload["tags"]
        updated_at = now()
        self.store.execute(
            """
            UPDATE workflows
            SET name = ?, description = ?, draft_json = ?, metadata_json = ?, settings_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.get("name", current["name"]),
                payload.get("description", current["description"]),
                json.dumps(draft),
                json.dumps(metadata),
                json.dumps(payload.get("settings", current["settings"])),
                updated_at,
                workflow_id,
            ),
        )
        self.event("workflow.updated", workflow_id=workflow_id, message="Workflow draft updated", payload={"workflowId": workflow_id})
        self.store.audit(new_id("audit"), "workflow.updated", "workflow", workflow_id, {"name": payload.get("name", current["name"])})
        return {"workflow": self.get_workflow(workflow_id)}

    def archive_workflow(self, workflow_id: str) -> dict[str, Any]:
        self.store.execute("UPDATE workflows SET status = ?, updated_at = ? WHERE id = ?", ("archived", now(), workflow_id))
        self.event("workflow.archived", workflow_id=workflow_id, message="Workflow archived", payload={})
        self.store.audit(new_id("audit"), "workflow.archived", "workflow", workflow_id, {})
        return {"archived": True, "workflowId": workflow_id}

    def duplicate_workflow(self, workflow_id: str) -> dict[str, Any]:
        current = self.get_workflow(workflow_id)
        return self.create_workflow(
            {
                "name": f"{current['name']} Copy",
                "description": current["description"],
                "draft": current["draft"],
                "settings": current["settings"],
                "tags": current["metadata"].get("tags", []),
            }
        )

    def validate_workflow(self, workflow_id: str | None = None, graph: dict[str, Any] | None = None) -> dict[str, Any]:
        if graph is None:
            if not workflow_id:
                raise ValueError("workflow_id or graph is required")
            graph = self.get_workflow(workflow_id)["draft"]
        return {"validation": validate_graph(graph)}

    def publish_workflow(self, workflow_id: str, actor: str = "local") -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        validation = validate_graph(workflow["draft"])
        if not validation["valid"]:
            raise ValidationError("; ".join(validation["errors"]))
        existing = self.store.rows("SELECT version FROM workflow_versions WHERE workflow_id = ? ORDER BY version DESC LIMIT 1", (workflow_id,))
        version = int(existing[0]["version"]) + 1 if existing else 1
        version_id = f"{workflow_id}_v{version}_{stable_hash(workflow['draft'])[:8]}"
        self.store.execute(
            """
            INSERT INTO workflow_versions(id, workflow_id, version, graph_json, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, workflow_id, version, json.dumps(workflow["draft"]), now(), actor),
        )
        self.store.execute(
            "UPDATE workflows SET status = ?, active_version_id = ?, updated_at = ? WHERE id = ?",
            ("published", version_id, now(), workflow_id),
        )
        published_workflow = self.get_workflow(workflow_id)
        published_version = self.get_version(version_id)
        rexhub_status = self.rexhub.publish_workflow(published_workflow, published_version)
        self.event(
            "workflow.published",
            workflow_id=workflow_id,
            message=f"Workflow published v{version}",
            payload={"versionId": version_id, "version": version, "rexhubDeliveryStatus": rexhub_status},
        )
        self.store.audit(new_id("audit"), "workflow.published", "workflow", workflow_id, {"versionId": version_id, "version": version}, actor=actor)
        return {"workflow": published_workflow, "version": published_version, "validation": validation}

    def versions(self, workflow_id: str) -> dict[str, Any]:
        return {"versions": self.store.rows("SELECT * FROM workflow_versions WHERE workflow_id = ? ORDER BY version DESC", (workflow_id,))}

    def get_version(self, version_id: str) -> dict[str, Any]:
        row = self.store.row("SELECT * FROM workflow_versions WHERE id = ?", (version_id,))
        if not row:
            raise KeyError(f"version not found: {version_id}")
        return row

    def execute_workflow(self, workflow_id: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        execution = self.begin_execution(workflow_id, variables=variables)["execution"]
        return self.resume_execution(execution["id"])

    def begin_execution(self, workflow_id: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        version_id = workflow.get("activeVersionId")
        if not version_id:
            published = self.publish_workflow(workflow_id)
            version_id = published["version"]["id"]
        execution_id = new_id("exec")
        timestamp = now()
        self.store.execute(
            """
            INSERT INTO executions(id, workflow_id, version_id, status, current_node_id, variables_json, error, created_at, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (execution_id, workflow_id, version_id, "pending", None, json.dumps(variables or {}), None, timestamp, None, None),
        )
        self.event("workflow.execution.started", workflow_id=workflow_id, execution_id=execution_id, message="Execution started", payload={"versionId": version_id})
        self.store.audit(new_id("audit"), "workflow.execution.started", "execution", execution_id, {"workflowId": workflow_id, "versionId": version_id})
        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}

    def start_execution_async(self, execution_id: str) -> dict[str, Any]:
        with self._active_workflows_lock:
            existing = self._active_workflows.get(execution_id)
            if existing and not existing.done():
                return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}
            future = self.workflow_pool.submit(self._resume_execution_for_pool, execution_id)
            self._active_workflows[execution_id] = future
        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}

    def _resume_execution_for_pool(self, execution_id: str) -> None:
        try:
            self.resume_execution(execution_id)
        finally:
            with self._active_workflows_lock:
                self._active_workflows.pop(execution_id, None)

    def execute_webhook(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = "/" + path.strip("/")
        return self._execute_matching_trigger(
            "webhook_trigger",
            lambda node: str((node.get("config") or {}).get("path") or "").rstrip("/") == normalized.rstrip("/"),
            {"trigger": {"kind": "webhook", "path": normalized, "payload": payload or {}}},
        )

    def execute_rexhub_event(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._execute_matching_trigger(
            "rexhub_event_trigger",
            lambda node: (node.get("config") or {}).get("eventType") in {event_type, "*"},
            {"trigger": {"kind": "rexhub_event", "eventType": event_type, "payload": payload or {}}},
        )

    def run_schedules(self, schedule: str | None = None) -> dict[str, Any]:
        return self._execute_matching_trigger(
            "schedule_trigger",
            lambda node: schedule is None or str((node.get("config") or {}).get("schedule") or "") == schedule,
            {"trigger": {"kind": "schedule", "schedule": schedule or "manual_run"}},
        )

    def _execute_matching_trigger(self, trigger_type: str, matches: Any, variables: dict[str, Any]) -> dict[str, Any]:
        executions = []
        for workflow in self.list_workflows()["workflows"]:
            graph = workflow["draft"]
            if any(node.get("type") == trigger_type and matches(node) for node in graph.get("nodes", [])):
                executions.append(self.execute_workflow(workflow["id"], variables=variables)["execution"])
        self.event(
            "workflow.triggered",
            message=f"{trigger_type} triggered {len(executions)} workflow(s)",
            payload={"triggerType": trigger_type, "executionIds": [item["id"] for item in executions]},
        )
        return {"matched": len(executions), "executions": executions}

    def resume_execution(self, execution_id: str) -> dict[str, Any]:
        execution = self.get_execution(execution_id)
        if execution["status"] in {"completed", "cancelled"}:
            return {"execution": execution, "steps": self.steps(execution_id)["steps"]}
        version = self.get_version(execution["version_id"])
        graph = version["graph"]
        compiled = compile_graph(graph)
        variables = execution.get("variables") or {}
        if execution["status"] == "paused":
            current_node_id = execution.get("current_node_id")
            if current_node_id and not variables.get(f"approval_{current_node_id}"):
                return {"execution": execution, "steps": self.steps(execution_id)["steps"]}
        self._set_execution_status(execution_id, "running", started=True)
        try:
            while True:
                if self._is_cancelled(execution_id):
                    self.event("workflow.execution.cancelled", workflow_id=execution["workflow_id"], execution_id=execution_id, message="Execution cancelled", payload={})
                    return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}
                next_nodes = self._ready_nodes(execution_id, compiled)
                if not next_nodes:
                    break
                progressed = False
                for node_id in next_nodes:
                    if self._latest_step_status(execution_id, node_id) in {"succeeded", "skipped"}:
                        continue
                    if self._is_cancelled(execution_id):
                        self.event("workflow.execution.cancelled", workflow_id=execution["workflow_id"], execution_id=execution_id, message="Execution cancelled", payload={})
                        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}
                    node = compiled["nodes"][node_id]
                    result = self._run_node(execution_id, execution["workflow_id"], node, variables)
                    if result.get("cancelled"):
                        self._set_execution_status(execution_id, "cancelled", ended=True)
                        self.event("workflow.execution.cancelled", workflow_id=execution["workflow_id"], execution_id=execution_id, message="Execution cancelled", payload={})
                        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}
                    if result.get("paused"):
                        self._set_execution_status(execution_id, "paused", current_node_id=node_id)
                        self.event("workflow.execution.paused", workflow_id=execution["workflow_id"], execution_id=execution_id, node_id=node_id, message=f"Execution paused at {node['name']}", payload={})
                        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}
                    variables.update(result.get("variables", {}))
                    self._update_variables(execution_id, variables)
                    progressed = True
                if not progressed:
                    break
            self._set_execution_status(execution_id, "completed", ended=True)
            self.event("workflow.execution.completed", workflow_id=execution["workflow_id"], execution_id=execution_id, message="Execution completed", payload={})
        except Exception as exc:
            self._set_execution_status(execution_id, "failed", error=str(exc), ended=True)
            self.event("workflow.execution.failed", workflow_id=execution["workflow_id"], execution_id=execution_id, level="error", message=str(exc), payload={})
        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}

    def _ready_nodes(self, execution_id: str, compiled: dict[str, Any]) -> list[str]:
        latest = self._latest_steps(execution_id)
        completed = {node_id for node_id, step in latest.items() if step["status"] in {"succeeded", "skipped"}}
        paused = {node_id for node_id, step in latest.items() if step["status"] == "paused"}
        if paused:
            return []
        ready: list[str] = []
        for node_id in compiled["order"]:
            if node_id in completed:
                continue
            node = compiled["nodes"][node_id]
            incoming = compiled["incoming"].get(node_id, [])
            if not incoming:
                if NODE_BY_TYPE[node["type"]]["category"] == "trigger":
                    ready.append(node_id)
                continue
            active_sources = []
            blocked = False
            for edge in incoming:
                source_id = edge["sourceNodeId"]
                source_node = compiled["nodes"].get(source_id)
                source_step = latest.get(source_id)
                if not source_step or source_step["status"] not in {"succeeded", "skipped"}:
                    blocked = True
                    continue
                if self._edge_active(source_node, edge, source_step.get("output") or {}):
                    active_sources.append(source_id)
            if not blocked and active_sources:
                ready.append(node_id)
        return ready

    def _latest_steps(self, execution_id: str) -> dict[str, dict[str, Any]]:
        rows = self.store.rows("SELECT * FROM execution_steps WHERE execution_id = ? ORDER BY started_at, id", (execution_id,))
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            latest[row["node_id"]] = row
        return latest

    def _latest_step_status(self, execution_id: str, node_id: str) -> str | None:
        return self._latest_steps(execution_id).get(node_id, {}).get("status")

    def _edge_active(self, source_node: dict[str, Any] | None, edge: dict[str, Any], output: dict[str, Any]) -> bool:
        if not source_node:
            return False
        if source_node["type"] == "condition":
            return edge["sourcePort"] == ("true" if output.get("condition") else "false")
        if source_node["type"] == "approval_gate":
            return edge["sourcePort"] == output.get("approval", "approved")
        return True

    def _run_node(self, execution_id: str, workflow_id: str, node: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
        step_id = new_id("step")
        attempt = 1 + int(
            self.store.row(
                "SELECT COUNT(*) AS count FROM execution_steps WHERE execution_id = ? AND node_id = ?",
                (execution_id, node["id"]),
            )["count"]
        )
        self.store.execute(
            """
            INSERT INTO execution_steps(id, execution_id, node_id, status, attempt, input_json, output_json, error, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (step_id, execution_id, node["id"], "running", attempt, json.dumps(variables), "{}", None, now(), None),
        )
        self.store.execute("UPDATE executions SET current_node_id = ? WHERE id = ?", (node["id"], execution_id))
        self.event("workflow.execution.step.started", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], message=f"Started {node['name']}", payload={"node": node})
        output: dict[str, Any] = {"nodeId": node["id"], "nodeType": node["type"]}
        result: dict[str, Any] = {"variables": {f"last_{node['id']}": output}}
        config = node.get("config") or {}
        try:
            if node["type"] in {"manual_trigger", "webhook_trigger", "schedule_trigger", "rexhub_event_trigger"}:
                output["trigger"] = node["type"]
                output["received"] = variables.get("trigger") or {}
            elif node["type"] == "http_request":
                output["http"] = self._execute_http_request(config, variables)
                result["variables"][f"http_{node['id']}"] = output["http"]
            elif node["type"] == "transform_data":
                transformed = self._transform_data(str(config.get("expression") or "return input"), variables)
                output["result"] = transformed
                result["variables"][f"transform_{node['id']}"] = transformed
            elif node["type"] == "condition":
                condition = str(config.get("condition", "true")).strip().lower()
                output["condition"] = condition not in {"false", "0", "no", "off"}
            elif node["type"] in {"parallel_branch", "join"}:
                output["flow"] = node["type"]
            elif node["type"] == "delay":
                seconds = max(0.0, float(config.get("seconds") or 0))
                time.sleep(min(seconds, 0.25))
                output["waitedSeconds"] = seconds
            elif node["type"] == "approval_gate":
                approval = variables.get(f"approval_{node['id']}")
                if not approval:
                    task = self.create_task(
                        {
                            "workflowId": workflow_id,
                            "executionId": execution_id,
                            "nodeId": node["id"],
                            "title": f"Approval required: {node['name']}",
                            "description": "AlosCurrent approval gate is waiting.",
                            "assigneeId": config.get("assigneeId"),
                            "priority": "high",
                            "status": "review",
                            "acceptanceCriteria": "Approve or reject the paused workflow execution.",
                        }
                    )["task"]
                    approval_delivery = self.rexhub.request_approval(execution_id, node["id"], config.get("assigneeId"))
                    output["taskId"] = task["id"]
                    output["rexhubApprovalDeliveryStatus"] = approval_delivery
                    self._finish_step(step_id, "paused", output)
                    self.event(
                        "approval.requested",
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        node_id=node["id"],
                        message="Approval requested",
                        payload={"taskId": task["id"], "rexhubDeliveryStatus": approval_delivery},
                    )
                    return {"paused": True}
                output["approval"] = approval
            elif node["type"] == "create_task":
                task = self.create_task(
                    {
                        "workflowId": workflow_id,
                        "executionId": execution_id,
                        "nodeId": node["id"],
                        "title": config.get("title") or node["name"],
                        "description": config.get("description") or "",
                        "priority": config.get("priority") or "normal",
                        "status": "ready",
                        "acceptanceCriteria": config.get("acceptanceCriteria") or "",
                    }
                )["task"]
                output["taskId"] = task["id"]
            elif node["type"] == "assign_department_head":
                department_id = config.get("departmentId") or "operations"
                department = self.store.row("SELECT * FROM departments WHERE id = ?", (department_id,))
                if not department:
                    raise ValueError(f"department not found: {department_id}")
                output["departmentId"] = department_id
                output["assigneeId"] = department["head_id"]
                delivery = self.rexhub.assign_department_head(None, department_id, department["head_id"])
                output["rexhubDeliveryStatus"] = delivery
                self.event("task.assigned", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], message=f"Assigned Department Head {department['head_id']}", payload=output)
            elif node["type"] == "assign_sub_agent":
                capability = config.get("capability") or ""
                agent = self._find_agent(capability)
                output["assigneeId"] = agent["id"]
                output["capability"] = capability
                delivery = self.rexhub.assign_sub_agent(None, agent["id"])
                output["rexhubDeliveryStatus"] = delivery
                self.event("task.assigned", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], message=f"Assigned Sub-Agent {agent['id']}", payload=output)
            elif node["type"] == "swarm_assignment":
                mode = config.get("assignmentMode") or "autonomous"
                if mode == "manual":
                    agent_id = config.get("agentId")
                    if not agent_id:
                        raise ValueError("Manual assignment requires an Agent ID")
                    agent = self.store.row("SELECT * FROM agents WHERE id = ?", (agent_id,))
                    if not agent:
                        raise ValueError(f"Agent not found: {agent_id}")
                    output["assigneeId"] = agent_id
                    output["assignmentMode"] = "manual"
                else:
                    capability = config.get("capability") or "research"
                    agent = self._find_agent(capability)
                    output["assigneeId"] = agent["id"]
                    output["capability"] = capability
                    output["assignmentMode"] = "autonomous"
                
                delivery = self.rexhub.assign_sub_agent(None, output["assigneeId"])
                output["rexhubDeliveryStatus"] = delivery
                self.event("task.assigned", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], message=f"Swarm assigned task to {output['assigneeId']} ({mode})", payload=output)
            elif node["type"] == "escalation_gate":
                revisions = int(variables.get("revisionCycles", 0))
                max_revisions = int(config.get("maxRevisions") or 3)
                output["escalated"] = revisions >= max_revisions
                if output["escalated"]:
                    delivery = self.rexhub.create_escalation(execution_id, node["id"], "Revision limit reached")
                    output["rexhubDeliveryStatus"] = delivery
                    self.event("escalation.created", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], level="warn", message="Revision limit reached", payload=output)
            elif node["type"] in {"notification", "audit_log"}:
                message = config.get("message") or node["name"]
                self.event("audit.recorded", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], message=message, payload={"node": node})
            elif node["type"] == "invoke_agent":
                from src.agents.invoke import run_agent_step
                from modules.current.contracts.nodes.invoke_agent import InvokeAgentNodeInput

                agent_input = InvokeAgentNodeInput(
                    prompt=str(config.get("prompt") or "Complete the objective."),
                    agent_id=str(config.get("agentId") or "supervisor"),
                    max_turns=int(config.get("maxTurns") or 10),
                    timeout_seconds=int(config.get("timeoutSeconds") or 300),
                )

                # Cooperative cancellation checker
                def check_cancelled() -> bool:
                    try:
                        exec_state = self.get_execution(execution_id)
                        return exec_state.get("status") == "cancelled"
                    except:
                        return True # Safety default

                # Turn event relay
                def relay_event(evt_type: str, evt_payload: dict):
                    self.event(evt_type, workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], payload=evt_payload)

                # Dispatch to thread pool (RFC-0002 Decision 2)
                future = self.agent_pool.submit(
                    run_agent_step,
                    agent_input,
                    cancel_check=check_cancelled,
                    on_event=relay_event,
                    run_id=execution_id,
                    step_id=node["id"]
                )

                # Block and wait for agent turn completion
                agent_output = future.result(timeout=agent_input.timeout_seconds + 5)
                
                output["agent_status"] = agent_output.status
                output["agent_output"] = agent_output.output
                output["turns_used"] = agent_output.turns_used
                if agent_output.error:
                    output["agent_error"] = agent_output.error.dict()
                
                # Check for cancellation exit
                if agent_output.status == "cancelled":
                    self._finish_step(step_id, "cancelled", output)
                    return {"cancelled": True}
                
                result["variables"][f"agent_{node['id']}"] = agent_output.output
            
            elif node["type"] == "shell":
                from src.runtime.terminal import ObservedPtyRunner
                
                command = str(config.get("command") or "")
                timeout = int(config.get("timeoutSeconds") or 60)
                
                def on_data(data: str):
                    self.event(
                        "terminal.observed_data", 
                        workflow_id=workflow_id, 
                        execution_id=execution_id, 
                        node_id=node["id"], 
                        payload={"data": data}
                    )
                
                runner = ObservedPtyRunner(on_data=on_data, timeout_seconds=timeout)
                # Run in current directory or workspace root
                shell_result = runner.run(command)
                
                output["stdout"] = shell_result["stdout"]
                output["stderr"] = shell_result["stderr"]
                output["returncode"] = shell_result["returncode"]
                output["status"] = shell_result["status"]
                
                result["variables"][f"shell_{node['id']}"] = shell_result["stdout"]

            elif node["type"] == "output":
                output["summary"] = config.get("summary") or "Done"
            self._finish_step(step_id, "succeeded", output)
            self.event("workflow.execution.step.completed", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], message=f"Completed {node['name']}", payload=output)
            return result
        except Exception as exc:
            self._finish_step(step_id, "failed", output, str(exc))
            self.event("workflow.execution.step.failed", workflow_id=workflow_id, execution_id=execution_id, node_id=node["id"], level="error", message=str(exc), payload=output)
            raise

    def _execute_http_request(self, config: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
        method = str(config.get("method") or "GET").upper()
        url = str(config.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HTTP Request node requires an http:// or https:// URL")
        headers = self._parse_headers(config.get("headersJson"))
        body = str(config.get("body") or "")
        if body == "{{variables}}":
            body = json.dumps(variables)
            headers.setdefault("content-type", "application/json")
        data = body.encode("utf-8") if method not in {"GET", "HEAD"} and body else None
        timeout = max(1.0, min(float(config.get("timeoutSeconds") or 10), 60.0))
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_body = response.read(65536).decode("utf-8", errors="replace")
                return {
                    "status": response.status,
                    "ok": 200 <= response.status < 400,
                    "body": response_body,
                    "headers": dict(response.headers.items()),
                }
        except urllib.error.HTTPError as exc:
            response_body = exc.read(8192).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP request failed with status {exc.code}: {response_body[:400]}") from exc

    def _parse_headers(self, raw: Any) -> dict[str, str]:
        if not raw:
            return {}
        parsed = json.loads(str(raw))
        if not isinstance(parsed, dict):
            raise ValueError("Headers JSON must be an object")
        return {str(key): str(value) for key, value in parsed.items()}

    def _transform_data(self, expression: str, variables: dict[str, Any]) -> Any:
        expr = expression.strip()
        if not expr or expr == "return input":
            return variables
        if expr.startswith("return "):
            expr = expr[7:].strip()
        if expr in {"input", "variables"}:
            return variables
        if expr.startswith("variables."):
            value: Any = variables
            for part in expr.split(".")[1:]:
                if not isinstance(value, dict):
                    return None
                value = value.get(part)
            return value
        if expr.startswith("set "):
            key, _, value = expr[4:].partition("=")
            if not key.strip():
                raise ValueError("Transform set expression requires a key")
            return {key.strip(): self._coerce_value(value.strip())}
        try:
            return json.loads(expr)
        except json.JSONDecodeError:
            return {"result": expr}

    def _coerce_value(self, value: str) -> Any:
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
        if value.lower() == "null":
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def approve_execution(self, execution_id: str, node_id: str, approved: bool = True) -> dict[str, Any]:
        self.record_approval(execution_id, node_id=node_id, approved=approved)
        return self.resume_execution(execution_id)

    def record_approval(self, execution_id: str, node_id: str, approved: bool = True) -> dict[str, Any]:
        execution = self.get_execution(execution_id)
        variables = execution.get("variables") or {}
        variables[f"approval_{node_id}"] = "approved" if approved else "rejected"
        self._update_variables(execution_id, variables)
        self.store.execute(
            "UPDATE execution_steps SET status = ?, output_json = ?, ended_at = ? WHERE execution_id = ? AND node_id = ? AND status = 'paused'",
            ("succeeded", json.dumps({"approval": variables[f"approval_{node_id}"]}), now(), execution_id, node_id),
        )
        self.event("approval.resolved", workflow_id=execution["workflow_id"], execution_id=execution_id, node_id=node_id, message=f"Approval {variables[f'approval_{node_id}']}", payload={"approved": approved})
        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}

    def retry_execution(self, execution_id: str) -> dict[str, Any]:
        self.store.execute("UPDATE executions SET status = ?, error = NULL, ended_at = NULL WHERE id = ?", ("pending", execution_id))
        return self.resume_execution(execution_id)

    def cancel_execution(self, execution_id: str) -> dict[str, Any]:
        execution = self.get_execution(execution_id)
        self._set_execution_status(execution_id, "cancelled", ended=True)
        self.store.execute("UPDATE execution_steps SET status = ? WHERE execution_id = ? AND status IN ('pending', 'running')", ("cancelled", execution_id))
        self.event("workflow.execution.cancelled", workflow_id=execution["workflow_id"], execution_id=execution_id, message="Execution cancelled", payload={})
        return {"execution": self.get_execution(execution_id), "steps": self.steps(execution_id)["steps"]}

    def recover(self) -> dict[str, Any]:
        rows = self.store.rows("SELECT id FROM executions WHERE status IN ('pending', 'running', 'paused')")
        recovered = []
        for row in rows:
            recovered.append(self.resume_execution(row["id"])["execution"]["id"])
        return {"recovered": recovered}

    def executions(self) -> dict[str, Any]:
        return {"executions": self.store.rows("SELECT * FROM executions ORDER BY created_at DESC LIMIT 100")}

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        row = self.store.row("SELECT * FROM executions WHERE id = ?", (execution_id,))
        if not row:
            raise KeyError(f"execution not found: {execution_id}")
        return row

    def steps(self, execution_id: str) -> dict[str, Any]:
        return {"steps": self.store.rows("SELECT * FROM execution_steps WHERE execution_id = ? ORDER BY started_at, id", (execution_id,))}

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = payload.get("id") or new_id("task")
        timestamp = now()
        task = {
            "id": task_id,
            "workflow_id": payload.get("workflowId"),
            "execution_id": payload.get("executionId"),
            "node_id": payload.get("nodeId"),
            "title": payload.get("title") or "Untitled task",
            "description": payload.get("description") or "",
            "department_id": payload.get("departmentId"),
            "assignee_id": payload.get("assigneeId"),
            "priority": payload.get("priority") or "normal",
            "status": payload.get("status") or "ready",
            "acceptance_criteria": payload.get("acceptanceCriteria") or "",
            "due_at": payload.get("dueAt"),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.store.execute(
            """
            INSERT INTO tasks(id, workflow_id, execution_id, node_id, title, description, department_id, assignee_id, priority, status, acceptance_criteria, due_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(task.values()),
        )
        rexhub_status = self.rexhub.create_task(task)
        self.event(
            "task.created",
            workflow_id=task["workflow_id"],
            execution_id=task["execution_id"],
            node_id=task["node_id"],
            message=f"Task created: {task['title']}",
            payload={"taskId": task_id, "rexhubDeliveryStatus": rexhub_status},
        )
        return {"task": self.get_task(task_id)}

    def update_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_task(task_id)
        merged = {**current, **payload, "updated_at": now()}
        self.store.execute(
            """
            UPDATE tasks SET title=?, description=?, department_id=?, assignee_id=?, priority=?, status=?, acceptance_criteria=?, due_at=?, updated_at=? WHERE id=?
            """,
            (
                merged["title"],
                merged.get("description", ""),
                merged.get("department_id") or merged.get("departmentId"),
                merged.get("assignee_id") or merged.get("assigneeId"),
                merged.get("priority", "normal"),
                merged.get("status", "ready"),
                merged.get("acceptance_criteria") or merged.get("acceptanceCriteria") or "",
                merged.get("due_at") or merged.get("dueAt"),
                merged["updated_at"],
                task_id,
            ),
        )
        rexhub_status = self.rexhub.update_task(task_id, payload)
        self.event(
            "task.updated",
            workflow_id=current.get("workflow_id"),
            execution_id=current.get("execution_id"),
            node_id=current.get("node_id"),
            message=f"Task updated: {task_id}",
            payload={**payload, "rexhubDeliveryStatus": rexhub_status},
        )
        return {"task": self.get_task(task_id)}

    def tasks(self) -> dict[str, Any]:
        return {"tasks": self.store.rows("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 200")}

    def get_task(self, task_id: str) -> dict[str, Any]:
        row = self.store.row("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not row:
            raise KeyError(f"task not found: {task_id}")
        return row

    def swarm(self) -> dict[str, Any]:
        return {
            "departments": self.store.rows("SELECT * FROM departments ORDER BY name"),
            "agents": self.store.rows("SELECT * FROM agents ORDER BY kind, name"),
        }

    def get_available_agents(self) -> dict[str, Any]:
        agents = self.store.rows("SELECT id, name, kind, department_id, capabilities_json FROM agents WHERE available = 1")
        return {"agents": agents}

    def events(self, execution_id: str | None = None, limit: int = 200) -> dict[str, Any]:
        if execution_id:
            rows = self.store.rows("SELECT * FROM events WHERE execution_id = ? ORDER BY timestamp DESC LIMIT ?", (execution_id, limit))
        else:
            rows = self.store.rows("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,))
        return {"events": rows}

    def event(
        self,
        event_type: str,
        workflow_id: str | None = None,
        execution_id: str | None = None,
        node_id: str | None = None,
        level: str = "info",
        message: str = "",
        payload: dict[str, Any] | None = None,
        delivery_status: str = "local_only",
    ) -> dict[str, Any]:
        event_id = new_id("evt")
        event_payload = {
            "id": event_id,
            "type": event_type,
            "workflowId": workflow_id,
            "executionId": execution_id,
            "nodeId": node_id,
            "level": level,
            "message": message,
            "payload": payload or {},
            "timestamp": now(),
        }
        actual_delivery_status = self.rexhub.emit_event(event_payload)
        self.store.execute(
            """
            INSERT INTO events(id, type, workflow_id, execution_id, node_id, level, message, payload_json, delivery_status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, event_type, workflow_id, execution_id, node_id, level, message, json.dumps(payload or {}), actual_delivery_status or delivery_status, event_payload["timestamp"]),
        )
        return {"eventId": event_id}

    def audit_log(self) -> dict[str, Any]:
        return {"audit": self.store.rows("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 200")}

    def _finish_step(self, step_id: str, status: str, output: dict[str, Any], error: str | None = None) -> None:
        self.store.execute(
            "UPDATE execution_steps SET status = ?, output_json = ?, error = ?, ended_at = ? WHERE id = ?",
            (status, json.dumps(output), error, now(), step_id),
        )

    def _set_execution_status(self, execution_id: str, status: str, current_node_id: str | None = None, error: str | None = None, started: bool = False, ended: bool = False) -> None:
        fields = ["status = ?", "error = ?"]
        values: list[Any] = [status, error]
        if current_node_id is not None:
            fields.append("current_node_id = ?")
            values.append(current_node_id)
        if started:
            fields.append("started_at = COALESCE(started_at, ?)")
            values.append(now())
        if ended:
            fields.append("ended_at = ?")
            values.append(now())
        values.append(execution_id)
        self.store.execute(f"UPDATE executions SET {', '.join(fields)} WHERE id = ?", tuple(values))

    def _update_variables(self, execution_id: str, variables: dict[str, Any]) -> None:
        self.store.execute("UPDATE executions SET variables_json = ? WHERE id = ?", (json.dumps(variables), execution_id))

    def _is_cancelled(self, execution_id: str) -> bool:
        try:
            return self.get_execution(execution_id).get("status") == "cancelled"
        except KeyError:
            return True

    def _find_agent(self, capability: str) -> dict[str, Any]:
        for agent in self.store.rows("SELECT * FROM agents WHERE available = 1"):
            if capability in agent.get("capabilities", []):
                return agent
        raise ValueError(f"no available agent with capability: {capability}")
