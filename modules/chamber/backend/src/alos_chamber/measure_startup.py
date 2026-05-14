#!/usr/bin/env python3
"""
Measure alos_chamber startup times for Python and Node stacks.
"""
import subprocess
import time
import statistics

def measure_stack(stack: str, command: str, runs: int = 5) -> dict:
    """Measure startup time for a given stack."""
    times = []
    
    for i in range(runs):
        start = time.time()
        result = subprocess.run([
            'python3', 'alos_chamber_manager.py', 'run', stack, '--command', command
        ], capture_output=True, text=True, cwd='/home/quantamp/.openclaw/workspace/upgrade/alos_chamber')
        end = time.time()
        
        if result.returncode == 0:
            elapsed = end - start
            times.append(elapsed)
            print(f"  Run {i+1}: {elapsed:.3f}s")
        else:
            print(f"  Run {i+1}: FAILED - {result.stderr}")
    
    if times:
        return {
            'times': times,
            'avg': statistics.mean(times),
            'min': min(times),
            'max': max(times),
            'std': statistics.stdev(times) if len(times) > 1 else 0
        }
    else:
        return {'times': [], 'avg': 0, 'min': 0, 'max': 0, 'std': 0}

def main():
    print("Measuring alos_chamber startup times...")
    print("=" * 50)
    
    # Test Python stack
    print("\nPython Stack:")
    python_result = measure_stack('python', 'python -c "print(\\"hello\\")"', runs=5)
    
    # Test Node stack  
    print("\nNode Stack:")
    node_result = measure_stack('node', 'node -e "console.log(\\"hello\\")"', runs=5)
    
    print("\n" + "=" * 50)
    print("RESULTS:")
    print(f"Python - Avg: {python_result['avg']:.3f}s, Min: {python_result['min']:.3f}s, Max: {python_result['max']:.3f}s")
    print(f"Node   - Avg: {node_result['avg']:.3f}s, Min: {node_result['min']:.3f}s, Max: {node_result['max']:.3f}s")
    
    # Check if meets target (<5 seconds)
    python_meets = python_result['avg'] < 5.0
    node_meets = node_result['avg'] < 5.0
    
    print(f"\nTarget (<5s):")
    print(f"Python: {'PASS' if python_meets else 'FAIL'} ({python_result['avg']:.3f}s)")
    print(f"Node:   {'PASS' if node_meets else 'FAIL'} ({node_result['avg']:.3f}s)")
    
    return 0 if (python_meets and node_meets) else 1

if __name__ == '__main__':
    exit(main())