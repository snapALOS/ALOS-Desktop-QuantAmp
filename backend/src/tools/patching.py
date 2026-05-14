import difflib
import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.core.config import DATA_DIR, ROOT_DIR, config as alos_config
from src.core.policy import PolicyViolation, classify_file_write, resolve_workspace_path
from src.runtime.chamber_gate import (
    block_gate,
    get_gate_for_patch,
    record_gate_write,
    run_patch_gate,
    stage_patch_gate,
)
from src.runtime.mutation import mutation_gate


PATCH_INBOX_PATH = Path(os.environ.get("ALOS_PATCH_INBOX_PATH", str(DATA_DIR / "patch_inbox.json")))


class PatchHunk(BaseModel):
    header: str
    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)


class PatchProposal(BaseModel):
    id: str
    file: str
    hunks: list[PatchHunk]
    before_hash: str
    after_hash: str
    rationale: str
    diff: str
    proposed_content: str = ""
    status: str = "pending"
    mutation_id: Optional[str] = None # QuantAmp Mutation ID
    created_at: str


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT_DIR))


def _read_inbox() -> list[dict[str, Any]]:
    if not PATCH_INBOX_PATH.exists():
        return []
    try:
        data = json.loads(PATCH_INBOX_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_inbox(items: list[dict[str, Any]]) -> None:
    PATCH_INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    PATCH_INBOX_PATH.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_unified_hunks(diff: str) -> list[PatchHunk]:
    hunks: list[PatchHunk] = []
    current: Optional[PatchHunk] = None
    for line in diff.splitlines():
        if line.startswith("@@"):
            if current:
                hunks.append(current)
            current = PatchHunk(header=line)
        elif current and line.startswith("-") and not line.startswith("---"):
            current.before.append(line[1:])
        elif current and line.startswith("+") and not line.startswith("+++"):
            current.after.append(line[1:])
        elif current and line.startswith(" "):
            current.before.append(line[1:])
            current.after.append(line[1:])
    if current:
        hunks.append(current)
    return hunks


def build_patch_proposal(file_path: str, new_content: str, rationale: str) -> PatchProposal:
    target = resolve_workspace_path(file_path)
    old_content = target.read_text(encoding="utf-8") if target.exists() else ""
    before_hash = sha256_text(old_content)
    after_hash = sha256_text(new_content)
    if before_hash == after_hash:
        raise ValueError("Patch proposal has no file changes.")
    rel = _relative_path(target)
    diff = "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"{rel} (current)",
            tofile=f"{rel} (proposed)",
            n=3,
        )
    )
    return PatchProposal(
        id=str(uuid.uuid4()),
        file=rel,
        hunks=_parse_unified_hunks(diff),
        before_hash=before_hash,
        after_hash=after_hash,
        rationale=rationale,
        diff=diff,
        proposed_content=new_content,
        created_at=datetime.utcnow().isoformat(),
    )


def save_patch_proposal(proposal: PatchProposal) -> PatchProposal:
    items = [item for item in _read_inbox() if item.get("id") != proposal.id]
    items.insert(0, proposal.model_dump())
    _write_inbox(items[:100])
    return proposal


def list_patch_proposals(status: Optional[str] = None) -> list[dict[str, Any]]:
    items = _read_inbox()
    if status:
        items = [item for item in items if item.get("status") == status]
    return [public_patch_payload(PatchProposal(**item)) for item in items]


def get_patch_proposal(patch_id: str) -> PatchProposal:
    for item in _read_inbox():
        if item.get("id") == patch_id:
            return PatchProposal(**item)
    raise KeyError(f"Patch proposal not found: {patch_id}")


def update_patch_status(patch_id: str, status: str) -> None:
    items = _read_inbox()
    for item in items:
        if item.get("id") == patch_id:
            item["status"] = status
            item["updated_at"] = datetime.utcnow().isoformat()
            _write_inbox(items)
            return
    raise KeyError(f"Patch proposal not found: {patch_id}")


