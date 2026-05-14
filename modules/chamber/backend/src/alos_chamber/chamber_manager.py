#!/usr/bin/env python3
"""
alos_chamber_manager.py — ALOS Proprietary Sandbox Manager

100% proprietary isolation layer. No Docker dependency.
Uses Python venv and subprocess isolation for Python stack.
Uses system Node.js with isolated working directories for Node stack.
Uses Node.js with React Native tooling for Android stack.

Customers get a working alos_chamber with zero additional installs beyond
what OpenClaw already requires (Python 3.10+ and Node.js).

Usage:
    python3 alos_chamber_manager.py run python --command "python script.py"
    python3 alos_chamber_manager.py run node --command "node index.js"
    python3 alos_chamber_manager.py run android --command "npx react-native info"
    python3 alos_chamber_manager.py list
    python3 alos_chamber_manager.py stop <session_id>
"""

import functools
import json
import os
try:
    import resource
except ImportError:
    # Windows compatibility
    resource = None
import shutil
import signal
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"
SANDBOX_ROOT = Path.home() / ".alos" / "chamber"
SESSIONS_FILE = SANDBOX_ROOT / ".sessions.json"

@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """Load stack configuration from config.json (Lazy)."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_container_prefix() -> str:
    return get_config().get("container_prefix", "alos_chamber_session")

def get_max_concurrent() -> int:
    return get_config().get("max_concurrent_containers", 3)

def get_default_timeout() -> int:
    return get_config().get("default_timeout_seconds", 300)

# Initialize base venv for Python stack on module load
def _init_base_venv():
    """Initialize the base Python venv template for faster alos_chamber startup."""
    base_venv = SANDBOX_ROOT / "python" / "_base_venv"
    if not base_venv.exists():
        base_venv.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        import sys
        subprocess.run(
            [sys.executable, "-m", "venv", str(base_venv)],
            capture_output=True, timeout=30
        )
        # Install common packages in base venv
        pip_base = base_venv / "bin" / "pip"
        subprocess.run(
            [str(pip_base), "install", "--upgrade", "pip"],
            capture_output=True, timeout=30
        )

# Initialize base venv when module loads
# REDACTED: _init_base_venv() no longer called at import time to prevent boot slowdown
# _init_base_venv()

# ── Session tracking ──────────────────────────────────────────────────────────
def load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text())
        except Exception:
            pass
    return {}

def save_sessions(sessions: dict):
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))

def register_session(session_id: str, stack: str, workdir: str, pid: int = None):
    sessions = load_sessions()
    sessions[session_id] = {
        "stack": stack,
        "workdir": workdir,
        "pid": pid,
        "started_at": time.time()
    }
    save_sessions(sessions)

def remove_session(session_id: str):
    sessions = load_sessions()
    sessions.pop(session_id, None)
    save_sessions(sessions)

# ── Sandbox implementations ───────────────────────────────────────────────────

def run_python_alos_chamber(command: str, workdir: Path, timeout: int) -> dict:
    """
    Run a command in an isolated Python environment.
    Uses a pre-created base venv with common packages for faster startup.
    """
    # Use a shared base venv template for faster startup
    base_venv = SANDBOX_ROOT / "python" / "_base_venv"
    venv_dir = workdir / ".venv"

    # Create base venv if it doesn't exist (runs once)
    if not base_venv.exists():
        base_venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "venv", str(base_venv)],
            capture_output=True, timeout=30
        )
        # Install common packages in base venv
        pip_base = base_venv / "bin" / "pip"
        subprocess.run(
            [str(pip_base), "install", "--upgrade", "pip"],
            capture_output=True, timeout=30
        )

    # Copy base venv to working directory (much faster than creating from scratch)
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    shutil.copytree(base_venv, venv_dir)

    python_bin = venv_dir / "bin" / "python"
    pip_bin = venv_dir / "bin" / "pip"

    # Build the actual command — if it starts with "python", replace with venv python
    if command.startswith("python ") or command == "python":
        actual_cmd = command.replace("python", shlex.quote(str(python_bin)), 1)
    elif command.startswith("pip "):
        actual_cmd = command.replace("pip", shlex.quote(str(pip_bin)), 1)
    else:
        actual_cmd = command

    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["PATH"] = str(venv_dir / "bin") + ":" + env.get("PATH", "")
    env["HOME"] = str(workdir)
    env["PYTHONPATH"] = str(workdir)
    # Remove any existing PYTHONHOME that could interfere
    env.pop("PYTHONHOME", None)

    try:
        result = subprocess.run(
            actual_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            env=env
        )
        output = result.stdout + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": f"Command timed out after {timeout}s", "exit_code": 124}
    except Exception as e:
        return {"success": False, "output": str(e), "exit_code": 1}


def run_node_alos_chamber(command: str, workdir: Path, timeout: int) -> dict:
    """
    Run a command in an isolated Node.js environment.
    Uses a fresh working directory with its own node_modules.
    """
    # Find node binary
    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm")
    npx_bin = shutil.which("npx")

    if not node_bin:
        return {
            "success": False,
            "output": "Node.js not found. Install Node.js to use the node alos_chamber.",
            "exit_code": 1
        }

    # Replace bare commands with full paths
    actual_cmd = command
    if command.startswith("node ") or command == "node":
        actual_cmd = command.replace("node", shlex.quote(node_bin), 1)
    elif command.startswith("npm ") and npm_bin:
        actual_cmd = command.replace("npm", shlex.quote(npm_bin), 1)
    elif command.startswith("npx ") and npx_bin:
        actual_cmd = command.replace("npx", shlex.quote(npx_bin), 1)

    env = os.environ.copy()
    env["HOME"] = str(workdir)
    env["NPM_CONFIG_PREFIX"] = str(workdir / ".npm-global")
    env["PATH"] = str(workdir / ".npm-global" / "bin") + ":" + env.get("PATH", "")

    try:
        result = subprocess.run(
            actual_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            env=env
        )
        output = result.stdout + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": f"Command timed out after {timeout}s", "exit_code": 124}
    except Exception as e:
        return {"success": False, "output": str(e), "exit_code": 1}


def run_android_alos_chamber(command: str, workdir: Path, timeout: int) -> dict:
    """
    Run a command in an Android/React Native isolated environment.
    Uses Node.js with React Native CLI tools in an isolated working directory.
    """
    # Android alos_chamber uses same Node isolation but with RN-specific env vars
    node_bin = shutil.which("node")
    if not node_bin:
        return {
            "success": False,
            "output": "Node.js not found. Required for Android/React Native alos_chamber.",
            "exit_code": 1
        }

    env = os.environ.copy()
    env["HOME"] = str(workdir)
    env["NPM_CONFIG_PREFIX"] = str(workdir / ".npm-global")
    env["PATH"] = str(workdir / ".npm-global" / "bin") + ":" + env.get("PATH", "")
    env["REACT_NATIVE_SKIP_BUNDLER"] = "1"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            env=env
        )
        output = result.stdout + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": f"Command timed out after {timeout}s", "exit_code": 124}
    except Exception as e:
        return {"success": False, "output": str(e), "exit_code": 1}


# ── Primary public function ───────────────────────────────────────────────────

def run_alos_chamber(stack: str, command: str = None, interactive: bool = False) -> dict:
    """
    Launch a alos_chamber and optionally run a command inside it.

    Args:
        stack: One of "python", "node", "android"
        command: Command to run inside the alos_chamber. If None, runs a health check.
        interactive: Not used in proprietary mode — kept for API compatibility.

    Returns:
        {
            "success": bool,
            "output": str,
            "container_id": str,   # session ID (replaces Docker container ID)
            "exit_code": int
        }
    """
    valid_stacks = ["python", "node", "android"]
    if stack not in valid_stacks:
        return {
            "success": False,
            "output": f"Unknown stack: '{stack}'. Valid options: {valid_stacks}",
            "container_id": "",
            "exit_code": 1
        }

    # Resource check
    sessions = load_sessions()
    active = [s for s in sessions.values() if time.time() - s.get("started_at", 0) < get_default_timeout()]
    if len(active) >= get_max_concurrent():
        return {
            "success": False,
            "output": f"Max concurrent alos_chambers ({get_max_concurrent()}) reached. Stop one first.",
            "container_id": "",
            "exit_code": 1
        }

    # Create isolated temp working directory
    session_id = f"{get_container_prefix()}_{stack}_{uuid.uuid4().hex[:8]}"
    stack_mount = SANDBOX_ROOT / stack
    workdir = stack_mount / session_id
    workdir.mkdir(parents=True, exist_ok=True)

    register_session(session_id, stack, str(workdir))

    # [PATCH] Lazy-initialize base venv on first demand
    if stack == "python":
        _init_base_venv()

    # Default command if none provided
    if not command:
        command = {
            "python": f"{sys.executable} --version",
            "node": "node --version",
            "android": "node --version"
        }.get(stack, "echo 'Sandbox ready'")

    timeout = get_config().get("default_timeout_seconds", get_default_timeout())

    try:
        if stack == "python":
            result = run_python_alos_chamber(command, workdir, timeout)
        elif stack == "node":
            result = run_node_alos_chamber(command, workdir, timeout)
        elif stack == "android":
            result = run_android_alos_chamber(command, workdir, timeout)
        else:
            result = {"success": False, "output": "Unknown stack", "exit_code": 1}

        result["container_id"] = session_id
        return result

    finally:
        # Clean up working directory
        try:
            shutil.rmtree(str(workdir), ignore_errors=True)
        except Exception:
            pass
        remove_session(session_id)


def list_active_alos_chambers() -> list:
    """Return list of currently active alos_chamber sessions."""
    sessions = load_sessions()
    now = time.time()
    active = []
    for session_id, info in sessions.items():
        age = now - info.get("started_at", now)
        if age < get_default_timeout():
            active.append({
                "id": session_id,
                "name": session_id,
                "status": "running",
                "stack": info.get("stack"),
                "age_seconds": round(age)
            })
    return active


def commit_to_workspace(session_id: str, relative_path: str, workspace_root: str) -> dict:
    """
    Commit a file from the alos_chamber to the workspace.
    Creates a .bak backup of the original file if it exists.
    """
    sessions = load_sessions()
    if session_id not in sessions:
        return {"success": False, "error": f"Session {session_id} not found."}
    
    session_dir = Path(sessions[session_id]["workdir"])
    source_file = session_dir / relative_path
    target_file = Path(workspace_root) / relative_path

    if not source_file.exists():
        return {"success": False, "error": f"Source file {relative_path} not found in chamber."}

    # Backup existing file
    if target_file.exists():
        backup_file = target_file.with_suffix(target_file.suffix + ".bak")
        try:
            shutil.copy2(target_file, backup_file)
        except Exception as e:
            return {"success": False, "error": f"Failed to create backup: {str(e)}"}

    # Commit change
    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        return {"success": True, "target": str(target_file), "backup": str(backup_file) if target_file.exists() else None}
    except Exception as e:
        return {"success": False, "error": f"Failed to commit file: {str(e)}"}


def stop_alos_chamber(container_id: str) -> bool:
    """Stop a alos_chamber session by ID."""
    sessions = load_sessions()
    if container_id in sessions:
        workdir = sessions[container_id].get("workdir")
        if workdir:
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass
        remove_session(container_id)
        return True
    return False


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    class SandboxArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            # Return exit code 1 instead of argparse default 2
            # so callers can reliably detect failure
            print(json.dumps({"success": False, "output": message, "container_id": "", "exit_code": 1}))
            sys.exit(1)

    parser = SandboxArgumentParser(description="ALOS Sandbox Manager (Proprietary — No Docker)")
    subparsers = parser.add_subparsers(dest="action")

    run_parser = subparsers.add_parser("run", help="Run a command in a alos_chamber")
    run_parser.add_argument("stack", choices=["python", "node", "android"])
    run_parser.add_argument("--command", "-c", default=None)
    run_parser.add_argument("--interactive", "-i", action="store_true")

    subparsers.add_parser("list", help="List active alos_chambers")

    stop_parser = subparsers.add_parser("stop", help="Stop a alos_chamber")
    stop_parser.add_argument("container_id")

    args = parser.parse_args()

    if args.action == "run":
        result = run_alos_chamber(args.stack, args.command, getattr(args, "interactive", False))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["success"] else 1)
    elif args.action == "list":
        print(json.dumps(list_active_alos_chambers(), indent=2))
    elif args.action == "stop":
        success = stop_alos_chamber(args.container_id)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
