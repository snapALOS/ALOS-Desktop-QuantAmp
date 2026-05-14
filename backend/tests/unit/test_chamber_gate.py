from pathlib import Path

from src.runtime import chamber_gate
from src.runtime.mutation import mutation_gate
from src.tools import patching


def _proposal(tmp_path, monkeypatch, *, commands):
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    inbox = tmp_path / "patch_inbox.json"
    gates = tmp_path / "chamber_gates.json"
    runs = tmp_path / "chamber_runs"

    monkeypatch.setattr(patching, "PATCH_INBOX_PATH", inbox)
    monkeypatch.setattr(chamber_gate, "CHAMBER_GATES_PATH", gates)
    monkeypatch.setattr(chamber_gate, "CHAMBER_RUN_ROOT", runs)
    monkeypatch.setattr(chamber_gate, "_workspace_root", lambda: root.resolve())

    def resolve(raw_path: str, *, must_exist: bool = False):
        path = Path(raw_path)
        resolved = path if path.is_absolute() else root / path
        if must_exist and not resolved.exists():
            raise ValueError("missing test path")
        return resolved.resolve()

    monkeypatch.setattr(patching, "resolve_workspace_path", resolve)
    monkeypatch.setattr(patching, "_relative_path", lambda p: str(p.resolve().relative_to(root)))

    new_content = "VALUE = 2\n"
    proposal = patching.build_patch_proposal("app.py", new_content, "change value")
    proposal.mutation_id = mutation_gate.propose(str(target), new_content, "change value")
    patching.save_patch_proposal(proposal)
    chamber_gate.stage_patch_gate(
        patch_id=proposal.id,
        file_path=proposal.file,
        risk="high",
        rationale=proposal.rationale,
        commands=commands,
    )
    return proposal, target, new_content


def test_chamber_gate_blocks_failed_validation(tmp_path, monkeypatch):
    proposal, target, new_content = _proposal(
        tmp_path,
        monkeypatch,
        commands=["python3.11 -c \"import sys; sys.exit(3)\""],
    )

    result = patching.apply_patch_proposal(proposal, new_content)

    assert result["status"] == "blocked"
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    gate = chamber_gate.get_gate_for_patch(proposal.id)
    assert gate is not None
    assert gate["status"] == "blocked"
    assert gate["evidence"][0]["exit_code"] == 3


def test_chamber_gate_allows_write_after_passed_validation(tmp_path, monkeypatch):
    proposal, target, new_content = _proposal(
        tmp_path,
        monkeypatch,
        commands=["python3.11 -c \"print('ok')\""],
    )

    result = patching.apply_patch_proposal(proposal, new_content)

    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    gate = chamber_gate.get_gate_for_patch(proposal.id)
    assert gate is not None
    assert gate["status"] == "written"
    assert gate["evidence"][0]["status"] == "passed"


def test_chamber_override_writes_and_records_actor(tmp_path, monkeypatch):
    proposal, target, new_content = _proposal(
        tmp_path,
        monkeypatch,
        commands=["python3.11 -c \"import sys; sys.exit(4)\""],
    )

    result = patching.apply_patch_proposal(
        proposal,
        new_content,
        override_chamber=True,
        actor="admin-test",
    )

    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    gate = chamber_gate.get_gate_for_patch(proposal.id)
    assert gate is not None
    assert gate["status"] == "overridden"
    assert gate["override"]["actor"] == "admin-test"


def test_chamber_override_can_be_disabled_from_settings(tmp_path, monkeypatch):
    proposal, target, new_content = _proposal(
        tmp_path,
        monkeypatch,
        commands=["python3.11 -c \"import sys; sys.exit(4)\""],
    )
    monkeypatch.setattr(patching.alos_config, "allow_chamber_override", False)

    result = patching.apply_patch_proposal(
        proposal,
        new_content,
        override_chamber=True,
        actor="admin-test",
    )

    assert result["status"] == "blocked"
    assert "override is disabled" in result["message"]
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_chamber_gate_requirement_can_be_disabled_from_settings(tmp_path, monkeypatch):
    proposal, target, new_content = _proposal(
        tmp_path,
        monkeypatch,
        commands=["python3.11 -c \"import sys; sys.exit(4)\""],
    )
    monkeypatch.setattr(patching.alos_config, "chamber_gate_required", False)

    result = patching.apply_patch_proposal(proposal, new_content)

    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
