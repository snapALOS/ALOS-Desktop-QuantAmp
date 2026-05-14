"""Bounded query, impact, and change-scope operations."""

from __future__ import annotations

import json
import shutil
import subprocess
import stat
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import AlosAtlasConfig
from .discovery import FileDiscoverer, file_hash
from .models import Node, RepositoryProfile
from .storage import IndexStore, node_id
from .vault import decrypt_file, encrypt_file


DEFAULT_LIMIT = 10


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row)


class AlosAtlasQueries:
    def __init__(self, config: AlosAtlasConfig, profile: RepositoryProfile) -> None:
        self.config = config
        self.profile = profile
        self.store = IndexStore(config, profile)

    def status(self) -> dict[str, Any]:
        stored = self.store.read_status_file()
        if not stored:
            return {
                "repo_id": self.profile.repo_id,
                "repo_name": self.profile.repo_name,
                "repo_path": self.profile.repo_path,
                "indexed": False,
                "stale": True,
                "reason": "repository has not been indexed",
            }

        stale_reasons = self._stale_reasons(stored)
        counts = self.store.counts() if self.store.db_path.exists() else {}
        return {
            **stored,
            "indexed": True,
            "stale": bool(stale_reasons),
            "stale_reasons": stale_reasons,
            "counts": counts,
            "files_indexed": counts.get("indexed_files", stored.get("files_indexed", 0)),
            "node_count": counts.get("nodes", stored.get("node_count", 0)),
            "edge_count": counts.get("edges", stored.get("edge_count", 0)),
        }

    def _stale_reasons(self, stored: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        manifest_path = self.store.repo_dir / "manifest.json"
        if not manifest_path.exists():
            return ["manifest missing"]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["manifest unreadable"]

        root = self.profile.path
        for entry in manifest:
            if not entry.get("indexed"):
                continue
            path = root / entry["path"]
            if not path.exists():
                reasons.append(f"indexed file missing: {entry['path']}")
                continue
            try:
                current_hash = file_hash(path)
            except OSError:
                reasons.append(f"indexed file unreadable: {entry['path']}")
                continue
            if current_hash != entry.get("content_hash"):
                reasons.append(f"indexed file changed: {entry['path']}")
            if len(reasons) >= 10:
                reasons.append("additional stale files omitted")
                break
        return reasons

    def search(self, text: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        limit = self._limit(limit)
        pattern = f"%{text.lower()}%"
        rows = self.store.query(
            """
            SELECT DISTINCT node_id, path, type, name, text
            FROM search_index
            WHERE repo_id = ? AND lower(text) LIKE ?
            ORDER BY type, name
            LIMIT ?
            """,
            (self.profile.repo_id, pattern, limit),
        )
        return {
            "status": self._brief_status(),
            "query": text,
            "limit": limit,
            "results": [row_dict(row) for row in rows],
        }

    def file_context(self, path: str, limit: int = 20) -> dict[str, Any]:
        limit = self._limit(limit, 50)
        normalized = path.replace("\\", "/").lstrip("./")
        nodes = self.store.query(
            """
            SELECT * FROM nodes
            WHERE repo_id = ? AND path = ?
            ORDER BY start_line, type, name
            LIMIT ?
            """,
            (self.profile.repo_id, normalized, limit),
        )
        file_nodes = [row for row in nodes if row["type"] == "File"]
        ids = [row["id"] for row in file_nodes] or [row["id"] for row in nodes[:1]]
        edges = self._edges_for_ids(ids, limit=limit)
        return {
            "status": self._brief_status(),
            "path": normalized,
            "nodes": [row_dict(row) for row in nodes],
            "relationships": edges,
        }

    def symbol_context(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        limit = self._limit(limit, 50)
        pattern = f"%{symbol.lower()}%"
        nodes = self.store.query(
            """
            SELECT * FROM nodes
            WHERE repo_id = ? AND lower(name) LIKE ? AND type != 'File'
            ORDER BY confidence DESC, type, name
            LIMIT ?
            """,
            (self.profile.repo_id, pattern, limit),
        )
        ids = [row["id"] for row in nodes]
        return {
            "status": self._brief_status(),
            "symbol": symbol,
            "matches": [row_dict(row) for row in nodes],
            "relationships": self._edges_for_ids(ids, limit=limit),
        }

    def route_context(self, route: str, limit: int = 20) -> dict[str, Any]:
        limit = self._limit(limit, 50)
        pattern = f"%{route.lower()}%"
        nodes = self.store.query(
            """
            SELECT * FROM nodes
            WHERE repo_id = ? AND type IN ('Route', 'Endpoint') AND lower(name) LIKE ?
            ORDER BY type, name
            LIMIT ?
            """,
            (self.profile.repo_id, pattern, limit),
        )
        ids = [row["id"] for row in nodes]
        return {
            "status": self._brief_status(),
            "route": route,
            "matches": [row_dict(row) for row in nodes],
            "relationships": self._edges_for_ids(ids, limit=limit),
        }

    def impact(self, target: str, target_type: str = "auto", depth: int = 3, limit: int = 50) -> dict[str, Any]:
        depth = max(1, min(depth, 5))
        limit = self._limit(limit, 100)
        seeds = self._find_targets(target, target_type, limit=10)
        visited: set[str] = set()
        frontier = [(row["id"], 0) for row in seeds]
        impacted: list[dict[str, Any]] = []

        while frontier and len(impacted) < limit:
            current_id, current_depth = frontier.pop(0)
            if current_id in visited or current_depth >= depth:
                continue
            visited.add(current_id)
            rows = self.store.query(
                """
                SELECT e.*, n.type AS source_type, n.name AS source_name, n.path AS source_node_path
                FROM edges e
                JOIN nodes n ON n.id = e.source_id
                WHERE e.repo_id = ? AND e.target_id = ?
                ORDER BY e.confidence DESC
                LIMIT ?
                """,
                (self.profile.repo_id, current_id, limit),
            )
            for row in rows:
                item = row_dict(row)
                item["depth"] = current_depth + 1
                impacted.append(item)
                frontier.append((row["source_id"], current_depth + 1))

        risk = self._risk(impacted)
        tests = self._tests_for_node_ids([row["id"] for row in seeds] + [row["source_id"] for row in impacted], limit=20)
        tests.extend(self._test_dependents(impacted, limit=20))
        return {
            "status": self._brief_status(),
            "target": target,
            "target_type": target_type,
            "seeds": [row_dict(row) for row in seeds],
            "risk_level": risk,
            "confidence": self._average_confidence(impacted),
            "direct_dependents": [item for item in impacted if item["depth"] == 1],
            "indirect_dependents": [item for item in impacted if item["depth"] > 1],
            "affected_tests": tests,
            "recommended_verification": self._verification_steps(risk, tests),
        }

    def change_scope(self, files: list[str] | None = None, use_git: bool = False, limit: int = 50) -> dict[str, Any]:
        changed = files or []
        if use_git:
            changed.extend(self._git_changed_files())
        normalized = sorted({item.replace("\\", "/").lstrip("./") for item in changed if item})
        results = []
        for path in normalized[: self._limit(limit, 100)]:
            context = self.file_context(path, limit=20)
            impact = self.impact(path, "file", depth=3, limit=25)
            results.append(
                {
                    "path": path,
                    "changed_symbols": [
                        node
                        for node in context.get("nodes", [])
                        if node.get("type") not in {"File", "Import", "Call"}
                    ],
                    "impact": impact,
                }
            )
        docs = [path for path in normalized if path.lower().endswith((".md", ".rst", ".txt"))]
        return {
            "status": self._brief_status(),
            "changed_files": normalized,
            "docs_changed": docs,
            "files": results,
            "recommended_tests": self.recommend_tests(files=normalized, limit=25)["tests"],
        }

    def recommend_tests(self, target: str | None = None, files: list[str] | None = None, limit: int = 20) -> dict[str, Any]:
        limit = self._limit(limit, 50)
        target_ids: list[str] = []
        if target:
            target_ids.extend(row["id"] for row in self._find_targets(target, "auto", limit=10))
        if files:
            for path in files:
                file_target = self._find_targets(path, "file", limit=5)
                target_ids.extend(row["id"] for row in file_target)
        tests = self._tests_for_node_ids(target_ids, limit=limit)
        if not tests and (target or files):
            tests = self._heuristic_tests(target, files or [], limit)
        return {
            "status": self._brief_status(),
            "target": target,
            "files": files or [],
            "tests": tests,
        }

    def graph_overview(self, limit: int = 20) -> dict[str, Any]:
        limit = self._limit(limit, 100)
        node_counts = self.store.query(
            """
            SELECT type, COUNT(*) AS count
            FROM nodes
            WHERE repo_id = ?
            GROUP BY type
            ORDER BY count DESC, type
            """,
            (self.profile.repo_id,),
        )
        edge_counts = self.store.query(
            """
            SELECT type, COUNT(*) AS count
            FROM edges
            WHERE repo_id = ?
            GROUP BY type
            ORDER BY count DESC, type
            """,
            (self.profile.repo_id,),
        )
        file_classes = self.store.query(
            """
            SELECT file_class, COUNT(*) AS count
            FROM files
            WHERE repo_id = ?
            GROUP BY file_class
            ORDER BY count DESC, file_class
            """,
            (self.profile.repo_id,),
        )
        top_files = self.store.query(
            """
            SELECT path, COUNT(nodes.id) AS symbols
            FROM nodes
            WHERE repo_id = ? AND type != 'File'
            GROUP BY path
            ORDER BY symbols DESC, path
            LIMIT ?
            """,
            (self.profile.repo_id, limit),
        )
        return {
            "status": self._brief_status(),
            "node_counts": [row_dict(row) for row in node_counts],
            "edge_counts": [row_dict(row) for row in edge_counts],
            "file_classes": [row_dict(row) for row in file_classes],
            "top_files": [row_dict(row) for row in top_files],
        }

    def graph_data(self, limit: int = 80) -> dict[str, Any]:
        limit = self._limit(limit, 200)
        nodes = self.store.query(
            """
            SELECT id, type, name, path, confidence
            FROM nodes
            WHERE repo_id = ?
            ORDER BY CASE type WHEN 'File' THEN 0 WHEN 'Route' THEN 1 WHEN 'Endpoint' THEN 2 ELSE 3 END,
                     path, name
            LIMIT ?
            """,
            (self.profile.repo_id, limit),
        )
        node_ids = [row["id"] for row in nodes]
        if not node_ids:
            return {"status": self._brief_status(), "nodes": [], "edges": []}
        bind_marks = ",".join("?" for _ in node_ids)
        edges = self.store.query(
            f"""
            SELECT id, source_id, target_id, type, confidence, reason
            FROM edges
            WHERE repo_id = ? AND source_id IN ({bind_marks}) AND target_id IN ({bind_marks})
            ORDER BY confidence DESC, type
            LIMIT ?
            """,
            tuple([self.profile.repo_id, *node_ids, *node_ids, limit * 2]),
        )
        return {
            "status": self._brief_status(),
            "nodes": [row_dict(row) for row in nodes],
            "edges": [row_dict(row) for row in edges],
        }

    def list_files(self, limit: int = 100, indexed_only: bool = True) -> dict[str, Any]:
        limit = self._limit(limit, 500)
        if indexed_only:
            rows = self.store.query(
                """
                SELECT path, language, file_class, size_bytes, indexed, reason
                FROM files
                WHERE repo_id = ? AND indexed = 1
                ORDER BY path
                LIMIT ?
                """,
                (self.profile.repo_id, limit),
            )
        else:
            rows = self.store.query(
                """
                SELECT path, language, file_class, size_bytes, indexed, reason
                FROM files
                WHERE repo_id = ?
                ORDER BY path
                LIMIT ?
                """,
                (self.profile.repo_id, limit),
            )
        return {"status": self._brief_status(), "files": [row_dict(row) for row in rows]}

    def list_symbols(self, limit: int = 100, type_: str | None = None) -> dict[str, Any]:
        limit = self._limit(limit, 500)
        if type_:
            rows = self.store.query(
                """
                SELECT id, type, name, path, start_line, confidence, signature
                FROM nodes
                WHERE repo_id = ? AND type = ?
                ORDER BY path, start_line, name
                LIMIT ?
                """,
                (self.profile.repo_id, type_, limit),
            )
        else:
            rows = self.store.query(
                """
                SELECT id, type, name, path, start_line, confidence, signature
                FROM nodes
                WHERE repo_id = ? AND type != 'File'
                ORDER BY path, start_line, type, name
                LIMIT ?
                """,
                (self.profile.repo_id, limit),
            )
        return {"status": self._brief_status(), "symbols": [row_dict(row) for row in rows]}

    def export_report(self, target: str | None = None, target_type: str = "auto") -> dict[str, Any]:
        status = self.status()
        graph = self.graph_overview(limit=10)
        body = [
            "# AlosAtlas Report",
            "",
            f"- Repository: {self.profile.repo_name}",
            f"- Path: {self.profile.repo_path}",
            f"- Indexed: {status.get('indexed')}",
            f"- Stale: {status.get('stale')}",
            "",
            "## Graph Overview",
            "",
        ]
        for item in graph["node_counts"]:
            body.append(f"- Nodes `{item['type']}`: {item['count']}")
        for item in graph["edge_counts"]:
            body.append(f"- Edges `{item['type']}`: {item['count']}")
        if target:
            impact = self.impact(target, target_type=target_type)
            body.extend(
                [
                    "",
                    "## Impact",
                    "",
                    f"- Target: {target}",
                    f"- Risk: {impact['risk_level']}",
                    f"- Confidence: {impact['confidence']}",
                    "",
                    "## Direct Dependents",
                    "",
                ]
            )
            for item in impact["direct_dependents"]:
                body.append(
                    f"- `{item['source_node_path']}` via `{item['type']}` confidence `{item['confidence']}`"
                )
            body.extend(["", "## Affected Tests", ""])
            for item in impact["affected_tests"]:
                body.append(f"- `{item['path']}` confidence `{item.get('confidence')}`")
        return {
            "status": self._brief_status(),
            "format": "markdown",
            "report": "\n".join(body).strip() + "\n",
        }

    def add_runtime_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        saved = self.store.save_runtime_trace(trace)
        linked: dict[str, Any] = {}
        if saved.get("path"):
            linked["file_context"] = self.file_context(str(saved["path"]), limit=10)
        elif saved.get("symbol"):
            linked["symbol_context"] = self.symbol_context(str(saved["symbol"]), limit=10)
        elif saved.get("route") or saved.get("endpoint"):
            linked["route_context"] = self.route_context(str(saved.get("route") or saved.get("endpoint")), limit=10)
        return {"status": self._brief_status(), "trace": saved, "linked_context": linked}

    def runtime_traces(self, limit: int = 100) -> dict[str, Any]:
        return {"status": self._brief_status(), "traces": self.store.list_runtime_traces(limit=self._limit(limit, 500))}

    def export_index_archive(self, destination: str | None = None) -> dict[str, Any]:
        target = Path(destination).expanduser().resolve() if destination else self.store.repo_dir / f"{self.profile.repo_id}-export.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in ["profile.json", "manifest.json", "status.json", "index.sqlite"]:
                path = self.store.repo_dir / name
                if path.exists():
                    archive.write(path, arcname=name)
            report = self.export_report()["report"]
            archive.writestr("report.md", report)
        return {"status": self._brief_status(), "archive": str(target), "bytes": target.stat().st_size}

    def export_encrypted_archive(
        self,
        destination: str | None = None,
        passphrase: str | None = None,
    ) -> dict[str, Any]:
        plain = self.export_index_archive()
        plain_path = Path(plain["archive"])
        target = Path(destination).expanduser().resolve() if destination else plain_path.with_suffix(".zip.enc")
        encrypt_file(plain_path, target, passphrase=passphrase)
        return {
            "status": self._brief_status(),
            "encrypted_archive": str(target),
            "bytes": target.stat().st_size,
            "algorithm": "AES-256-CBC PBKDF2",
        }

    def decrypt_archive(
        self,
        encrypted_path: str,
        destination: str | None = None,
        passphrase: str | None = None,
    ) -> dict[str, Any]:
        source = Path(encrypted_path).expanduser().resolve()
        target = Path(destination).expanduser().resolve() if destination else source.with_suffix("")
        decrypt_file(source, target, passphrase=passphrase)
        return {"decrypted_archive": str(target), "bytes": target.stat().st_size}

    def lock_index(self, passphrase: str | None = None) -> dict[str, Any]:
        vault_dir = self.config.home / "vaults"
        vault_dir.mkdir(parents=True, exist_ok=True)
        target = vault_dir / f"{self.profile.repo_id}.zip.enc"
        encrypted = self.export_encrypted_archive(destination=str(target), passphrase=passphrase)
        if self.store.repo_dir.exists():
            shutil.rmtree(self.store.repo_dir)
        return {
            "repo_id": self.profile.repo_id,
            "repo_name": self.profile.repo_name,
            "locked": True,
            "encrypted_archive": encrypted["encrypted_archive"],
            "algorithm": encrypted["algorithm"],
        }

    def unlock_index(self, passphrase: str | None = None, encrypted_path: str | None = None) -> dict[str, Any]:
        source = Path(encrypted_path).expanduser().resolve() if encrypted_path else self.config.home / "vaults" / f"{self.profile.repo_id}.zip.enc"
        if not source.exists():
            raise FileNotFoundError(f"encrypted archive not found: {source}")
        temp_zip = self.config.home / "vaults" / f"{self.profile.repo_id}.zip"
        decrypt_file(source, temp_zip, passphrase=passphrase)
        try:
            self.store.repo_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(temp_zip, "r") as archive:
                self._extract_zip_safely(archive, self.store.repo_dir)
        finally:
            temp_zip.unlink(missing_ok=True)
        return {
            "repo_id": self.profile.repo_id,
            "repo_name": self.profile.repo_name,
            "unlocked": True,
            "repo_dir": str(self.store.repo_dir),
        }

    def delete_index(self, remove_files: bool = True) -> dict[str, Any]:
        self.store.delete_repository_index()
        if remove_files and self.store.repo_dir.exists():
            shutil.rmtree(self.store.repo_dir)
        return {
            "repo_id": self.profile.repo_id,
            "repo_name": self.profile.repo_name,
            "deleted": True,
            "removed_files": remove_files,
        }

    def _extract_zip_safely(self, archive: zipfile.ZipFile, destination: Path) -> None:
        root = destination.resolve()
        for member in archive.infolist():
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"refusing to extract symlink from archive: {member.filename}")
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"refusing to extract archive path outside index directory: {member.filename}")
        archive.extractall(root)

    def _heuristic_tests(self, target: str | None, files: list[str], limit: int) -> list[dict[str, Any]]:
        tokens = [Path(path).stem.lower().replace("test_", "") for path in files]
        if target:
            tokens.append(Path(target).stem.lower())
        tokens = [token for token in tokens if token]
        if not tokens:
            return []
        clauses = " OR ".join(["lower(path) LIKE ? OR lower(name) LIKE ?" for _ in tokens])
        params: list[Any] = [self.profile.repo_id]
        for token in tokens:
            params.extend([f"%{token}%", f"%{token}%"])
        params.append(limit)
        rows = self.store.query(
            f"""
            SELECT * FROM nodes
            WHERE repo_id = ? AND type = 'TestCase' AND ({clauses})
            ORDER BY confidence DESC, path, name
            LIMIT ?
            """,
            tuple(params),
        )
        return [row_dict(row) | {"reason": "heuristic test name/path match"} for row in rows]

    def _tests_for_node_ids(self, node_ids: list[str], limit: int) -> list[dict[str, Any]]:
        if not node_ids:
            rows = self.store.query(
                """
                SELECT * FROM nodes
                WHERE repo_id = ? AND type = 'TestCase'
                ORDER BY path, name
                LIMIT ?
                """,
                (self.profile.repo_id, limit),
            )
            return [row_dict(row) | {"reason": "available indexed test"} for row in rows]

        bind_marks = ",".join("?" for _ in node_ids)
        rows = self.store.query(
            f"""
            SELECT n.*, e.reason AS relationship_reason, e.confidence AS relationship_confidence
            FROM edges e
            JOIN nodes n ON n.id = e.source_id
            WHERE e.repo_id = ? AND e.type = 'TESTS' AND e.target_id IN ({bind_marks})
            ORDER BY e.confidence DESC, n.path, n.name
            LIMIT ?
            """,
            tuple([self.profile.repo_id, *node_ids, limit]),
        )
        return [row_dict(row) for row in rows]

    def _test_dependents(self, impacted: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        tests: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in impacted:
            path = item.get("source_node_path") or item.get("source_path") or ""
            source_type = item.get("source_type")
            path_parts = [part.lower() for part in Path(path).parts]
            if source_type != "TestCase" and not any("test" in part for part in path_parts) and not Path(path).name.startswith("test_"):
                continue
            key = item.get("source_id") or path
            if key in seen:
                continue
            seen.add(key)
            tests.append(
                {
                    "id": item.get("source_id"),
                    "type": source_type,
                    "name": item.get("source_name"),
                    "path": path,
                    "confidence": item.get("confidence"),
                    "reason": item.get("reason") or "test dependent imports impacted target",
                }
            )
            if len(tests) >= limit:
                break
        return tests

    def _find_targets(self, target: str, target_type: str, limit: int) -> list[Any]:
        normalized = target.replace("\\", "/").lstrip("./")
        if target_type == "file":
            return self.store.query(
                "SELECT * FROM nodes WHERE repo_id = ? AND type = 'File' AND path = ? LIMIT ?",
                (self.profile.repo_id, normalized, limit),
            )
        if target_type == "route":
            return self.store.query(
                "SELECT * FROM nodes WHERE repo_id = ? AND type IN ('Route', 'Endpoint') AND name LIKE ? LIMIT ?",
                (self.profile.repo_id, f"%{target}%", limit),
            )
        if target_type == "config":
            return self.store.query(
                "SELECT * FROM nodes WHERE repo_id = ? AND type IN ('ConfigKey', 'EnvironmentVariable') AND name LIKE ? LIMIT ?",
                (self.profile.repo_id, f"%{target}%", limit),
            )
        rows = self.store.query(
            """
            SELECT * FROM nodes
            WHERE repo_id = ? AND (path = ? OR name = ? OR name LIKE ?)
            ORDER BY CASE WHEN path = ? OR name = ? THEN 0 ELSE 1 END, confidence DESC
            LIMIT ?
            """,
            (self.profile.repo_id, normalized, target, f"%{target}%", normalized, target, limit),
        )
        return rows

    def _edges_for_ids(self, ids: list[str], limit: int) -> list[dict[str, Any]]:
        if not ids:
            return []
        bind_marks = ",".join("?" for _ in ids)
        rows = self.store.query(
            f"""
            SELECT e.*,
                   source.type AS source_type,
                   source.name AS source_name,
                   source.path AS source_node_path,
                   target.type AS target_type,
                   target.name AS target_name,
                   target.path AS target_node_path
            FROM edges e
            LEFT JOIN nodes source ON source.id = e.source_id
            LEFT JOIN nodes target ON target.id = e.target_id
            WHERE e.repo_id = ? AND (e.source_id IN ({bind_marks}) OR e.target_id IN ({bind_marks}))
            ORDER BY e.confidence DESC, e.type
            LIMIT ?
            """,
            tuple([self.profile.repo_id, *ids, *ids, limit]),
        )
        return [row_dict(row) for row in rows]

    def _git_changed_files(self) -> list[str]:
        try:
            completed = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.profile.path,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        if completed.returncode != 0:
            return []
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    def _brief_status(self) -> dict[str, Any]:
        status = self.status()
        return {
            "repo_id": status.get("repo_id"),
            "repo_name": status.get("repo_name"),
            "indexed": status.get("indexed", False),
            "stale": status.get("stale", True),
            "stale_reasons": status.get("stale_reasons", [])[:3],
        }

    def _risk(self, impacted: list[dict[str, Any]]) -> str:
        direct = sum(1 for item in impacted if item["depth"] == 1)
        total = len(impacted)
        if total >= 25 or direct >= 10:
            return "high"
        if total >= 8 or direct >= 3:
            return "medium"
        if total:
            return "low"
        return "unknown"

    def _average_confidence(self, impacted: list[dict[str, Any]]) -> float:
        if not impacted:
            return 0.0
        return round(sum(float(item["confidence"]) for item in impacted) / len(impacted), 2)

    def _verification_steps(self, risk: str, tests: list[dict[str, Any]]) -> list[str]:
        steps = ["Review listed source paths before editing."]
        if tests:
            steps.append("Run the affected tests listed in this report.")
        else:
            steps.append("No direct tests were linked; inspect nearby test folders manually.")
        if risk in {"medium", "high"}:
            steps.append("Run broader module or integration tests before handoff.")
        if self._brief_status().get("stale"):
            steps.append("Refresh the AlosAtlas index before relying on this report.")
        return steps

    def _limit(self, value: int, maximum: int = 50) -> int:
        return max(1, min(int(value), maximum))


def list_repositories(config: AlosAtlasConfig) -> list[dict[str, Any]]:
    return [asdict(profile) for profile in config.list_profiles()]


def queries_for(config: AlosAtlasConfig, repo: str) -> AlosAtlasQueries:
    return AlosAtlasQueries(config, config.get_profile(repo))
