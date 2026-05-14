"""Bounded tool adapter functions for Reggie/OpenClaw-style callers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import AlosAtlasConfig
from .indexer import index_repository
from .query import list_repositories, queries_for


def _config(home: str | None = None) -> AlosAtlasConfig:
    return AlosAtlasConfig(Path(home).expanduser().resolve() if home else None)


def alos_atlas_list_repos(home: str | None = None, limit: int = 20) -> dict[str, Any]:
    config = _config(home)
    repos = list_repositories(config)[: max(1, min(limit, 20))]
    return {"repositories": repos, "limit": limit}


def alos_atlas_status(repo: str, home: str | None = None) -> dict[str, Any]:
    return queries_for(_config(home), repo).status()


def alos_atlas_query(repo: str, query: str, home: str | None = None, limit: int = 10) -> dict[str, Any]:
    return queries_for(_config(home), repo).search(query, limit=limit)


def alos_atlas_symbol_context(repo: str, symbol: str, home: str | None = None, limit: int = 20) -> dict[str, Any]:
    return queries_for(_config(home), repo).symbol_context(symbol, limit=limit)


def alos_atlas_file_context(repo: str, path: str, home: str | None = None, limit: int = 20) -> dict[str, Any]:
    return queries_for(_config(home), repo).file_context(path, limit=limit)


def alos_atlas_route_context(repo: str, route: str, home: str | None = None, limit: int = 20) -> dict[str, Any]:
    return queries_for(_config(home), repo).route_context(route, limit=limit)


def alos_atlas_impact(
    repo: str,
    target: str,
    home: str | None = None,
    target_type: str = "auto",
    depth: int = 3,
    limit: int = 50,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).impact(target, target_type=target_type, depth=depth, limit=limit)


def alos_atlas_change_scope(
    repo: str,
    files: list[str] | None = None,
    home: str | None = None,
    use_git: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).change_scope(files=files, use_git=use_git, limit=limit)


def alos_atlas_recommend_tests(
    repo: str,
    target: str | None = None,
    files: list[str] | None = None,
    home: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).recommend_tests(target=target, files=files, limit=limit)


def alos_atlas_graph(repo: str, home: str | None = None, limit: int = 20) -> dict[str, Any]:
    return queries_for(_config(home), repo).graph_overview(limit=limit)


def alos_atlas_graph_data(repo: str, home: str | None = None, limit: int = 80) -> dict[str, Any]:
    return queries_for(_config(home), repo).graph_data(limit=limit)


def alos_atlas_files(repo: str, home: str | None = None, limit: int = 100, indexed_only: bool = True) -> dict[str, Any]:
    return queries_for(_config(home), repo).list_files(limit=limit, indexed_only=indexed_only)


def alos_atlas_symbols(repo: str, home: str | None = None, limit: int = 100, type_: str | None = None) -> dict[str, Any]:
    return queries_for(_config(home), repo).list_symbols(limit=limit, type_=type_)


def alos_atlas_export_report(
    repo: str,
    home: str | None = None,
    target: str | None = None,
    target_type: str = "auto",
) -> dict[str, Any]:
    return queries_for(_config(home), repo).export_report(target=target, target_type=target_type)


def alos_atlas_export_index(repo: str, home: str | None = None, destination: str | None = None) -> dict[str, Any]:
    return queries_for(_config(home), repo).export_index_archive(destination=destination)


def alos_atlas_export_encrypted(
    repo: str,
    home: str | None = None,
    destination: str | None = None,
    passphrase: str | None = None,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).export_encrypted_archive(destination=destination, passphrase=passphrase)


def alos_atlas_decrypt_archive(
    repo: str,
    encrypted_path: str,
    home: str | None = None,
    destination: str | None = None,
    passphrase: str | None = None,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).decrypt_archive(
        encrypted_path,
        destination=destination,
        passphrase=passphrase,
    )


def alos_atlas_lock_index(repo: str, home: str | None = None, passphrase: str | None = None) -> dict[str, Any]:
    return queries_for(_config(home), repo).lock_index(passphrase=passphrase)


def alos_atlas_unlock_index(
    repo: str,
    home: str | None = None,
    encrypted_path: str | None = None,
    passphrase: str | None = None,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).unlock_index(
        encrypted_path=encrypted_path,
        passphrase=passphrase,
    )


def alos_atlas_traces(repo: str, home: str | None = None, limit: int = 100) -> dict[str, Any]:
    return queries_for(_config(home), repo).runtime_traces(limit=limit)


def alos_atlas_trace(
    repo: str,
    trace: dict[str, Any],
    home: str | None = None,
) -> dict[str, Any]:
    return queries_for(_config(home), repo).add_runtime_trace(trace)


def alos_atlas_index(repo: str, home: str | None = None, allow_heavy_indexing: bool = False) -> dict[str, Any]:
    if not allow_heavy_indexing:
        return {
            "refused": True,
            "reason": "indexing is a heavy operation and requires explicit approval",
            "required_argument": "allow_heavy_indexing=True",
        }
    return index_repository(_config(home), repo)
