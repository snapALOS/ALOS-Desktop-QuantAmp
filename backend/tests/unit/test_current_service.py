import sys
import time
from pathlib import Path


CURRENT_SRC = Path(__file__).resolve().parents[3] / "modules" / "current" / "backend" / "src"
if str(CURRENT_SRC) not in sys.path:
    sys.path.insert(0, str(CURRENT_SRC))

from alos_current.service import AlosCurrentService
from alos_current.storage import AlosCurrentStore


def service_for(tmp_path):
    return AlosCurrentService(AlosCurrentStore(tmp_path / "current"))


def wait_for_status(service, execution_id, expected, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        execution = service.get_execution(execution_id)
        if execution["status"] in expected:
            return execution
        time.sleep(0.05)
    return service.get_execution(execution_id)


def test_current_approval_gate_persists_tasks_and_audit(tmp_path):
    service = service_for(tmp_path)

    workflow = service.create_workflow({"name": "Approval workflow"})["workflow"]
    result = service.execute_workflow(workflow["id"])

    assert result["execution"]["status"] == "paused"
    assert service.tasks()["tasks"][0]["status"] == "review"
    assert any(item["action"] == "workflow.execution.started" for item in service.audit_log()["audit"])

    resolved = service.approve_execution(
        result["execution"]["id"],
        node_id=result["execution"]["current_node_id"],
        approved=True,
    )

    assert resolved["execution"]["status"] == "completed"
    assert any(event["type"] == "approval.resolved" for event in service.events()["events"])


def test_current_async_execution_can_be_cancelled_before_resume(tmp_path):
    service = service_for(tmp_path)

    workflow = service.create_workflow({"name": "Async workflow"})["workflow"]
    created = service.begin_execution(workflow["id"])
    execution_id = created["execution"]["id"]

    service.cancel_execution(execution_id)
    service.start_execution_async(execution_id)
    execution = wait_for_status(service, execution_id, {"cancelled"})

    assert execution["status"] == "cancelled"
    assert any(event["type"] == "workflow.execution.cancelled" for event in service.events(execution_id=execution_id)["events"])
