"""
Atlas — agent-facing tools.

Wraps ``alos_atlas.query`` in-process so the swarm agents can use the same
visual-dependency-intelligence the user sees in AtlasView, without going
out to HTTP. The tools are deliberately small and side-effect-free so they
can be granted to research, architecture, and planning agents.

Imports are lazy: ``alos_atlas`` only joins ``sys.path`` after the FastAPI
``discover_and_mount_modules`` pass runs. Importing at the top of this
module would race that wiring and break the sidecar boot order.

Usage shape mirrors the FastAPI router in
``modules/atlas/backend/src/api/router.py`` — keep the two in lockstep.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.core.config import ROOT_DIR, USER_DATA_DIR, system_logger


# ── Lazy alos_atlas import ────────────────────────────────────────
def _ensure_alos_atlas_on_path() -> None:
    """
    Make sure ``modules/atlas/backend/src`` is on sys.path so we can
    import ``alos_atlas``. Idempotent — safe to call from every tool.
    The ALOS sidecar already does this in ``discover_and_mount_modules``,
    so by the time tools fire we're a no-op. But if a unit test or REPL
    calls a tool before the FastAPI mount runs, we still work.
    """
    candidate = (
        Path(__file__).resolve().parent.parent.parent.parent  # → repo root
        / "modules"
        / "atlas"
        / "backend"
        / "src"
    )
    p = str(candidate)
    if candidate.is_dir() and p not in sys.path:
        sys.path.insert(0, p)


def _config_and_repo(repo_hint: Optional[str] = None):
    """
    Resolve (config, repo_key). ``repo_hint`` is the absolute repo path
    or repo_id. If omitted, we fall back to the ALOS workspace itself.
    """
    _ensure_alos_atlas_on_path()
    from alos_atlas.config import AlosAtlasConfig
    from alos_atlas.query import list_repositories

    config = AlosAtlasConfig(Path(USER_DATA_DIR) / "atlas")
    config.ensure()

    if repo_hint:
        return config, repo_hint

    # No hint — pick the ALOS source root if it's been indexed; otherwise
    # use the first available repo.
    default = str(ROOT_DIR.resolve().parent)
    repos = list_repositories(config)
    paths = {
        r.get("repo_path") or r.get("path"): r.get("repo_id")
        for r in repos
    }
    if default in paths:
        return config, paths[default]
    if repos:
        first = repos[0]
        return config, first.get("repo_id") or first.get("repo_path") or first.get("path")
    # Nothing indexed yet — return the default; the caller will get a
    # clean error from alos_atlas.
    return config, default


# ── Tool input schemas ────────────────────────────────────────────
class AtlasSearchSchema(BaseModel):
    query: str = Field(..., description="Concept, symbol name, or path fragment to search for.")
    repo: Optional[str] = Field(default=None, description="Absolute repo path or repo_id. Defaults to the ALOS workspace.")
    limit: int = Field(default=10, description="Max results.")


class AtlasImpactSchema(BaseModel):
    target: str = Field(..., description="Symbol name, file path, or route to compute blast radius for.")
    repo: Optional[str] = Field(default=None, description="Absolute repo path or repo_id. Defaults to the ALOS workspace.")
    target_type: str = Field(default="auto", description="One of: auto, symbol, file, route.")
    depth: int = Field(default=3, description="Transitive depth (1=direct callers; 3=typical).")
    limit: int = Field(default=50, description="Max impacted nodes to return.")


class AtlasContextSchema(BaseModel):
    name: str = Field(..., description="Symbol name to expand to its full context (callers, callees, references).")
    repo: Optional[str] = Field(default=None, description="Absolute repo path or repo_id. Defaults to the ALOS workspace.")
    limit: int = Field(default=20, description="Max context entries per category.")


class AtlasFileContextSchema(BaseModel):
    path: str = Field(..., description="Absolute or repo-relative path of the file to inspect.")
    repo: Optional[str] = Field(default=None, description="Absolute repo path or repo_id. Defaults to the ALOS workspace.")
    limit: int = Field(default=20, description="Max related entries to return.")


class AtlasStatusSchema(BaseModel):
    repo: Optional[str] = Field(default=None, description="Absolute repo path or repo_id. Defaults to the ALOS workspace.")


class AtlasReportSchema(BaseModel):
    target: Optional[str] = Field(default=None, description="Optional symbol/file/route to focus the report on.")
    repo: Optional[str] = Field(default=None, description="Absolute repo path or repo_id. Defaults to the ALOS workspace.")
    target_type: str = Field(default="auto", description="One of: auto, symbol, file, route.")


# ── Tools ─────────────────────────────────────────────────────────
@tool(args_schema=AtlasSearchSchema)
def atlas_search(query: str, repo: Optional[str] = None, limit: int = 10) -> dict[str, Any]:
    """Search the Atlas code graph by concept, symbol name, or path fragment.

    Returns a list of ranked hits — each hit names a file, symbol, route,
    or other graph node. Use this to discover candidates before drilling
    in with ``atlas_context`` or ``atlas_impact``.
    """
    try:
        from alos_atlas.query import queries_for  # type: ignore[import-not-found]
        config, key = _config_and_repo(repo)
        result = queries_for(config, key).search(query, limit)
        return {"status": "ok", "result": result}
    except Exception as exc:  # pragma: no cover — surfaced to agent
        system_logger.warning(f"atlas_search failed: {exc}")
        return {"status": "error", "result": str(exc)}


@tool(args_schema=AtlasImpactSchema)
def atlas_impact(
    target: str,
    repo: Optional[str] = None,
    target_type: str = "auto",
    depth: int = 3,
    limit: int = 50,
) -> dict[str, Any]:
    """Compute blast radius for a symbol, file, or route.

    Returns risk classification, list of impacted nodes (with depth and
    confidence), recommended tests, and verification steps. Use this
    BEFORE editing anything load-bearing.
    """
    try:
        from alos_atlas.query import queries_for  # type: ignore[import-not-found]
        config, key = _config_and_repo(repo)
        result = queries_for(config, key).impact(
            target, target_type=target_type, depth=depth, limit=limit
        )
        return {"status": "ok", "result": result}
    except Exception as exc:
        system_logger.warning(f"atlas_impact failed: {exc}")
        return {"status": "error", "result": str(exc)}


@tool(args_schema=AtlasContextSchema)
def atlas_context(name: str, repo: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    """Resolve full context for a symbol — callers, callees, references.

    Use this to understand a function/class/method end-to-end before
    refactoring or extracting it. Pairs with ``atlas_impact`` for safety.
    """
    try:
        from alos_atlas.query import queries_for  # type: ignore[import-not-found]
        config, key = _config_and_repo(repo)
        result = queries_for(config, key).symbol_context(name, limit=limit)
        return {"status": "ok", "result": result}
    except Exception as exc:
        system_logger.warning(f"atlas_context failed: {exc}")
        return {"status": "error", "result": str(exc)}


@tool(args_schema=AtlasFileContextSchema)
def atlas_file_context(
    path: str, repo: Optional[str] = None, limit: int = 20
) -> dict[str, Any]:
    """Resolve full context for a file — symbols defined, files imported, dependents."""
    try:
        from alos_atlas.query import queries_for  # type: ignore[import-not-found]
        config, key = _config_and_repo(repo)
        result = queries_for(config, key).file_context(path, limit=limit)
        return {"status": "ok", "result": result}
    except Exception as exc:
        system_logger.warning(f"atlas_file_context failed: {exc}")
        return {"status": "error", "result": str(exc)}


@tool(args_schema=AtlasStatusSchema)
def atlas_status(repo: Optional[str] = None) -> dict[str, Any]:
    """Check whether the Atlas index is fresh, stale, or absent for a repo."""
    try:
        from alos_atlas.query import queries_for  # type: ignore[import-not-found]
        config, key = _config_and_repo(repo)
        return {"status": "ok", "result": queries_for(config, key).status()}
    except Exception as exc:
        system_logger.warning(f"atlas_status failed: {exc}")
        return {"status": "error", "result": str(exc)}


@tool(args_schema=AtlasReportSchema)
def atlas_report(
    target: Optional[str] = None,
    repo: Optional[str] = None,
    target_type: str = "auto",
) -> dict[str, Any]:
    """Generate a release-grade dependency + impact report.

    Same shape as ``atlas_impact`` plus a summary suitable for inclusion
    in PR descriptions and release notes.
    """
    try:
        from alos_atlas.query import queries_for  # type: ignore[import-not-found]
        config, key = _config_and_repo(repo)
        result = queries_for(config, key).export_report(target=target, target_type=target_type)
        return {"status": "ok", "result": result}
    except Exception as exc:
        system_logger.warning(f"atlas_report failed: {exc}")
        return {"status": "error", "result": str(exc)}


def get_atlas_tools() -> list:
    """Convenience accessor mirroring ``get_core_tools``."""
    return [
        atlas_search,
        atlas_impact,
        atlas_context,
        atlas_file_context,
        atlas_status,
        atlas_report,
    ]


__all__ = [
    "atlas_search",
    "atlas_impact",
    "atlas_context",
    "atlas_file_context",
    "atlas_status",
    "atlas_report",
    "get_atlas_tools",
]
