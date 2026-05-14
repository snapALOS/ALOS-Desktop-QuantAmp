import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add the alos_chamber package to the path so we can import chamber_manager
sys.path.append(str(Path(__file__).parent.parent))

import alos_chamber.chamber_manager as manager

def mcp_response(result: Any) -> str:
    return json.dumps(result, indent=2)

def tool_create_chamber(stack: str) -> str:
    """Create a new isolated development chamber."""
    result = manager.run_alos_chamber(stack, command=None)
    return mcp_response(result)

def tool_run_command(session_id: str, command: str) -> str:
    """Run a command inside an active chamber session."""
    sessions = manager.load_sessions()
    if session_id not in sessions:
        return mcp_response({"success": False, "error": f"Session {session_id} not found."})
    
    info = sessions[session_id]
    stack = info["stack"]
    workdir = Path(info["workdir"])
    
    # Update logic from run_alos_chamber but for an existing session
    timeout = manager.config.get("default_timeout_seconds", 300)
    
    if stack == "python":
        result = manager.run_python_alos_chamber(command, workdir, timeout)
    elif stack == "node":
        result = manager.run_node_alos_chamber(command, workdir, timeout)
    elif stack == "android":
        result = manager.run_android_alos_chamber(command, workdir, timeout)
    else:
        result = {"success": False, "error": "Unknown stack"}
    
    result["session_id"] = session_id
    return mcp_response(result)

def tool_read_file(session_id: str, relative_path: str) -> str:
    """Read a file from a chamber session."""
    sessions = manager.load_sessions()
    if session_id not in sessions:
        return mcp_response({"success": False, "error": f"Session {session_id} not found."})
    
    workdir = Path(sessions[session_id]["workdir"])
    file_path = workdir / relative_path
    
    if not file_path.exists():
        return mcp_response({"success": False, "error": f"File {relative_path} not found."})
    
    try:
        content = file_path.read_text()
        return mcp_response({"success": True, "content": content})
    except Exception as e:
        return mcp_response({"success": False, "error": str(e)})

def tool_write_file(session_id: str, relative_path: str, content: str) -> str:
    """Write a file into a chamber session."""
    sessions = manager.load_sessions()
    if session_id not in sessions:
        return mcp_response({"success": False, "error": f"Session {session_id} not found."})
    
    workdir = Path(sessions[session_id]["workdir"])
    file_path = workdir / relative_path
    
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return mcp_response({"success": True, "path": relative_path})
    except Exception as e:
        return mcp_response({"success": False, "error": str(e)})

def tool_list_chambers() -> str:
    """List all currently active chamber sessions."""
    return mcp_response({"chambers": manager.list_active_alos_chambers()})

def tool_stop_chamber(session_id: str) -> str:
    """Stop and cleanup a chamber session."""
    success = manager.stop_alos_chamber(session_id)
    return mcp_response({"success": success})

def tool_commit_to_workspace(session_id: str, relative_path: str, workspace_root: str) -> str:
    """
    Commit a verified file from the chamber to the primary workspace.
    A .bak backup of the original workspace file will be created.
    """
    result = manager.commit_to_workspace(session_id, relative_path, workspace_root)
    return mcp_response(result)

def main():
    # Basic JSON-RPC loop for stdio MCP
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            params = request.get("params", {})
            req_id = request.get("id")
            
            if method == "create_chamber":
                result = tool_create_chamber(params.get("stack", "python"))
            elif method == "run_command":
                result = tool_run_command(params.get("session_id"), params.get("command"))
            elif method == "read_file":
                result = tool_read_file(params.get("session_id"), params.get("relative_path"))
            elif method == "write_file":
                result = tool_write_file(params.get("session_id"), params.get("relative_path"), params.get("content"))
            elif method == "list_chambers":
                result = tool_list_chambers()
            elif method == "stop_chamber":
                result = tool_stop_chamber(params.get("session_id"))
            elif method == "commit_to_workspace":
                result = tool_commit_to_workspace(params.get("session_id"), params.get("relative_path"), params.get("workspace_root"))
            else:
                result = json.dumps({"error": "Method not found"})
                
            print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": str(e)}))
            sys.stdout.flush()

if __name__ == "__main__":
    main()
