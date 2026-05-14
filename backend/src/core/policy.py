import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.core.config import ROOT_DIR


WORKSPACE_ROOT = ROOT_DIR.resolve()


class PolicyViolation(ValueError):
    """Raised when an agent action crosses ALOS runtime boundaries."""


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    risk: str
    reason: str
    requires_approval: bool = False


def resolve_workspace_path(raw_path: str, *, must_exist: bool = False) -> Path:
    if not raw_path or not str(raw_path).strip():
        raise PolicyViolation("Path is empty.")

    suspicious_fragments = ["|", "&&", "||", ";", "$(", "`", "\n", "\r"]
    if any(fragment in raw_path for fragment in suspicious_fragments):
        raise PolicyViolation("Path contains shell syntax. Use the bash tool for commands.")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate

    resolved = candidate.resolve()
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise PolicyViolation(f"Path escapes ALOS workspace: {raw_path}") from exc

    if must_exist and not resolved.exists():
        raise PolicyViolation("Path does not exist inside the ALOS workspace.")

    return resolved


def classify_file_write(path: Path, new_content: str) -> PolicyDecision:
    sensitive_names = {".env", ".env.example", "alos_memory.db", "newclaw_memory.db"}
    if path.name in sensitive_names:
        return PolicyDecision(True, "critical", "Sensitive runtime/config file write.", True)
    if path.suffix in {".py", ".js", ".html", ".css", ".toml", ".json", ".yaml", ".yml"}:
        return PolicyDecision(True, "high", "Source or configuration file write.", True)
    if len(new_content) > 250_000:
        return PolicyDecision(True, "high", "Large file write.", True)
    return PolicyDecision(True, "medium", "Workspace file write.", True)


def parse_command(command: str) -> list[str]:
    if not command or not command.strip():
        raise PolicyViolation("Command is empty.")
    if any(fragment in command for fragment in ["&&", "||", ";", "$(", "`", "\n", "\r"]):
        raise PolicyViolation("Compound shell syntax is blocked. Request one explicit command at a time.")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise PolicyViolation(f"Command parsing failed: {exc}") from exc
    if not parts:
        raise PolicyViolation("Command has no executable.")
    return parts


def command_policy(argv: Iterable[str]) -> PolicyDecision:
    parts = list(argv)
    executable = Path(parts[0]).name
    blocked = {
        "rm", "rmdir", "mv", "cp", "chmod", "chown", "sudo", "su",
        "dd", "mkfs", "diskutil", "launchctl", "kill", "pkill",
        "git-reset", "git-clean",
    }
    if executable in blocked:
        return PolicyDecision(False, "critical", f"Blocked destructive command: {executable}")

    if executable == "git" and len(parts) > 1:
        subcommand = parts[1]
        if subcommand in {"reset", "clean", "checkout", "restore", "push", "rebase"}:
            return PolicyDecision(False, "critical", f"Blocked git mutation command: git {subcommand}")

    if executable in {"python", "python3", "pip", "pip3", "npm", "uvicorn", "pytest"}:
        return PolicyDecision(True, "medium", "Development command inside workspace.", False)

    readonly = {"ls", "pwd", "find", "rg", "sed", "cat", "head", "tail", "wc", "sqlite3"}
    if executable in readonly:
        return PolicyDecision(True, "low", "Read-only inspection command.", False)

    return PolicyDecision(True, "medium", "Unclassified workspace command.", True)


def public_policy_snapshot() -> dict[str, Any]:
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "path_jail": True,
        "compound_shell_blocked": True,
        "destructive_git_blocked": True,
        "writes_require_approval": True,
    }
