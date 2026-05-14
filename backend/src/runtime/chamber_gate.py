from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.config import DATA_DIR, ROOT_DIR, system_logger


CHAMBER_GATES_PATH = Path(os.environ.get("ALOS_CHAMBER_GATES_PATH", str(DATA_DIR / "chamber_gates.json")))
CHAMBER_RUN_ROOT = Path(os.environ.get("ALOS_CHAMBER_RUN_ROOT", str(DATA_DIR / "chamber_runs")))

TERMINAL_STATUSES = {"passed", "failed", "blocked", "approved", "overridden", "written"}


def utc_now() -> str:
    return datetime.utcnow().isoformat()


def _read_records() -> list[dict[str, Any]]:
    if not CHAMBER_GATES_PATH.exists():
        return []
    try:
        data = json.loads(CHAMBER_GATES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_records(records: list[dict[str, Any]]) -> None:
    CHAMBER_GATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHAMBER_GATES_PATH.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _upsert(record: dict[str, Any]) -> dict[str, Any]:
    records = [item for item in _read_records() if item.get("id") != record.get("id")]
    records.insert(0, record)
    _write_records(records[:200])
    return record


def _workspace_root() -> Path:
    return ROOT_DIR.resolve()


def _default_commands(file_path: str, risk: str) -> list[str]:
    suffix = Path(file_path).suffix.lower()
    parts = set(Path(file_path).parts)
    commands: list[str] = []
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".html"}:
        commands.append("npx tsc -b --noEmit")
    if suffix == ".py" or "backend" in parts:
        commands.append("python3.11 -m pytest tests")
    if suffix in {".md", ".txt", ".rst"}:
        commands.append("python3.11 -c \"print('documentation chamber gate passed')\"")
    if not commands and risk in {"high", "critical"}:
        commands.append("python3.11 -m pytest tests")
    return commands


def stage_patch_gate(
    *,
    patch_id: str,
    file_path: str,
    risk: str,
    rationale: str,
    commands: list[str] | None = None,
) -> dict[str, Any]:
    existing = get_gate_for_patch(patch_id)
    if existing and existing.get("status") not in TERMINAL_STATUSES:
        return existing

    now = utc_now()
    record = {
        "id": f"chamber-{patch_id[:8]}",
        "patch_id": patch_id,
        "file": file_path,
        "risk": risk,
        "rationale": rationale,
        "commands": commands if commands is not None else _default_commands(file_path, risk),
        "status": "staged",
        "evidence": [],
        "override": None,
        "created_at": now,
        "updated_at": now,
    }
    return _upsert(record)


def list_chamber_gates(status: str | None = None) -> list[dict[str, Any]]:
    records = _read_records()
    if status:
        records = [record for record in records if record.get("status") == status]
    return records


def get_gate(gate_id: str) -> dict[str, Any]:
    for record in _read_records():
        if record.get("id") == gate_id:
            return record
    raise KeyError(f"Chamber gate not found: {gate_id}")


def get_gate_for_patch(patch_id: str) -> dict[str, Any] | None:
    for record in _read_records():
        if record.get("patch_id") == patch_id:
            return record
    return None


def _ignore_workspace_items(_dir: str, names: list[str]) -> set[str]:
    ignored = {
        ".git",
        ".gitnexus",
        ".pytest_cache",
        "__pycache__",
        "dist",
        "htmlcov",
        "logs",
        "memory",
        "data",
    }
    return {name for name in names if name in ignored or name.endswith(".alos_bak")}


def _prepare_workspace(gate_id: str) -> Path:
    source = _workspace_root()
    target = CHAMBER_RUN_ROOT / gate_id / "workspace"
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=_ignore_workspace_items)
    return target


def _write_staged_content(workspace: Path, file_path: str, content: str) -> Path:
    relative = Path(file_path)
    if relative.is_absolute():
        relative = relative.resolve().relative_to(_workspace_root())
    target = (workspace / relative).resolve()
    target.relative_to(workspace.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _run_command(command: str, cwd: Path) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        return {
            "command": command,
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "duration_seconds": round(time.time() - started, 2),
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "failed",
            "exit_code": 124,
            "duration_seconds": round(time.time() - started, 2),
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"Command timed out after 180s: {command}",
        }


def run_patch_gate(patch_id: str, proposed_content: str, *, commands: list[str] | None = None) -> dict[str, Any]:
    record = get_gate_for_patch(patch_id)
    if not record:
        raise KeyError(f"Chamber gate not found for patch: {patch_id}")

    if commands is not None:
        record["commands"] = commands

    record["status"] = "running"
    record["updated_at"] = utc_now()
    record["evidence"] = []
    _upsert(record)

    try:
        workspace = _prepare_workspace(record["id"])
        staged_file = _write_staged_content(workspace, str(record["file"]), proposed_content)
        evidence: list[dict[str, Any]] = []
        for command in record.get("commands", []):
            result = _run_command(str(command), workspace)
            evidence.append(result)
            if result["status"] != "passed":
                break
        if not evidence:
            evidence.append(
                {
                    "command": "stage-only",
                    "status": "passed",
                    "exit_code": 0,
                    "duration_seconds": 0,
                    "stdout": f"Staged {staged_file.relative_to(workspace)} without inferred build commands.",
                    "stderr": "",
                }
            )
        record["evidence"] = evidence
        record["status"] = "passed" if all(item["status"] == "passed" for item in evidence) else "failed"
    except Exception as exc:
        system_logger.warning(f"Chamber gate failed for patch {patch_id}: {exc}")
        record["status"] = "failed"
        record["evidence"] = [
            {
                "command": "stage",
                "status": "failed",
                "exit_code": 1,
                "duration_seconds": 0,
                "stdout": "",
                "stderr": str(exc),
            }
        ]
    record["updated_at"] = utc_now()
    return _upsert(record)


def block_gate(patch_id: str, reason: str) -> dict[str, Any]:
    record = get_gate_for_patch(patch_id)
    if not record:
        raise KeyError(f"Chamber gate not found for patch: {patch_id}")
    record["status"] = "blocked"
    record["blocked_reason"] = reason
    record["updated_at"] = utc_now()
    return _upsert(record)


def record_gate_write(patch_id: str, *, override: bool = False, actor: str = "") -> dict[str, Any]:
    record = get_gate_for_patch(patch_id)
    if not record:
        raise KeyError(f"Chamber gate not found for patch: {patch_id}")
    record["status"] = "overridden" if override else "written"
    if override:
        record["override"] = {"actor": actor or "unknown", "approved_at": utc_now()}
    record["updated_at"] = utc_now()
    return _upsert(record)


def public_chamber_gate_summary() -> dict[str, Any]:
    records = list_chamber_gates()
    counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {"total": len(records), "counts": counts, "gates": records[:50]}
