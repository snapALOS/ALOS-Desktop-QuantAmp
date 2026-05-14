"""Configuration, profiles, and registry management."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RepositoryProfile


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".alos",
    ".alos_atlas",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    "gen",
    "generated",
    "coverage",
    ".cache",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

DEFAULT_SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

DEFAULT_SECRET_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".woff",
    ".woff2",
    ".ttf",
    ".rlib",
    ".rmeta",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return slug or "repo"


def stable_repo_id(name: str, path: str) -> str:
    digest = hashlib.sha256(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{slugify(name)}-{digest}"


def default_home() -> Path:
    configured = os.environ.get("ALOS_ATLAS_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".alos" / "atlas").resolve()


class AlosAtlasConfig:
    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or default_home()).resolve()
        self.registry_path = self.home / "registry.json"

    def ensure(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "repos").mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.write_text(json.dumps({"repositories": []}, indent=2), encoding="utf-8")

    def repo_dir(self, repo_id: str) -> Path:
        return self.home / "repos" / repo_id

    def load_registry(self) -> dict[str, Any]:
        self.ensure()
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def save_registry(self, registry: dict[str, Any]) -> None:
        self.ensure()
        self.registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")

    def list_profiles(self) -> list[RepositoryProfile]:
        registry = self.load_registry()
        return [RepositoryProfile.from_dict(item) for item in registry.get("repositories", [])]

    def get_profile(self, repo: str) -> RepositoryProfile:
        matches = [
            profile
            for profile in self.list_profiles()
            if profile.repo_id == repo or profile.repo_name == repo
        ]
        if not matches:
            raise KeyError(f"repository not registered: {repo}")
        return matches[0]

    def register(self, name: str, path: str) -> RepositoryProfile:
        repo_path = str(Path(path).expanduser().resolve())
        if not Path(repo_path).exists() or not Path(repo_path).is_dir():
            raise ValueError(f"repository path does not exist or is not a directory: {repo_path}")

        registry = self.load_registry()
        repos = registry.setdefault("repositories", [])
        repo_id = stable_repo_id(name, repo_path)
        profile = RepositoryProfile(repo_id=repo_id, repo_name=name, repo_path=repo_path)

        replaced = False
        for index, existing in enumerate(repos):
            if existing.get("repo_id") == repo_id or existing.get("repo_name") == name:
                repos[index] = profile.to_dict()
                replaced = True
                break
        if not replaced:
            repos.append(profile.to_dict())

        self.save_registry(registry)
        repo_dir = self.repo_dir(repo_id)
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "logs").mkdir(exist_ok=True)
        (repo_dir / "profile.json").write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        return profile

    def save_profile(self, profile: RepositoryProfile) -> RepositoryProfile:
        registry = self.load_registry()
        repos = registry.setdefault("repositories", [])
        for index, existing in enumerate(repos):
            if existing.get("repo_id") == profile.repo_id:
                repos[index] = profile.to_dict()
                break
        else:
            repos.append(profile.to_dict())
        self.save_registry(registry)
        repo_dir = self.repo_dir(profile.repo_id)
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "profile.json").write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        return profile

    def unregister(self, repo: str) -> RepositoryProfile:
        profile = self.get_profile(repo)
        registry = self.load_registry()
        registry["repositories"] = [
            item
            for item in registry.get("repositories", [])
            if item.get("repo_id") != profile.repo_id and item.get("repo_name") != profile.repo_name
        ]
        self.save_registry(registry)
        return profile
