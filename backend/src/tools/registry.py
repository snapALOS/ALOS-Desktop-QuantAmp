import sys
import os
import difflib
import subprocess
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from pathlib import Path
from typing import Any, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from src.core.config import ROOT_DIR, system_logger
from src.core.policy import (
    PolicyViolation,
    classify_file_write,
    command_policy,
    parse_command,
    resolve_workspace_path,
)
from src.tools.patching import apply_patch_proposal, propose_and_save_patch, public_patch_payload
from src.runtime.mutation import mutation_gate

# -------------------------------------------------------------------
# Input Validation Schemas
# -------------------------------------------------------------------
class PythonExecutionSchema(BaseModel):
    script_content: str = Field(..., description="The raw Python code string to execute locally.")
    timeout_seconds: int = Field(default=30, description="Hard timeout mapping preventing infinite loop hangs.")

class ReadDirSchema(BaseModel):
    directory_path: str = Field(default="./", description="Target path to list contents of. Defaults to workspace root.")

class ReadFileSchema(BaseModel):
    file_path: str = Field(..., description="Absolute or relative path of the file to read.")
    start_line: int = Field(default=1, description="Line number to start reading from (1-indexed).")
    end_line: Optional[int] = Field(default=None, description="Line number to halt reading. If null, reads up to 500 lines.")

class WriteFileSchema(BaseModel):
    file_path: str = Field(..., description="Absolute or relative path to the target file.")
    file_content: str = Field(..., description="The raw string content to dump into the file.")

class ProposePatchSchema(BaseModel):
    file_path: str = Field(..., description="Absolute or relative path to patch.")
    proposed_content: str = Field(..., description="Full proposed file content used to generate a verified diff.")
    rationale: str = Field(default="", description="Short reason for the change.")

class BashExecutionSchema(BaseModel):
    command: str = Field(..., description="The raw bash system command to execute (e.g., 'npm install', 'ls -la', 'python3 script.py').")
    timeout_seconds: int = Field(default=60, description="Rigorous timeout limit preventing hanging shell commands.")

class WebSearchSchema(BaseModel):
    query: str = Field(..., description="The string query to search directly across the internet. Be concise.")
    max_results: int = Field(default=3, description="Number of sequential search results to pull down.")

class ScoutQuerySchema(BaseModel):
    q: Optional[str] = Field(default=None, description="Text search across Scout source, level, event type, module, and message.")
    level: Optional[str] = Field(default=None, description="Optional exact level filter: info, warning, error, debug.")
    source: Optional[str] = Field(default=None, description="Optional exact source filter such as backend.log, backend.run, frontend.renderer.")
    module: Optional[str] = Field(default=None, description="Optional exact module/logger filter.")
    run_id: Optional[str] = Field(default=None, description="Optional run id filter.")
    session_id: Optional[str] = Field(default=None, description="Optional session id filter.")
    limit: int = Field(default=50, description="Maximum events to return, capped at 200.")

class ScrapeHTMLSchema(BaseModel):
    target_url: str = Field(..., description="Absolute URL string to scrape physical text data from.")

class GitRevertSchema(BaseModel):
    file_path: str = Field(..., description="Absolute or relative path to the specific file to reset via Git.")

