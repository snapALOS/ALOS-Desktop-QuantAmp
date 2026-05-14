import pytest
from pathlib import Path
from src.runtime.mutation import mutation_gate

def test_approve_does_not_write_by_default(tmp_path, monkeypatch):
    """
    Item 7 Verification: Split approve/execute.
    Propose -> Approve -> Content should NOT change until Execute.
    """
    test_file = tmp_path / "gate_test.txt"
    test_file.write_text("original", encoding="utf-8")
    
    # Propose
    mutation_id = mutation_gate.propose(str(test_file), "mutated", "Gate test")
    
    # Approve
    status = mutation_gate.approve(mutation_id)
    assert status is True
    assert mutation_gate.get_proposal(mutation_id).status == "approved"
    
    # Assert target file is UNCHANGED after approve
    assert test_file.read_text(encoding="utf-8") == "original"
    
    # Run Execute
    exec_status = mutation_gate.execute(mutation_id)
    assert exec_status is True
    assert test_file.read_text(encoding="utf-8") == "mutated"

def test_write_trusted_executes_immediately(tmp_path):
    """
    Item 7 Verification: Trusted write fast path.
    Should handle backup + write in one go.
    """
    test_file = tmp_path / "trusted_test.txt"
    test_file.write_text("v1", encoding="utf-8")
    
    # Trusted write
    mutation_id = mutation_gate.write_trusted(str(test_file), "v2", "Trusted test")
    
    # Assert immediate change
    assert test_file.read_text(encoding="utf-8") == "v2"
    
    # Assert backup exists
    proposal = mutation_gate.get_proposal(mutation_id)
    assert proposal.backup_path is not None
    assert Path(proposal.backup_path).exists()
    assert Path(proposal.backup_path).read_text(encoding="utf-8") == "v1"
