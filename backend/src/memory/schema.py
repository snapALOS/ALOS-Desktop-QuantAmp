from datetime import datetime
import re
from typing import Any, Dict, Literal, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


MemoryType = Literal[
    "checkpoint",
    "execution_insight",
    "decision",
    "project_fact",
    "user_preference",
    "failure_pattern",
    "tool_result",
    "run_summary",
    "integration_note",
]

MEMORY_TYPES = {
    "checkpoint",
    "execution_insight",
    "decision",
    "project_fact",
    "user_preference",
    "failure_pattern",
    "tool_result",
    "run_summary",
    "integration_note",
}

SECRET_PATTERNS = [
    re.compile(r"\b(nvapi-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{16,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{16,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
]

REDACTION = "[REDACTED_SECRET]"


def normalize_memory_type(value: str) -> MemoryType:
    candidate = (value or "execution_insight").strip()
    if candidate not in MEMORY_TYPES:
        return "execution_insight"
    return candidate  # type: ignore[return-value]


def redact_secrets(text: Any) -> Tuple[str, int]:
    redacted = str(text or "")
    count = 0
    for pattern in SECRET_PATTERNS:
        redacted, replacements = pattern.subn(lambda match: _replacement(match), redacted)
        count += replacements
    return redacted, count


def _replacement(match: re.Match) -> str:
    if match.re.pattern.lower().startswith("(?i)\\b(bearer"):
        return f"{match.group(1)}{REDACTION}"
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}={REDACTION}"
    return REDACTION


def redact_metadata(metadata: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    redacted: Dict[str, Any] = {}
    total = 0
    for key, value in (metadata or {}).items():
        if isinstance(value, dict):
            redacted_value, count = redact_metadata(value)
            redacted[str(key)] = redacted_value
            total += count
        elif isinstance(value, list):
            items = []
            for item in value:
                item_text, count = redact_secrets(item)
                items.append(item_text)
                total += count
            redacted[str(key)] = items
        else:
            text, count = redact_secrets(value)
            redacted[str(key)] = text
            total += count
    return redacted, total


class StrategicMemory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    memory_type: MemoryType
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "system"
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @field_validator("memory_type", mode="before")
    @classmethod
    def _valid_memory_type(cls, value):
        return normalize_memory_type(value)

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, value):
        content = str(value or "").strip()
        if not content:
            raise ValueError("memory content cannot be empty")
        return content

    def sanitized(self) -> "StrategicMemory":
        content, content_redactions = redact_secrets(self.content)
        metadata, metadata_redactions = redact_metadata(self.metadata)
        if content_redactions or metadata_redactions:
            metadata["redaction_count"] = str(content_redactions + metadata_redactions)
        return self.model_copy(update={"content": content, "metadata": metadata})

    def public_dict(self) -> Dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


class MemorySearchRequest(BaseModel):
    query: str = ""
    memory_type: Optional[MemoryType] = None
    scope: Literal["matters", "happened", "all"] = "matters"
    task_type: Optional[str] = None
    session_id: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=100)


class MemorySearchResult(BaseModel):
    memory: StrategicMemory
    score: float
    reason: str

    def public_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "reason": self.reason,
            **self.memory.public_dict(),
        }