# -------------------------------------------------------------------
# Guardrailed Physical Operations
# -------------------------------------------------------------------
@tool(args_schema=PythonExecutionSchema)
def execute_sandboxed_python(script_content: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Executes raw Python code natively utilizing subprocess constraints."""
    system_logger.info(f"Tool Requested: [execute_sandboxed_python] | Timeout constraints: {timeout_seconds}s")
    try:
        process = subprocess.run(
            [sys.executable, "-c", script_content],
            capture_output=True, text=True, timeout=timeout_seconds, cwd=str(ROOT_DIR)
        )
        return {
            "status": "success" if process.returncode == 0 else "failed",
            "returncode": process.returncode,
            "stdout": process.stdout[:2000],
            "stderr": process.stderr[:2000]
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout_failure", "stdout": "", "stderr": f"Execution mathematically halted beyond {timeout_seconds}s limit."}
    except Exception as e:
        return {"status": "critical_failure", "stdout": "", "stderr": str(e)}

@tool(args_schema=ReadDirSchema)
def read_local_directory(directory_path: str = "./") -> dict[str, Any]:
    """Reads specific directory structures and returns an itemized array of components."""
    system_logger.info(f"Tool Requested: [read_local_directory] | Target: {directory_path}")
    try:
        target = resolve_workspace_path(directory_path, must_exist=True)
        if not target.exists() or not target.is_dir():
            return {"status": "failed", "data": "Path is structurally missing."}
        items = [f"[{'DIR' if x.is_dir() else 'FILE'}] {x.name}" for x in target.iterdir()]
        return {"status": "success", "data": items[:200]}
    except Exception as e:
        return {"status": "failed", "data": str(e)}

@tool(args_schema=ReadFileSchema)
def read_file_content(file_path: str, start_line: int = 1, end_line: Optional[int] = None) -> dict[str, Any]:
    """Safely extracts text contents from a specific file array while enforcing line ceilings."""
    system_logger.info(f"Tool Requested: [read_file_content] | Target: {file_path}")
    try:
        target = resolve_workspace_path(file_path, must_exist=True)
        if not target.exists() or not target.is_file():
            return {"status": "failed", "content": "File block does not exist on disk."}
        with open(target, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        end_idx = min(len(all_lines), end_line or 500)
        start_idx = max(0, start_line - 1)
        return {
            "status": "success", 
            "content": "".join(all_lines[start_idx:end_idx]),
            "lines_inspected": f"{start_line} through {end_idx}"
        }
    except PolicyViolation as e:
        return {"status": "policy_denied", "content": str(e)}
    except UnicodeDecodeError:
         return {"status": "failed", "content": "Binary format mapping strictly blocked."}
    except Exception as e:
        return {"status": "failed", "content": str(e)}

@tool(args_schema=WriteFileSchema)
async def write_system_file(file_path: str, file_content: str) -> dict[str, Any]:
    """Exceptional fallback for whole-file writes. Prefer propose_patch for normal code edits."""
    system_logger.info(f"High-Risk Component Triggered: [write_system_file] | Target: {file_path}")
    try:
        from src.api.auth_bridge import wait_for_user_approval
        target = resolve_workspace_path(file_path)
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        diff = "".join(difflib.unified_diff(
            previous.splitlines(keepends=True),
            file_content.splitlines(keepends=True),
            fromfile=f"{file_path} (current)",
            tofile=f"{file_path} (proposed)",
            n=3,
        ))
        decision = classify_file_write(target, file_content)
        approved = await wait_for_user_approval(
            str(target.relative_to(ROOT_DIR)),
            file_content,
            diff=diff[:40_000],
            risk=decision.risk,
        )
        
        if not approved:
            return {"status": "unauthorized_abort", "result": "The Human operator securely aborted this write request."}
            
        # [V4 FIX: Item 7a] Trusted-write fast path
        # Documentation: 'write_trusted' is valid here because the 'wait_for_user_approval'
        # call above constitutes the required human authorization. 
        # This replaces the propose/approve bypass 'theater'.
        mutation_gate.write_trusted(
            file_path=str(target),
            proposed_content=file_content,
            explanation=f"Bulk write via write_system_file"
        )

        return {
            "status": "operation_success",
            "risk": decision.risk,
            "result": f"Exceptional whole-file write completed: '{target.relative_to(ROOT_DIR)}'"
        }
    except PolicyViolation as e:
        return {"status": "policy_denied", "result": str(e)}
    except Exception as e:
        return {"status": "hardware_failure", "result": str(e)}

@tool(args_schema=BashExecutionSchema)
def execute_system_bash(command: str, timeout_seconds: int = 60) -> dict[str, Any]:
    """Executes one explicit workspace command after policy inspection."""
    system_logger.info(f"High-Risk Component Triggered: [execute_system_bash] | Command: '{command}'")
    try:
        from src.runtime.terminal import ObservedPtyRunner
        from src.runtime.runs import current_run_context
        from src.core.event_bus import bus
        from src.core.event_bus.events import create_terminal_observed_data

        argv = parse_command(command)
        decision = command_policy(argv)
        if not decision.allowed:
            return {"status": "policy_denied", "stdout": "", "stderr": decision.reason, "risk": decision.risk}
        if decision.requires_approval:
            return {
                "status": "approval_required",
                "stdout": "",
                "stderr": f"Command requires a dedicated approved tool flow: {decision.reason}",
                "risk": decision.risk,
            }
        
        run_id, session_id = current_run_context()

        def on_data(data: str):
            # Stream PTY chunk to event bus
            try:
                event = create_terminal_observed_data(data, run_id=run_id or None)
                bus.publish(event)
            except:
                pass # Event bus failure should not halt the tool execution

        runner = ObservedPtyRunner(on_data=on_data, timeout_seconds=timeout_seconds)
        shell_result = runner.run(command)

        return {
            "status": "success" if shell_result["returncode"] == 0 else "failed",
            "risk": decision.risk,
            "returncode": shell_result["returncode"],
            "stdout": shell_result["stdout"][:3000],
            "stderr": shell_result["stderr"][:3000]
        }
    except PolicyViolation as e:
        return {"status": "policy_denied", "stdout": "", "stderr": str(e)}
    except Exception as e:
        return {"status": "critical_failure", "stdout": "", "stderr": f"Hardware crash: {str(e)}"}

@tool(args_schema=WebSearchSchema)
def web_search(query: str, max_results: int = 3) -> dict[str, Any]:
    """Generates real-time external network intelligence routing bypassing system boundaries."""
    system_logger.info(f"Tool Requested: [web_search] | Vector: '{query}'")
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=max_results)]
            return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "failed", "data": str(e)}

@tool(args_schema=ScoutQuerySchema)
def scout_query(
    q: Optional[str] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    module: Optional[str] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Query ALOS Scout diagnostics for recent logs, frontend errors, run events, and event-bus activity."""
    system_logger.info("Tool Requested: [scout_query]")
    try:
        from src.runtime.scout import list_scout_events

        events = list_scout_events(
            limit=max(1, min(int(limit or 50), 200)),
            source=source,
            level=level,
            module=module,
            run_id=run_id,
            session_id=session_id,
            q=q,
        )
        return {
            "status": "success",
            "count": len(events),
            "events": events,
        }
    except Exception as e:
        return {"status": "failed", "data": str(e)}

@tool(args_schema=ScrapeHTMLSchema)
def scrape_html_text(target_url: str) -> dict[str, Any]:
    """Tears down HTML DOM boundaries extracting formal text-only logic buffers."""
    system_logger.info(f"Tool Requested: [scrape_html_text] | Target: '{target_url}'")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup(["script", "style", "header", "footer", "nav"]):
            script.extract()
            
        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return {"status": "success", "content": text[:10000]}
    except Exception as e:
        return {"status": "failed", "content": f"URL Fetch Fault: {str(e)}"}

@tool(args_schema=GitRevertSchema)
def git_targeted_revert(file_path: str) -> dict[str, Any]:
    """Secures a clean git-rollback trace on an individual hardcoded file mapping."""
    system_logger.info(f"Tool Requested: [git_targeted_revert] | Target: '{file_path}'")
    return {
        "status": "policy_denied",
        "result": "Direct git rollback is disabled. Use an explicit diff review and approved patch flow instead."
    }


@tool(args_schema=ProposePatchSchema)
async def propose_patch(file_path: str, proposed_content: str, rationale: str = "") -> dict[str, Any]:
    """Creates a hash-guarded unified diff, requests human approval, and applies atomically."""
    system_logger.info(f"Patch Proposal Requested: [propose_patch] | Target: {file_path}")
    try:
        from src.api.auth_bridge import wait_for_patch_approval

        proposal = propose_and_save_patch(file_path, proposed_content, rationale)
        target = resolve_workspace_path(proposal.file)
        decision = classify_file_write(target, proposed_content)
        approved = await wait_for_patch_approval(public_patch_payload(proposal), risk=decision.risk)
        if not approved:
            from src.tools.patching import reject_patch_proposal
            reject_patch_proposal(proposal.id)
            return {"status": "rejected", "patch_id": proposal.id, "file": proposal.file}
        
        # [QUANTAMP INTEGRATION: MUTATION MANAGER]
        # DOCUMENTATION: apply_patch_proposal() below now owns the mutation_gate.approve() 
        # call, ensuring the patch and the gate remain in sync. Human approval above 
        # provides the bypass authorization.

        result = apply_patch_proposal(proposal, proposed_content)
        return {"patch_id": proposal.id, **result}
    except PolicyViolation as e:
        return {"status": "policy_denied", "result": str(e)}
    except Exception as e:
        return {"status": "patch_failure", "result": str(e)}

def get_core_tools() -> list:
    # Atlas tools are imported lazily so the registry stays usable even if
    # the modules tree is unreachable (packaged sidecar without modules/).
    try:
        from src.tools.atlas_tools import get_atlas_tools
        atlas_tools = get_atlas_tools()
    except Exception as exc:  # pragma: no cover — packaging fallback
        system_logger.warning(f"Atlas tools unavailable: {exc}")
        atlas_tools = []
    return [
        execute_sandboxed_python, read_local_directory, read_file_content,
        propose_patch, write_system_file, execute_system_bash, web_search,
        scout_query, scrape_html_text, git_targeted_revert,
        *atlas_tools,
    ]
