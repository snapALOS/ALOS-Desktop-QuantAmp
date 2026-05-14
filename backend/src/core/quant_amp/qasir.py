from typing import List, Dict, Any, Optional
from src.core.quant_amp.doctrine import UniversalAtom, QuantAmpDoctrine
from src.memory.quant_amp import QuantAmpAtomizer, QIP, QuantumCollapse

class QASIRCompiler:
    """
    Project QuantAmp: QA-SIR (Quantum-Aware Successive Instructional Retrieval) Compiler.
    The primary engine for compiling intent into high-fidelity logical atoms.
    """

    # SLL: Standard Logic Lexicon
    # Maps human/technical intent to QuantAmp internal metadata signatures.
    SLL_MAP = {
        "FIX": {"priority": 0.9, "entropy": 0.2, "logic_type": "correction"},
        "FEATURE": {"priority": 0.7, "entropy": 0.5, "logic_type": "expansion"},
        "REFACTOR": {"priority": 0.6, "entropy": 0.3, "logic_type": "optimization"},
        "AUDIT": {"priority": 0.8, "entropy": 0.1, "logic_type": "observation"},
        "CRITICAL": {"priority": 1.0, "entropy": 0.05, "logic_type": "emergency"},
    }

    @staticmethod
    def compile_intent(content: str, label: Optional[str] = None) -> UniversalAtom:
        """
        [CLAIM 1] Compiles raw content into a Universal Atom with SLL metadata.
        """
        sll_metadata = QASIRCompiler.SLL_MAP.get(label, {"priority": 0.5, "entropy": 0.5, "logic_type": "general"})
        
        # 1. Project into Complex Hilbert Space (Atomization)
        # Note: In a real implementation, we'd also pass dependencies
        atom = QuantAmpAtomizer.atomize(content)
        
        # 2. Enrich with SLL Logic Lexicon
        # [FIX] UniversalAtom now has metadata field
        atom.metadata.update(sll_metadata)
        
        # 3. Synthesize Logic Pulse (QIP)
        pulse = QIP.synthesize_pulse(atom)
        
        # 4. Binary Quantization (QVQ)
        signature_bytes = QuantumCollapse.encode(pulse)
        
        # [FIX] Store the signature as a hex string as expected by analyze_ripple
        atom.signature = signature_bytes.hex()
        
        return atom

    @staticmethod
    def analyze_ripple(atoms: List[UniversalAtom]) -> Dict[str, Any]:
        """
        [CLAIM 2] Successive Retrieval Analysis.
        Measures the resonance and convergence of a group of atoms.
        """
        if not atoms:
            return {"resonance": 0.0, "convergence": "NULL"}

        # Calculate average Hamming similarity as a measure of Logic Convergence
        total_similarity = 0.0
        comparisons = 0
        
        for i in range(len(atoms)):
            for j in range(i + 1, len(atoms)):
                if atoms[i].signature and atoms[j].signature:
                    sig1 = bytes.fromhex(atoms[i].signature)
                    sig2 = bytes.fromhex(atoms[j].signature)
                    hamming = QuantumCollapse.hamming_distance(sig1, sig2)
                    similarity = 1.0 - (hamming / 1024.0)
                    total_similarity += similarity
                    comparisons += 1
        
        avg_res = total_similarity / comparisons if comparisons > 0 else 1.0
        
        return {
            "resonance": round(avg_res, 4),
            "convergence": "STABLE" if avg_res > 0.85 else "TURBULENT" if avg_res < 0.5 else "FLOW",
            "atom_count": len(atoms)
        }

def get_qasir_compiler():
    return QASIRCompiler()
