#!/usr/bin/env python3
"""
Measure baseline alos_chamber startup times for python and node stacks.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

SANDBOX_MGR = Path(__file__).parent / "alos_chamber_manager.py"

def measure_startup_time(stack: str, command: str = None) -> float:
    """Measure the time to start a alos_chamber and run a command."""
    if not command:
        if stack == "python":
            command = "python -c \"print('hello')\""
        elif stack == "node":
            command = "node -e \"console.log('hello')\""
    
    start_time = time.time()
    
    # Run the alos_chamber command
    result = subprocess.run([
        sys.executable, str(SANDBOX_MGR), "run", stack, "--command", command
    ], capture_output=True, text=True, cwd=Path(__file__).parent)
    
    end_time = time.time()
    
    if result.returncode != 0:
        print(f"Error running {stack} alos_chamber: {result.stderr}")
        return None
        
    try:
        output = json.loads(result.stdout)
        if not output.get("success", False):
            print(f"Sandbox failed: {output.get('output', 'Unknown error')}")
            return None
    except json.JSONDecodeError:
        print(f"Invalid JSON output: {result.stdout}")
        return None
    
    return end_time - start_time

def main():
    print("Measuring alos_chamber startup baseline times...")
    print("=" * 50)
    
    # Test Python stack
    python_time = measure_startup_time("python")
    if python_time is not None:
        print(f"Python stack startup time: {python_time:.3f} seconds")
    else:
        print("Python stack measurement failed")
    
    # Test Node stack
    node_time = measure_startup_time("node")
    if node_time is not None:
        print(f"Node stack startup time: {node_time:.3f} seconds")
    else:
        print("Node stack measurement failed")
    
    print("=" * 50)
    print("Target: <5 seconds for both stacks")
    
    if python_time is not None and python_time < 5.0:
        print("✓ Python stack meets target (<5s)")
    elif python_time is not None:
        print(f"✗ Python stack exceeds target ({python_time:.3f}s >= 5s)")
        
    if node_time is not None and node_time < 5.0:
        print("✓ Node stack meets target (<5s)")
    elif node_time is not None:
        print(f"✗ Node stack exceeds target ({node_time:.3f}s >= 5s)")

if __name__ == "__main__":
    main()