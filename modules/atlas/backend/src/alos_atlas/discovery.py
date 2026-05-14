"""Safe repository file discovery and classification."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path

from .config import (
    BINARY_SUFFIXES,
    DEFAULT_EXCLUDE_DIRS,
    DEFAULT_SECRET_NAMES,
    DEFAULT_SECRET_SUFFIXES,
)
from .models import FileRecord, RepositoryProfile


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".sql": "sql",
    ".qml": "qml",
    ".ui": "qml",
}

CONFIG_NAMES = {
    "dockerfile",
    "makefile",
    "package.json",
    "tsconfig.json",
    "vite.config.ts",
    "jest.config.js",
    "pyproject.toml",
    "requirements.txt",
}

GENERATED_MARKERS = {
    ".min.js",
    ".bundle.js",
    ".generated.",
    ".g.",
    "_pb2.py",
}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_secret_path(path: Path) -> bool:
    name = path.name.lower()
    if name in DEFAULT_SECRET_NAMES:
        return True
    if any(name.endswith(suffix) for suffix in DEFAULT_SECRET_SUFFIXES):
        return True
    secret_terms = ["secret", "credential", "apikey", "api-key"]
    if any(term in name for term in secret_terms):
        return True
    if "token" in name and path.suffix.lower() in {"", ".json", ".txt", ".key", ".env"}:
        return True
    if "password" in name and path.suffix.lower() in {"", ".txt", ".json", ".env"}:
        return True
    return False


def is_generated(path: Path) -> bool:
    lower = path.name.lower()
    return any(marker in lower for marker in GENERATED_MARKERS)


def detect_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in LANGUAGE_BY_SUFFIX:
        return LANGUAGE_BY_SUFFIX[suffix]
    if path.name.lower() in CONFIG_NAMES:
        return "config"
    return "unknown"


def classify_file(path: Path, language: str) -> str:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if is_generated(path):
        return "generated"
    if "test" in parts or "tests" in parts or name.startswith("test_") or name.endswith(".test.ts"):
        return "test"
    if language in {"json", "toml", "yaml", "config"} or name in CONFIG_NAMES:
        return "config"
    if language == "markdown":
        return "documentation"
    if language == "shell":
        return "script"
    if language == "tsx" or name.endswith(".jsx"):
        return "ui"
    if "routes" in parts or "api" in parts:
        return "route"
    if language in {"python", "javascript", "typescript", "rust", "go", "java", "csharp", "sql"}:
        return "source"
    if language == "qml":
        return "ui"
    return "unknown"


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


class FileDiscoverer:
    def __init__(self, profile: RepositoryProfile) -> None:
        self.profile = profile

    def discover(self) -> tuple[list[FileRecord], list[str]]:
        root = self.profile.path
        warnings: list[str] = []
        records: list[FileRecord] = []
        scanned = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                dirname
                for dirname in dirnames
                if dirname.lower() not in DEFAULT_EXCLUDE_DIRS
                and not matches_any((Path(dirpath) / dirname).relative_to(root).as_posix(), self.profile.exclude_patterns)
            )

            for filename in sorted(filenames):
                path = Path(dirpath) / filename

                relative = path.relative_to(root).as_posix()
                parts = set(path.relative_to(root).parts)
                lower_parts = {part.lower() for part in parts}
                language = detect_language(path)
                file_class = classify_file(path.relative_to(root), language)
                reason = "indexed"
                indexed = True

                if lower_parts & DEFAULT_EXCLUDE_DIRS:
                    indexed = False
                    reason = "excluded directory"
                elif matches_any(relative, self.profile.exclude_patterns):
                    indexed = False
                    reason = "profile exclusion"
                elif not matches_any(relative, self.profile.include_patterns):
                    indexed = False
                    reason = "not included by profile"
                elif is_secret_path(path):
                    indexed = False
                    reason = "secret-like file skipped"
                    warnings.append(f"Skipped secret-like file: {relative}")
                elif path.suffix.lower() in BINARY_SUFFIXES:
                    indexed = False
                    reason = "binary/media/archive skipped"
                elif is_generated(path):
                    indexed = False
                    reason = "generated file skipped"
                elif path.stat().st_size > self.profile.max_file_size_bytes:
                    indexed = False
                    reason = "file too large"
                elif language not in self.profile.languages and language != "config":
                    indexed = False
                    reason = "unsupported language"
                elif file_class == "test" and not self.profile.parse_tests:
                    indexed = False
                    reason = "tests disabled"
                elif file_class == "documentation" and not self.profile.parse_docs:
                    indexed = False
                    reason = "docs disabled"
                elif file_class == "config" and not self.profile.parse_configs:
                    indexed = False
                    reason = "configs disabled"

                if indexed:
                    scanned += 1
                    if scanned > self.profile.max_files:
                        indexed = False
                        reason = "max files limit reached"

                content_hash = file_hash(path) if indexed else ""
                records.append(
                    FileRecord(
                        repo_id=self.profile.repo_id,
                        path=relative,
                        absolute_path=str(path.resolve()),
                        language=language,
                        file_class=file_class,
                        size_bytes=path.stat().st_size,
                        content_hash=content_hash,
                        indexed=indexed,
                        reason=reason,
                    )
                )

        return records, warnings
