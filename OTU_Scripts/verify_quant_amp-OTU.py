import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

try:
    import numpy as np
    print(f"Numpy version: {np.__version__}")
except ImportError:
    print("Numpy not found! Need to install it.")
    sys.exit(1)

from src.memory.quant_amp import QuantAmpAtomizer, QIP, QuantumCollapse
from src.alos_core.doctrine import UniversalAtom

def test_quant_amp():
    content = "def test_func():\n    print('hello world')\n    import os\n"
    deps = ["os"]
    
    print("Testing Atomizer...")
    atom = QuantAmpAtomizer.atomize(content, deps=deps)
    print(f"Atom UUID: {atom.uuid}")
    print(f"Atom Vector (first 5): {atom.vector[:5]}")
    
    print("\nTesting QIP...")
    pulse = QIP.synthesize_pulse(atom)
    print(f"Pulse (first 5): {pulse[:5]}")
    
    print("\nTesting QVQ...")
    sig = QuantumCollapse.encode(pulse)
    print(f"Signature (hex, first 20): {sig.hex()[:20]}")
    
    print("\nTesting Hamming Distance...")
    sig2 = QuantumCollapse.encode([p * 0.9 for p in pulse]) # slightly different
    dist = QuantumCollapse.hamming_distance(sig, sig2)
    print(f"Hamming distance: {dist}")
    
    print("\nSUCCESS: All algorithms functional.")

if __name__ == "__main__":
    test_quant_amp()