def apply_patch_proposal(
    proposal: PatchProposal,
    new_content: str,
    *,
    override_chamber: bool = False,
    actor: str = "",
) -> dict[str, Any]:
    target = resolve_workspace_path(proposal.file)
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if sha256_text(current) != proposal.before_hash:
        update_patch_status(proposal.id, "stale")
        return {
            "status": "stale",
            "message": "Patch was not applied because the file changed after proposal.",
            "file": proposal.file,
        }
    if sha256_text(new_content) != proposal.after_hash:
        update_patch_status(proposal.id, "invalid")
        return {
            "status": "invalid",
            "message": "Patch was not applied because proposed content hash did not match.",
            "file": proposal.file,
        }

    decision = classify_file_write(target, new_content)
    
    gate = get_gate_for_patch(proposal.id)
    if not gate:
        gate = stage_patch_gate(
            patch_id=proposal.id,
            file_path=proposal.file,
            risk=decision.risk,
            rationale=proposal.rationale,
        )
    if gate.get("status") != "passed" and not override_chamber:
        if alos_config.chamber_gate_required:
            gate = run_patch_gate(proposal.id, new_content)
        else:
            gate["status"] = "skipped"
            gate["message"] = "Chamber gate skipped by Settings."
    if override_chamber and not alos_config.allow_chamber_override:
        block_gate(proposal.id, "Chamber override is disabled in Settings.")
        update_patch_status(proposal.id, "blocked")
        return {
            "status": "blocked",
            "message": "Patch was not applied because Chamber override is disabled in Settings.",
            "file": proposal.file,
            "chamber_gate": get_gate_for_patch(proposal.id),
        }
    if gate.get("status") != "passed" and alos_config.chamber_gate_required and not override_chamber:
        block_gate(proposal.id, "Chamber build/test gate did not pass.")
        update_patch_status(proposal.id, "blocked")
        return {
            "status": "blocked",
            "message": "Patch was not applied because the Chamber build/test gate did not pass.",
            "file": proposal.file,
            "chamber_gate": gate,
        }

    mut_id = proposal.mutation_id
    if not mut_id:
        mut_id = mutation_gate.propose(str(target), new_content, "Patch application fallback")
    
    prop = mutation_gate.get_proposal(mut_id)
    if prop and prop.status == "pending":
        mutation_gate.approve(mut_id)
    
    success = mutation_gate.execute(mut_id)

    if not success:
        return {
            "status": "failed",
            "message": "Mutation gate denied execution. check system_logger for hardware/policy faults.",
            "file": proposal.file,
            "chamber_gate": gate,
        }

    update_patch_status(proposal.id, "applied")
    record_gate_write(proposal.id, override=override_chamber, actor=actor)
        
    return {
        "status": "applied",
        "file": proposal.file,
        "risk": decision.risk,
        "after_hash": proposal.after_hash,
        "chamber_gate": get_gate_for_patch(proposal.id),
    }


def reject_patch_proposal(patch_id: str) -> dict[str, Any]:
    update_patch_status(patch_id, "rejected")
    return {"status": "rejected", "patch_id": patch_id}


def propose_and_save_patch(file_path: str, new_content: str, rationale: str) -> PatchProposal:
    try:
        proposal = build_patch_proposal(file_path, new_content, rationale)
        target = resolve_workspace_path(proposal.file)
        decision = classify_file_write(target, new_content)
        mutation_id = mutation_gate.propose(str(target), new_content, rationale)
        proposal.mutation_id = mutation_id
        saved = save_patch_proposal(proposal)
        stage_patch_gate(
            patch_id=saved.id,
            file_path=saved.file,
            risk=decision.risk,
            rationale=saved.rationale,
        )
        return saved
    except PolicyViolation:
        raise


def apply_patch_by_id(patch_id: str, *, override_chamber: bool = False, actor: str = "") -> dict[str, Any]:
    proposal = get_patch_proposal(patch_id)
    if proposal.status not in {"pending", "blocked"}:
        return {"status": proposal.status, "patch_id": patch_id, "message": "Patch is no longer pending."}
    return {
        "patch_id": patch_id,
        **apply_patch_proposal(
            proposal,
            proposal.proposed_content,
            override_chamber=override_chamber,
            actor=actor,
        ),
    }


def public_patch_payload(proposal: PatchProposal) -> dict[str, Any]:
    data = proposal.model_dump(exclude={"proposed_content"})
    data["hunk_count"] = len(proposal.hunks)
    data["chamber_gate"] = get_gate_for_patch(proposal.id)
    return data
