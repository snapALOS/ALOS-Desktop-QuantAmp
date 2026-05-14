"""Core AlosAtlas data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RepositoryProfile:
    repo_id: str
    repo_name: str
    repo_path: str
    include_patterns: list[str] = field(default_factory=lambda: ["**/*"])
    exclude_patterns: list[str] = field(default_factory=list)
    languages: list[str] = field(
        default_factory=lambda: [
            "python",
            "javascript",
            "typescript",
            "tsx",
            "json",
            "markdown",
            "toml",
            "yaml",
            "shell",
            "rust",
            "go",
            "java",
            "csharp",
            "sql",
            "qml",
        ]
    )
    max_file_size_bytes: int = 512_000
    max_files: int = 20_000
    parse_tests: bool = True
    parse_docs: bool = True
    parse_configs: bool = True
    semantic_index_enabled: bool = False
    last_indexed_at: str | None = None
    source_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepositoryProfile":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})

    @property
    def path(self) -> Path:
        return Path(self.repo_path).expanduser().resolve()


@dataclass(slots=True)
class FileRecord:
    repo_id: str
    path: str
    absolute_path: str
    language: str
    file_class: str
    size_bytes: int
    content_hash: str
    indexed: bool
    reason: str


@dataclass(slots=True)
class Node:
    repo_id: str
    type: str
    name: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    signature: str | None = None
    content_hash: str | None = None
    confidence: float = 1.0
    id: str | None = None


@dataclass(slots=True)
class Edge:
    repo_id: str
    source_id: str
    target_id: str
    type: str
    confidence: float
    reason: str
    source_path: str
    source_line: int | None = None
    id: str | None = None


@dataclass(slots=True)
class ParseResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    search_text: list[tuple[str, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
