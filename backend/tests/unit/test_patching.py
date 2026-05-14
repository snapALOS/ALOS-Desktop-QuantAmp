import pytest
from pathlib import Path
from src.tools.patching import build_patch_proposal, apply_patch_proposal, save_patch_proposal
from src.runtime.mutation import mutation_gate

def test_apply_patch_proposal_success_returns_dict(tmp_path, monkeypatch):
    """
    Item 2 Verification: Minimal happy-path for patch application.
    Checks that the returned dict has the correct keys and no NameError occurs.
    """
    # 1. Setup a dummy file
    root = tmp_path.resolve()
    test_file = root / "test_fix.txt"
    test_file.write_text("line1\nline2\n", encoding="utf-8")
    
    # Mock _relative_path to avoid macOS /private/var symlink issues in tests
    monkeypatch.setattr("src.tools.patching._relative_path", lambda p: p.name)
    
    # 2. Build proposal
    new_content = "line1\nline2\nline3\n"
    # We must use a path relative to root
    rel_path = "test_fix.txt"
    
    # [QUANTAMP INTEGRATION] We need a mutation_id
    mutation_id = mutation_gate.propose(str(test_file), new_content, "Fix test")
    
    proposal = build_patch_proposal(rel_path, new_content, "Add line 3")
    proposal.mutation_id = mutation_id
    # 3. Save the proposal (status: pending)
    save_patch_proposal(proposal)
    
    # 4. Apply (This should now trigger execute() internally)
    result = apply_patch_proposal(proposal, new_content)
    
    # 5. Assertions
    assert isinstance(result, dict)
    assert result["status"] == "applied"
    assert "file" in result
    assert "after_hash" in result
    assert "backup" not in result # Verified we dropped the key
    
    # Confirm file content changed
    assert test_file.read_text(encoding="utf-8") == new_content
