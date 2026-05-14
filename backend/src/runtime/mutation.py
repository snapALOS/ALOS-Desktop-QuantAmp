import uuid
import os
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from src.core.config import system_logger

@dataclass
class MutationProposal:
    id: str
    file_path: str
    proposed_content: str
    explanation: str
    status: str = "pending" # pending, approved, rejected, executed
    backup_path: Optional[str] = None

class MutationManager:
    """
    Project QuantAmp: Mutation Manager (Hard Gate).
    Separates logical proposals from physical filesystem mutations.
    """
    def __init__(self):
        self._proposals: Dict[str, MutationProposal] = {}

    def propose(self, file_path: str, proposed_content: str, explanation: str) -> str:
        """
        [CLAIM 1] Create a logical proposal for a filesystem change.
        """
        mutation_id = str(uuid.uuid4())[:8]
        proposal = MutationProposal(
            id=mutation_id,
            file_path=file_path,
            proposed_content=proposed_content,
            explanation=explanation
        )
        self._proposals[mutation_id] = proposal
        system_logger.info(f"MUTATION PROPOSED: [{mutation_id}] target={file_path}")
        return mutation_id

    def approve(self, mutation_id: str) -> bool:
        """
        [CLAIM 2] Approve a proposal, allowing it to be executed.
        Does NOT execute by default (V4 Fix).
        """
        if mutation_id in self._proposals:
            self._proposals[mutation_id].status = "approved"
            system_logger.info(f"MUTATION APPROVED: [{mutation_id}]")
            return True
        return False

    def write_trusted(self, file_path: str, proposed_content: str, explanation: str) -> str:
        """
        [V4 Fix 7a] Trusted-write fast path for shell-owned system files.
        Handles atomic write + backup but skips the manual approve ceremony.
        """
        mutation_id = self.propose(file_path, proposed_content, f"[TRUSTED] {explanation}")
        self._proposals[mutation_id].status = "approved"
        success = self.execute(mutation_id)
        if not success:
             raise RuntimeError(f"Trusted write failed for {file_path}. Check logs.")
        return mutation_id

    def execute(self, mutation_id: str) -> bool:
        """
        [HARD GATE] Physical write to disk.
        Only executes if the proposal is approved.
        """
        proposal = self._proposals.get(mutation_id)
        if not proposal or proposal.status != "approved":
            system_logger.error(f"MUTATION DENIED: [{mutation_id}] status is {proposal.status if proposal else 'NOT_FOUND'}")
            return False

        try:
            target = Path(proposal.file_path)
            # 1. Create backup
            if target.exists():
                backup_path = target.with_suffix(target.suffix + f".alos_bak_{mutation_id}")
                shutil.copy2(target, backup_path)
                proposal.backup_path = str(backup_path)
            
            # 2. Atomic Write (Tmp + Replace)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target.with_suffix(target.suffix + ".mutation_tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(proposal.proposed_content)
            
            os.replace(tmp_path, target)
            
            proposal.status = "executed"
            system_logger.info(f"MUTATION EXECUTED: [{mutation_id}] successfully updated {proposal.file_path}")
            return True
        except Exception as e:
            system_logger.error(f"MUTATION FAILED: [{mutation_id}] error: {e}")
            return False

    def get_proposal(self, mutation_id: str) -> Optional[MutationProposal]:
        return self._proposals.get(mutation_id)

# Singleton Instance for system-wide gate
mutation_gate = MutationManager()
