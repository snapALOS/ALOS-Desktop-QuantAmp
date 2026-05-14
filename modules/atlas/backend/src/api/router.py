"""
Atlas FastAPI router.

Auto-discovered and mounted by the ALOS sidecar at `/api/atlas/*`
(see backend/src/api/server.py::discover_and_mount_modules).

Wraps the alos_atlas.query API surface — a typed query facade over the
on-disk SQLite code graph the indexer produces. Exposes everything the
React AtlasView and agent-facing tools need: search, symbol/file context,
impact, change scope, recommended tests, graph data, listings, and a
release-critical export report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from alos_atlas.config import AlosAtlasConfig
from alos_atlas.indexer import index_repository
from alos_atlas.query import list_repositories, queries_for
from src.auth.rbac import require_run_read, require_run_write
from src.core.config import USER_DATA_DIR

router = APIRouter()

# Single config instance per process. Indexer + queries both honor
# the ALOS user-data directory as the on-disk root. The Atlas indexer is
# process-local; the ALOS sidecar drives it.
config = AlosAtlasConfig(Path(USER_DATA_DIR) / "atlas")
config.ensure()


def _repo_key(repo: str) -> str:
    """Resolve a repo id/name/path into the canonical registered repo id."""
    raw = (repo or "").strip()
    normalized = str(Path(raw).expanduser().resolve()) if raw else raw
    for profile in config.list_profiles():
        if raw in {profile.repo_id, profile.repo_name, profile.repo_path}:
            return profile.repo_id
        if normalized == profile.repo_path:
            return profile.repo_id
    return raw


def _q(repo: str):
    """Resolve a queries-handle for `repo`, or 404 if unknown."""
    try:
        return queries_for(config, _repo_key(repo))
    except Exception as exc:  # pragma: no cover — alos_atlas raises bare ValueError
        raise HTTPException(status_code=404, detail=f"Unknown repo {repo!r}: {exc}")


def _public_repo(repo: dict[str, Any]) -> dict[str, Any]:
    """Expose repo records in the shape the desktop client consumes."""
    path = repo.get("path") or repo.get("repo_path")
    name = repo.get("name") or repo.get("repo_name")
    return {
        **repo,
        "path": path,
        "name": name,
        "last_indexed": repo.get("last_indexed") or repo.get("last_indexed_at"),
    }


def _public_search(result: dict[str, Any]) -> dict[str, Any]:
    hits = []
    for item in result.get("results", []):
        node_id = item.get("id") or item.get("node_id") or item.get("path") or item.get("name")
        hits.append(
            {
                **item,
                "id": str(node_id),
                "snippet": item.get("snippet") or item.get("text"),
            }
        )
    return {**result, "results": hits}


def _impact_node(item: dict[str, Any]) -> dict[str, Any]:
    node_id = item.get("id") or item.get("source_id") or item.get("target_id") or item.get("path")
    node_type = item.get("type") or item.get("source_type") or item.get("target_type") or "Unknown"
    name = item.get("name") or item.get("source_name") or item.get("target_name") or str(node_id)
    path = item.get("path") or item.get("source_node_path") or item.get("target_node_path") or item.get("source_path")
    return {
        **item,
        "id": str(node_id),
        "type": str(node_type),
        "name": str(name),
        "path": path,
    }


def _public_impact(result: dict[str, Any]) -> dict[str, Any]:
    direct = [_impact_node(item) for item in result.get("direct_dependents", [])]
    indirect = [_impact_node(item) for item in result.get("indirect_dependents", [])]
    tests = [_impact_node(item) for item in result.get("affected_tests", [])]
    return {
        **result,
        "risk": result.get("risk") or result.get("risk_level"),
        "impacted": direct + indirect,
        "tests": tests,
        "verification_steps": result.get("verification_steps")
        or result.get("recommended_verification")
        or [],
    }


# ── Health / discovery ─────────────────────────────────────────────
@router.get("/health")
def health(_: str = Depends(require_run_read)) -> dict[str, Any]:
    return {"ok": True, "service": "atlas"}


@router.get("/repos")
def list_repos(_: str = Depends(require_run_read)) -> dict[str, Any]:
    return {"repositories": [_public_repo(repo) for repo in list_repositories(config)]}


@router.get("/status")
def get_status(repo: str = Query(...), _: str = Depends(require_run_read)) -> dict[str, Any]:
    status = _q(repo).status()
    return {
        **status,
        "path": status.get("path") or status.get("repo_path"),
        "last_indexed": status.get("last_indexed") or status.get("last_indexed_at") or status.get("indexed_at"),
    }


# ── Indexing ───────────────────────────────────────────────────────
@router.post("/index")
def index(
    repo: str = Query(..., description="Absolute path to the repository to index."),
    _: str = Depends(require_run_write),
):
    """
    Index a repository on disk. `repo` is the absolute filesystem path —
    Atlas registers it (assigning a stable repo_id) and (re)indexes.
    """
    repo_path = Path(repo).expanduser().resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Repository path does not exist: {repo_path}")
    profile = config.register(repo_path.name, str(repo_path))
    result = index_repository(config, profile.repo_id)
    return {
        **result,
        "path": result.get("path") or result.get("repo_path"),
        "last_indexed": result.get("last_indexed") or result.get("indexed_at"),
    }


# ── Search & context ───────────────────────────────────────────────
@router.get("/search")
def search(repo: str = Query(...), q: str = Query(...), limit: int = 10, _: str = Depends(require_run_read)):
    return _public_search(_q(repo).search(q, limit))


@router.get("/symbol")
def symbol_context(repo: str = Query(...), name: str = Query(...), limit: int = 20, _: str = Depends(require_run_read)):
    return _q(repo).symbol_context(name, limit)


@router.get("/file")
def file_context(repo: str = Query(...), path: str = Query(...), limit: int = 20, _: str = Depends(require_run_read)):
    return _q(repo).file_context(path, limit)


@router.get("/route")
def route_context(repo: str = Query(...), route: str = Query(...), limit: int = 20, _: str = Depends(require_run_read)):
    return _q(repo).route_context(route, limit)


# ── Impact / consequence ───────────────────────────────────────────
@router.get("/impact")
def impact(
    repo: str = Query(...),
    target: str = Query(...),
    type: str = "auto",
    depth: int = 3,
    limit: int = 50,
    _: str = Depends(require_run_read),
):
    return _public_impact(_q(repo).impact(target, target_type=type, depth=depth, limit=limit))


@router.get("/change_scope")
def change_scope(
    repo: str = Query(...),
    files: list[str] = Query(default=[]),
    use_git: bool = False,
    limit: int = 50,
    _: str = Depends(require_run_read),
):
    return _q(repo).change_scope(files=files or None, use_git=use_git, limit=limit)


@router.get("/recommend_tests")
def recommend_tests(
    repo: str = Query(...),
    target: str | None = Query(default=None),
    files: list[str] = Query(default=[]),
    limit: int = 20,
    _: str = Depends(require_run_read),
):
    return _q(repo).recommend_tests(target=target, files=files or None, limit=limit)


# ── Visual graph ───────────────────────────────────────────────────
@router.get("/graph")
def graph(repo: str = Query(...), limit: int = 80, _: str = Depends(require_run_read)) -> dict[str, Any]:
    """Nodes + edges suitable for a force-directed visualization."""
    return _q(repo).graph_data(limit=limit)


@router.get("/graph_overview")
def graph_overview(repo: str = Query(...), limit: int = 20, _: str = Depends(require_run_read)) -> dict[str, Any]:
    return _q(repo).graph_overview(limit=limit)


# ── Listings ───────────────────────────────────────────────────────
@router.get("/files")
def list_files_endpoint(
    repo: str = Query(...),
    limit: int = 100,
    indexed_only: bool = True,
    _: str = Depends(require_run_read),
):
    return _q(repo).list_files(limit=limit, indexed_only=indexed_only)


@router.get("/symbols")
def list_symbols_endpoint(
    repo: str = Query(...),
    limit: int = 100,
    type: str | None = Query(default=None),
    _: str = Depends(require_run_read),
):
    return _q(repo).list_symbols(limit=limit, type_=type)


# ── Reports ────────────────────────────────────────────────────────
@router.get("/report")
def export_report(
    repo: str = Query(...),
    target: str | None = Query(default=None),
    type: str = "auto",
    _: str = Depends(require_run_read),
):
    """Release-grade dependency + impact report for a target (or whole repo)."""
    return _q(repo).export_report(target=target, target_type=type)
