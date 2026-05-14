import uuid
import json
import math
import numpy as np
from typing import List, Optional, Dict, Any, Union
from src.core.quant_amp.doctrine import UniversalAtom

class QuantAmpAtomizer:
    @staticmethod
    def generate_state_vector(exports_count: int, deps_count: int, complexity: int) -> List[complex]:
        """
        [CLAIM 1 & 2] Pure Math Implementation.
        Maps code features to a unit vector in a complex Hilbert Space (C^1024).
        """
        # [CLAIM 1] Hilbert Space Projection (Magnitudes)
        mag_exports = float(exports_count)
        mag_deps = float(deps_count)
        
        # [CLAIM 2] Phase Coherence (Internal Pressure/Rotation)
        phase = (complexity % 360) * (np.pi / 180.0)
        
        # Construct the Base Feature Vector (3-Dimensional Seed)
        vec = np.array([
            mag_exports + 0j,
            mag_deps + 0j,
            np.exp(1j * phase) * complexity
        ])
        
        # Project to Hilbert Space C^1024 (Padding as per Protocol)
        if len(vec) < 1024:
            vec = np.pad(vec, (0, 1024 - len(vec)), 'constant')
            
        # Normalization (Purity)
        unit_vec = vec / (np.linalg.norm(vec) + 1e-9)
        return unit_vec.tolist()

    @staticmethod
    def atomize(logic_content: str, deps: List[str] = None, correlation_id: str = "GLOBAL") -> UniversalAtom:
        """
        [FACTORY METHOD] [ALG 1 COMPLIANCE]
        Converts raw logic into a UniversalAtom object.
        """
        if deps is None: deps = []
        
        # Feature Extraction
        exports_count = logic_content.count("def ") + logic_content.count("class ")
        deps_count = len(deps)
        complexity = len(logic_content) // 10 # heuristic
        
        # [INTEGRATION] Call the Pure Math Function (Alg 2 Core)
        vector_complex = QuantAmpAtomizer.generate_state_vector(exports_count, deps_count, complexity)
        
        # We store the real parts/magnitudes for standard vector stores if needed, 
        # but the doctrine specifies the complex vector.
        # For simplicity in storage, we might store the absolute magnitudes.
        vector_float = [abs(c) for c in vector_complex]
        
        return UniversalAtom(
            uuid=str(uuid.uuid4()),
            correlation_id=correlation_id,
            logic_content=logic_content,
            vector=vector_float,
            deps=deps,
            signature=None 
        )

class QIP:
    """
    [CLAIM 1] Unified Pulse Synthesis.
    Applies Doctrine-defined weights to generate a 'Logic Pulse'.
    """
    WEIGHT_COMPLEXITY = 1.0
    WEIGHT_DENSITY = 0.8
    WEIGHT_PHASE = 1.2 # High priority for structural intent

    @staticmethod
    def synthesize_pulse(atom: UniversalAtom, aps_weights: Optional[Dict[str, float]] = None) -> List[float]:
        raw_vec = np.array(atom.vector)
        
        # Determine Weights
        # Using a fixed mapping for now; in full APS this would be dynamic
        w_phase = QIP.WEIGHT_PHASE
        if aps_weights and "aps_weight_phase" in aps_weights:
            w_phase = aps_weights["aps_weight_phase"]
        
        pulse_vector = raw_vec * w_phase 
        return pulse_vector.tolist()

class QuantumCollapse:
    """
    QVQ (Quantum Vector Quantization) Engine.
    Collapses high-dimensional embeddings into high-density 1024-bit logic signatures.
    """

    @staticmethod
    def encode(vector: Union[List[float], np.ndarray], precision: str = "BALANCED") -> bytes:
        if isinstance(vector, list): vector = np.array(vector)
        if len(vector) > 1024: vector = vector[:1024]
        elif len(vector) < 1024: vector = np.pad(vector, (0, 1024 - len(vector)), 'constant')
        
        # [CLAIM 2] Bit-Density Stabilizer (Maximum Entropy)
        stabilizer_B = np.median(np.real(vector))
        
        # [CLAIM 1] Topology-Preserving Projection
        bits = (np.real(vector) > stabilizer_B).astype(int)
        
        if precision == "SHALLOW": return np.packbits(bits[:6]).tobytes() 
        elif precision == "BALANCED": return np.packbits(bits[:128]).tobytes() 
        else: return np.packbits(bits).tobytes()

    @staticmethod
    def hamming_distance(sig1: bytes, sig2: bytes) -> int:
        arr1 = np.frombuffer(sig1, dtype=np.uint8)
        arr2 = np.frombuffer(sig2, dtype=np.uint8)
        # Ensure equal length
        min_len = min(len(arr1), len(arr2))
        diff = np.bitwise_xor(arr1[:min_len], arr2[:min_len])
        return int(np.unpackbits(diff).sum())
