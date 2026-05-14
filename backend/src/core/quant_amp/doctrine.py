import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

class QuantAmpDoctrine:
    """
    [GLOBAL CONTRACT]
    Defines the immutable keys and constants for inter-algorithm communication.
    Ensures 100% compliance between independent facets (e.g. Alg 3 & Alg 5).
    """
    # APS (Algorithm 5) Keys
    APS_KEY_PHASE_WEIGHT = "aps_weight_phase"
    APS_KEY_DENSITY_WEIGHT = "aps_weight_density"
    APS_KEY_COMPLEXITY_WEIGHT = "aps_weight_complexity"

@dataclass
class UniversalAtom:
    """
    [CLAIM 1] The Universal Data Structure.
    Standardized container for all logic, irrespective of source language.
    """
    uuid: str                       # Unique ID
    correlation_id: str             # Global Context Anchor (Claim 2)
    logic_content: str              # The actual code/logic
    vector: List[float]             # Hilbert Space Projection (Alg 2)
    deps: List[str]                 # Dependencies (Alg 2)
    signature: Optional[str] = None # QVQ Signature (Alg 4) - Hex encoded
    metadata: Dict[str, Any] = field(default_factory=dict) # Standard Logic Lexicon (SLL) and other metadata

    def to_qasir(self) -> str:
        """
        [ALG 6 INTEGRATION] 
        Serializes atom to QA-SIR Universal Unilanguage format.
        This ties Alg 1 (Protocol) to Alg 6 (Standard).
        """
        return (
            f"!QUANTUM-LOGIC ATOM\n"
            f"UUID: {self.uuid}\n"
            f"CORRELATION: {self.correlation_id}\n"
            f"VECTOR: {str(self.vector[:5])}... (truncated)\n"
            f"CONTENT:\n{self.logic_content}"
        )

class AtomicManager:
    """
    The Atomic Method Protocol (AMP) Manager.
    Handles stateful, iterative processing for large-scale data transfers and file generation.
    """
    
    TOKEN_THRESHOLD = 750  
    CHAR_THRESHOLD = 3000 
    
    @staticmethod
    def generate_correlation_id() -> str:
        return f"amp_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def needs_atomic_treatment(task: str, projected_size: Optional[int] = None) -> bool:
        triggers = [
            "full codebase", "all files", "complete documentation", 
            "comprehensive", "entire system", "complete backend",
            "implementation plan", "detailed architecture",
            "quantum", "coherence", "superposition", "collapse"
        ]
        if any(t in task.lower() for t in triggers): return True
        if projected_size and projected_size > AtomicManager.CHAR_THRESHOLD: return True
        if len(task.split()) > 300: return True
        return False

    @staticmethod
    def create_atomic_task(segment: str, current: int, total: int, correlation_id: str, running_context: str = "") -> str:
        return (
            f"--- ATOMIC METHOD PROTOCOL (AMP) ---\n"
            f"CORRELATION_ID: {correlation_id}\n"
            f"SEGMENT: {current} OF {total}\n\n"
            f"PREVIOUS CONTEXT (STITCHED):\n{running_context}\n\n"
            f"CURRENT TASK SEGMENT:\n{segment}\n\n"
            f"INSTRUCTION: Execute ONLY the task segment above. MAINTAIN continuity with previous context. "
            f"DO NOT repeat code from previous segments unless explicitly required for integration."
        )

    @staticmethod
    def assemble_results(segments: List[str], correlation_id: Optional[str] = None, separator: str = "") -> Dict[str, Any]:
        full_content = separator.join(segments)
        return {
            "content": full_content,
            "correlation_id": correlation_id,
            "segments": len(segments),
            "total_chars": len(full_content)
        }
