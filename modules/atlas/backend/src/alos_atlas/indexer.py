"""AlosAtlas indexing orchestration."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import AlosAtlasConfig, utc_now
from .discovery import FileDiscoverer
from .models import Edge, FileRecord, Node, RepositoryProfile
from .parsers import AlosAtlasParser, make_edge
from .storage import IndexStore, node_id


def profile_hash(profile: RepositoryProfile) -> str:
    payload = json.dumps(profile.to_dict(), sort_keys=True)
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_revision(repo_path: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


class AlosAtlasIndexer:
    def __init__(self, config: AlosAtlasConfig, profile: RepositoryProfile) -> None:
        self.config = config
        self.profile = profile
        self.store = IndexStore(config, profile)

    def index(self) -> dict[str, Any]:
        self.config.ensure()
        self.store.reset_index()
        run_id = self.store.start_run(profile_hash(self.profile))

        discoverer = FileDiscoverer(self.profile)
        records, discovery_warnings = discoverer.discover()
        indexed_records = [record for record in records if record.indexed]
        parser = AlosAtlasParser(self.profile)

        all_nodes: list[Node] = []
        all_edges: list[Edge] = []
        search_text: list[tuple[str, str, str]] = []
        warnings = list(discovery_warnings)
        parse_failures = 0

        for record in indexed_records:
            result = parser.parse(record)
            all_nodes.extend(result.nodes)
            all_edges.extend(result.edges)
            search_text.extend(result.search_text)
            if result.warnings:
                parse_failures += len(result.warnings)
                warnings.extend(result.warnings)

        all_edges.extend(self._resolve_imports(all_nodes))
        all_edges.extend(self._link_endpoints_to_routes(all_nodes))
        all_edges.extend(self._link_tests(all_nodes))

        self.store.save_files(records)
        self.store.save_nodes_edges(all_nodes, all_edges, search_text)

        source_revision = git_revision(self.profile.path)
        indexed_at = utc_now()
        self.profile.last_indexed_at = indexed_at
        self.profile.source_revision = source_revision
        self.store.save_repository(indexed_at, source_revision)

        stats = {
            "files_scanned": len(records),
            "files_indexed": len(indexed_records),
            "files_skipped": len(records) - len(indexed_records),
            "parse_failures": parse_failures,
            "node_count": len(all_nodes),
            "edge_count": len(all_edges),
            "warnings": warnings,
        }
        self.store.finish_run(run_id, stats)

        status = {
            "repo_id": self.profile.repo_id,
            "repo_name": self.profile.repo_name,
            "repo_path": self.profile.repo_path,
            "indexed_at": indexed_at,
            "source_revision": source_revision,
            "stale": False,
            "health": self._health(stats),
            **stats,
        }
        manifest = [asdict(record) for record in records]
        self.store.write_json_artifacts(manifest, status)
        self._update_registry_profile()
        return status

    def refresh_changed(self) -> dict[str, Any]:
        manifest_path = self.store.repo_dir / "manifest.json"
        if not manifest_path.exists() or not self.store.db_path.exists():
            status = self.index()
            return {"mode": "full-index", "reason": "missing existing index", "status": status}

        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = self.index()
            return {"mode": "full-index", "reason": "unreadable manifest", "status": status}

        previous = {item["path"]: item for item in previous_manifest}
        records, discovery_warnings = FileDiscoverer(self.profile).discover()
        current = {record.path: record for record in records}
        changed_paths: list[str] = []

        for record in records:
            old = previous.get(record.path)
            if record.indexed and (not old or old.get("content_hash") != record.content_hash or not old.get("indexed")):
                changed_paths.append(record.path)
            elif old and old.get("indexed") and not record.indexed:
                changed_paths.append(record.path)

        deleted_paths = [
            path
            for path, old in previous.items()
            if old.get("indexed") and path not in current
        ]
        touched_paths = sorted(set(changed_paths + deleted_paths))
        if not touched_paths:
            return {"mode": "incremental", "changed_files": [], "refreshed": False, "status": self.store.read_status_file()}

        self.store.delete_paths(touched_paths)
        self.store.save_files(records)

        parser = AlosAtlasParser(self.profile)
        parsed_nodes: list[Node] = []
        parsed_edges: list[Edge] = []
        search_text: list[tuple[str, str, str]] = []
        warnings = list(discovery_warnings)
        parse_failures = 0

        indexed_records = [record for record in records if record.indexed and record.path in touched_paths]
        for record in indexed_records:
            result = parser.parse(record)
            parsed_nodes.extend(result.nodes)
            parsed_edges.extend(result.edges)
            search_text.extend(result.search_text)
            if result.warnings:
                parse_failures += len(result.warnings)
                warnings.extend(result.warnings)

        self.store.save_nodes_edges(parsed_nodes, parsed_edges, search_text)
        self.store.delete_edges_by_types(["IMPORTS_RESOLVED", "FETCHES_ROUTE", "TESTS"])
        all_nodes = self.store.all_nodes()
        derived_edges = [
            *self._resolve_imports(all_nodes),
            *self._link_endpoints_to_routes(all_nodes),
            *self._link_tests(all_nodes),
        ]
        self.store.save_nodes_edges([], derived_edges, [])

        source_revision = git_revision(self.profile.path)
        indexed_at = utc_now()
        self.profile.last_indexed_at = indexed_at
        self.profile.source_revision = source_revision
        self.store.save_repository(indexed_at, source_revision)

        counts = self.store.counts()
        stats = {
            "files_scanned": len(records),
            "files_indexed": counts.get("indexed_files", 0),
            "files_skipped": max(0, len(records) - counts.get("indexed_files", 0)),
            "parse_failures": parse_failures,
            "node_count": counts.get("nodes", 0),
            "edge_count": counts.get("edges", 0),
            "warnings": warnings,
        }
        status = {
            "repo_id": self.profile.repo_id,
            "repo_name": self.profile.repo_name,
            "repo_path": self.profile.repo_path,
            "indexed_at": indexed_at,
            "source_revision": source_revision,
            "stale": False,
            "health": self._health(stats),
            **stats,
        }
        self.store.write_json_artifacts([asdict(record) for record in records], status)
        self._update_registry_profile()
        return {
            "mode": "incremental",
            "changed_files": touched_paths,
            "refreshed": True,
            "parsed_files": [record.path for record in indexed_records],
            "status": status,
        }

    def _update_registry_profile(self) -> None:
        registry = self.config.load_registry()
        repos = registry.setdefault("repositories", [])
        for index, repo in enumerate(repos):
            if repo.get("repo_id") == self.profile.repo_id:
                repos[index] = self.profile.to_dict()
                break
        else:
            repos.append(self.profile.to_dict())
        self.config.save_registry(registry)

    def _health(self, stats: dict[str, Any]) -> str:
        if stats["files_indexed"] == 0:
            return "failed-empty-index"
        if stats["node_count"] <= stats["files_indexed"]:
            return "warning-low-symbol-yield"
        if stats["parse_failures"] > max(5, stats["files_indexed"] // 4):
            return "warning-parser-failures"
        return "ok"

    def _resolve_imports(self, nodes: list[Node]) -> list[Edge]:
        file_nodes = {node.path: node for node in nodes if node.type == "File"}
        module_index = self._module_index(file_nodes)
        edges: list[Edge] = []
        for node in nodes:
            if node.type != "Import":
                continue
            source_file = file_nodes.get(node.path)
            if not source_file:
                continue
            target = self._resolve_import_node(node, source_file, module_index, file_nodes)
            if not target:
                continue
            confidence = 0.9 if node.name.startswith(".") or node.name.startswith("/") else 0.8
            edges.append(
                make_edge(
                    self.profile.repo_id,
                    source_file,
                    target,
                    "IMPORTS_RESOLVED",
                    f"resolved import {node.name} to {target.path}",
                    confidence,
                    node.start_line,
                )
            )
        return edges

    def _module_index(self, file_nodes: dict[str, Node]) -> dict[str, Node]:
        index: dict[str, Node] = {}
        for path, node in file_nodes.items():
            p = Path(path)
            stem_path = p.with_suffix("").as_posix()
            dotted = stem_path.replace("/", ".")
            candidates = {
                dotted,
                p.stem,
                stem_path,
                path,
            }
            if "/src/" in f"/{path}":
                after_src = f"/{path}".split("/src/", 1)[1]
                candidates.add(Path(after_src).with_suffix("").as_posix().replace("/", "."))
            if p.name == "__init__.py":
                candidates.add(p.parent.as_posix().replace("/", "."))
            for candidate in candidates:
                index.setdefault(candidate, node)
        return index

    def _resolve_import_node(
        self,
        import_node: Node,
        source_file: Node,
        module_index: dict[str, Node],
        file_nodes: dict[str, Node],
    ) -> Node | None:
        name = import_node.name
        if name.startswith("."):
            return self._resolve_relative_import(name, source_file, file_nodes)
        if name.startswith("/"):
            return self._resolve_js_absolute(name, file_nodes)
        if name in module_index:
            return module_index[name]
        if "/" in name:
            return self._resolve_js_path(name, source_file, file_nodes)
        parts = name.split(".")
        for index in range(len(parts), 0, -1):
            candidate = ".".join(parts[:index])
            if candidate in module_index:
                return module_index[candidate]
        return None

    def _resolve_relative_import(self, name: str, source_file: Node, file_nodes: dict[str, Node]) -> Node | None:
        source_dir = Path(source_file.path).parent
        level = len(name) - len(name.lstrip("."))
        remainder = name[level:]
        base = source_dir
        for _ in range(max(level - 1, 0)):
            base = base.parent
        if remainder:
            base = base / remainder.replace(".", "/")
        candidates = self._path_candidates(base.as_posix())
        for candidate in candidates:
            if candidate in file_nodes:
                return file_nodes[candidate]
        return None

    def _resolve_js_path(self, name: str, source_file: Node, file_nodes: dict[str, Node]) -> Node | None:
        if name.startswith("."):
            base = Path(source_file.path).parent / name
        else:
            base = Path(name)
        for candidate in self._path_candidates(base.as_posix()):
            if candidate in file_nodes:
                return file_nodes[candidate]
        return None

    def _resolve_js_absolute(self, name: str, file_nodes: dict[str, Node]) -> Node | None:
        normalized = name.lstrip("/")
        for candidate in self._path_candidates(normalized):
            if candidate in file_nodes:
                return file_nodes[candidate]
            src_candidate = f"src/{candidate}"
            if src_candidate in file_nodes:
                return file_nodes[src_candidate]
        return None

    def _path_candidates(self, base: str) -> list[str]:
        stripped = base.replace("\\", "/").lstrip("./")
        suffixes = ["", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", "/__init__.py", "/index.js", "/index.ts", "/index.tsx"]
        return [stripped + suffix for suffix in suffixes]

    def _link_endpoints_to_routes(self, nodes: list[Node]) -> list[Edge]:
        routes = [node for node in nodes if node.type == "Route"]
        endpoints = [node for node in nodes if node.type == "Endpoint"]
        edges: list[Edge] = []
        for endpoint in endpoints:
            endpoint_path = endpoint.name.split("?", 1)[0]
            for route in routes:
                route_path = route.name.split(" ", 1)[-1]
                if endpoint_path == route_path or endpoint_path.endswith(route_path):
                    edges.append(
                        make_edge(
                            self.profile.repo_id,
                            endpoint,
                            route,
                            "FETCHES_ROUTE",
                            f"endpoint {endpoint.name} appears to call route {route.name}",
                            0.6,
                            endpoint.start_line,
                        )
                    )
        return edges

    def _link_tests(self, nodes: list[Node]) -> list[Edge]:
        tests = [node for node in nodes if node.type == "TestCase"]
        symbols = [node for node in nodes if node.type in {"Function", "Class", "Component", "Route", "File"}]
        edges: list[Edge] = []
        for test in tests:
            lowered = test.name.lower()
            for symbol in symbols:
                if symbol.id == test.id:
                    continue
                token = symbol.name.lower().split(".")[-1]
                if token and token in lowered:
                    edges.append(
                        make_edge(
                            self.profile.repo_id,
                            test,
                            symbol,
                            "TESTS",
                            f"test name references {symbol.name}",
                            0.5,
                            test.start_line,
                        )
                    )
        return edges


def index_repository(config: AlosAtlasConfig, repo: str) -> dict[str, Any]:
    profile = config.get_profile(repo)
    return AlosAtlasIndexer(config, profile).index()


def refresh_changed_repository(config: AlosAtlasConfig, repo: str) -> dict[str, Any]:
    profile = config.get_profile(repo)
    return AlosAtlasIndexer(config, profile).refresh_changed()
