#!/bin/bash
# ALOS Sandbox Test Checklist — Proprietary (No Docker)
# Usage: bash run_alos_chamber_checklist.sh
# Exit code 0 = all tests passed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_MGR="$SCRIPT_DIR/chamber_manager.py"
PASS=0
FAIL=0
RESULTS=()

run_test() {
    local name="$1"
    local cmd="$2"
    local expected_exit="${3:-0}"
    echo -n "  [$name] ... "
    if eval "$cmd" > /tmp/alos_chamber_test_output 2>&1; then
        actual_exit=0
    else
        actual_exit=$?
    fi
    if [ "$actual_exit" -eq "$expected_exit" ]; then
        echo "PASS"
        PASS=$((PASS + 1))
        RESULTS+=("PASS: $name")
    else
        echo "FAIL (expected exit $expected_exit, got $actual_exit)"
        echo "Output: $(cat /tmp/alos_chamber_test_output)"
        FAIL=$((FAIL + 1))
        RESULTS+=("FAIL: $name")
    fi
}

echo "=== ALOS Sandbox Test Checklist (Proprietary — No Docker) ==="
echo ""

# Test 1: Python available
run_test "python_available" "python3 --version > /dev/null 2>&1"

# Test 2: Python alos_chamber echo
run_test "python_echo" "python3 '$SANDBOX_MGR' run python --command 'python -c \"print(\\\"hello_python\\\")\"'"

# Test 3: Node available
run_test "node_available" "node --version > /dev/null 2>&1"

# Test 4: Node alos_chamber echo
run_test "node_echo" "python3 '$SANDBOX_MGR' run node --command 'node -e \"console.log(\\\"hello_node\\\")\"'"

# Test 5: List alos_chamberes
run_test "list_alos_chamberes" "python3 '$SANDBOX_MGR' list"

# Test 6: Invalid stack returns exit 1
run_test "invalid_stack_fails" "python3 '$SANDBOX_MGR' run invalid_stack" "1"

echo ""
echo "=== Results: $PASS passed, $FAIL failed out of 6 tests ==="
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo ""
[ "$FAIL" -eq 0 ]
