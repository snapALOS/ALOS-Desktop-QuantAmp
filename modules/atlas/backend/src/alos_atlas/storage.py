"""SQLite storage for AlosAtlas indexes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import AlosAtlasConfig, utc_now
from .models import Edge, FileRecord, Node, RepositoryProfile


def _hash_parts(*parts: object) -> str:
    text = "\x1f".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def node_id(node: Node) -> str:
    return node.id or _hash_parts(
        "node",
        node.repo_id,
        node.type,
        node.path,
        node.name,
        node.start_line,
        node.signature,
    )


def edge_id(edge: Edge) -> str:
    return edge.id or _hash_parts(
        "edge",
        edge.repo_id,
        edge.source_id,
        edge.target_id,
        edge.type,
        edge.source_path,
        edge.source_line,
    )


class IndexStore:
    def __init__(self, config: AlosAtlasConfig, profile: RepositoryProfile) -> None:
        self.config = config
        self.profile = profile
        self.repo_dir = config.repo_dir(profile.repo_id)
        self.db_path = self.repo_dir / "index.sqlite"

    def connect(self) -> sqlite3.Connection:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = OFF")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS repositories (
                    repo_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    source_revision TEXT,
                    last_indexed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS files (
                    repo_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    file_class TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    indexed INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    PRIMARY KEY (repo_id, path)
                );

                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    start_line INTEGER,
                    end_line INTEGER,
                    language TEXT,
                    signature TEXT,
                    content_hash TEXT,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_repo_type_name
                    ON nodes(repo_id, type, name);
                CREATE INDEX IF NOT EXISTS idx_nodes_repo_path
                    ON nodes(repo_id, path);

                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_line INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_edges_source
                    ON edges(repo_id, source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target
                    ON edges(repo_id, target_id);
                CREATE INDEX IF NOT EXISTS idx_edges_type
                    ON edges(repo_id, type);

                CREATE TABLE IF NOT EXISTS search_index (
                    repo_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    PRIMARY KEY (repo_id, node_id, text)
                );

                CREATE TABLE IF NOT EXISTS index_runs (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    profile_hash TEXT NOT NULL,
                    files_scanned INTEGER DEFAULT 0,
                    files_indexed INTEGER DEFAULT 0,
                    files_skipped INTEGER DEFAULT 0,
                    parse_failures INTEGER DEFAULT 0,
                    node_count INTEGER DEFAULT 0,
                    edge_count INTEGER DEFAULT 0,
                    warnings TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS runtime_traces (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    path TEXT,
                    symbol TEXT,
                    route TEXT,
                    endpoint TEXT,
                    metadata TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runtime_traces_repo_type
                    ON runtime_traces(repo_id, event_type);
                """
            )

    def reset_index(self) -> None:
        self.initialize()
        with self.connect() as conn:
            for table in ["files", "nodes", "edges", "search_index"]:
                conn.execute(f"DELETE FROM {table} WHERE repo_id = ?", (self.profile.repo_id,))

    def save_repository(self, last_indexed_at: str, source_revision: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO repositories(repo_id, repo_name, repo_path, source_revision, last_indexed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repo_id) DO UPDATE SET
                    repo_name = excluded.repo_name,
                    repo_path = excluded.repo_path,
                    source_revision = excluded.source_revision,
                    last_indexed_at = excluded.last_indexed_at
                """,
                (
                    self.profile.repo_id,
                    self.profile.repo_name,
                    self.profile.repo_path,
                    source_revision,
                    last_indexed_at,
                ),
            )

    def save_files(self, files: Iterable[FileRecord]) -> None:
        rows = [
            (
                file.repo_id,
                file.path,
                file.absolute_path,
                file.language,
                file.file_class,
                file.size_bytes,
                file.content_hash,
                1 if file.indexed else 0,
                file.reason,
            )
            for file in files
        ]
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO files(repo_id, path, absolute_path, language, file_class, size_bytes,
                                  content_hash, indexed, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id, path) DO UPDATE SET
                    absolute_path = excluded.absolute_path,
                    language = excluded.language,
                    file_class = excluded.file_class,
                    size_bytes = excluded.size_bytes,
                    content_hash = excluded.content_hash,
                    indexed = excluded.indexed,
                    reason = excluded.reason
                """,
                rows,
            )

    def save_nodes_edges(
        self,
        nodes: Iterable[Node],
        edges: Iterable[Edge],
        search_text: Iterable[tuple[str, str, str]],
    ) -> None:
        now = utc_now()
        node_rows = []
        search_rows = []
        for node in nodes:
            nid = node_id(node)
            node.id = nid
            node_rows.append(
                (
                    nid,
                    node.repo_id,
                    node.type,
                    node.name,
                    node.path,
                    node.start_line,
                    node.end_line,
                    node.language,
                    node.signature,
                    node.content_hash,
                    node.confidence,
                    now,
                    now,
                )
            )
            text = " ".join(
                item
                for item in [node.type, node.name, node.path, node.signature or ""]
                if item
            )
            search_rows.append((node.repo_id, nid, node.path, node.type, node.name, text))

        edge_rows = []
        for edge in edges:
            eid = edge_id(edge)
            edge.id = eid
            edge_rows.append(
                (
                    eid,
                    edge.repo_id,
                    edge.source_id,
                    edge.target_id,
                    edge.type,
                    edge.confidence,
                    edge.reason,
                    edge.source_path,
                    edge.source_line,
                    now,
                )
            )

        for repo_id, nid, text in search_text:
            search_rows.append((repo_id, nid, "", "text", "", text))

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO nodes(id, repo_id, type, name, path, start_line, end_line, language,
                                  signature, content_hash, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    path = excluded.path,
                    start_line = excluded.start_line,
                    end_line = excluded.end_line,
                    language = excluded.language,
                    signature = excluded.signature,
                    content_hash = excluded.content_hash,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                node_rows,
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO edges(id, repo_id, source_id, target_id, type,
                                             confidence, reason, source_path, source_line, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                edge_rows,
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO search_index(repo_id, node_id, path, type, name, text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                search_rows,
            )

    def delete_paths(self, paths: list[str]) -> list[str]:
        if not paths:
            return []
        self.initialize()
        bind_marks = ",".join("?" for _ in paths)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM nodes WHERE repo_id = ? AND path IN ({bind_marks})",
                tuple([self.profile.repo_id, *paths]),
            ).fetchall()
            node_ids = [row["id"] for row in rows]
            if node_ids:
                node_marks = ",".join("?" for _ in node_ids)
                conn.execute(
                    f"DELETE FROM edges WHERE repo_id = ? AND (source_id IN ({node_marks}) OR target_id IN ({node_marks}) OR source_path IN ({bind_marks}))",
                    tuple([self.profile.repo_id, *node_ids, *node_ids, *paths]),
                )
                conn.execute(
                    f"DELETE FROM search_index WHERE repo_id = ? AND node_id IN ({node_marks})",
                    tuple([self.profile.repo_id, *node_ids]),
                )
                conn.execute(
                    f"DELETE FROM nodes WHERE repo_id = ? AND id IN ({node_marks})",
                    tuple([self.profile.repo_id, *node_ids]),
                )
            conn.execute(
                f"DELETE FROM files WHERE repo_id = ? AND path IN ({bind_marks})",
                tuple([self.profile.repo_id, *paths]),
            )
        return node_ids

    def delete_edges_by_types(self, edge_types: list[str]) -> None:
        if not edge_types:
            return
        self.initialize()
        bind_marks = ",".join("?" for _ in edge_types)
        with self.connect() as conn:
            conn.execute(
                f"DELETE FROM edges WHERE repo_id = ? AND type IN ({bind_marks})",
                tuple([self.profile.repo_id, *edge_types]),
            )

    def all_nodes(self) -> list[Node]:
        rows = self.query(
            """
            SELECT id, repo_id, type, name, path, start_line, end_line, language,
                   signature, content_hash, confidence
            FROM nodes
            WHERE repo_id = ?
            """,
            (self.profile.repo_id,),
        )
        return [
            Node(
                id=row["id"],
                repo_id=row["repo_id"],
                type=row["type"],
                name=row["name"],
                path=row["path"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                language=row["language"],
                signature=row["signature"],
                content_hash=row["content_hash"],
                confidence=row["confidence"],
            )
            for row in rows
        ]

    def start_run(self, profile_hash: str) -> str:
        run_id = _hash_parts(self.profile.repo_id, utc_now(), profile_hash)[:24]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO index_runs(id, repo_id, started_at, profile_hash) VALUES (?, ?, ?, ?)",
                (run_id, self.profile.repo_id, utc_now(), profile_hash),
            )
        return run_id

    def finish_run(self, run_id: str, stats: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE index_runs
                SET finished_at = ?,
                    files_scanned = ?,
                    files_indexed = ?,
                    files_skipped = ?,
                    parse_failures = ?,
                    node_count = ?,
                    edge_count = ?,
                    warnings = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    stats.get("files_scanned", 0),
                    stats.get("files_indexed", 0),
                    stats.get("files_skipped", 0),
                    stats.get("parse_failures", 0),
                    stats.get("node_count", 0),
                    stats.get("edge_count", 0),
                    json.dumps(stats.get("warnings", [])),
                    run_id,
                ),
            )

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            return {
                "files": conn.execute(
                    "SELECT COUNT(*) FROM files WHERE repo_id = ?", (self.profile.repo_id,)
                ).fetchone()[0],
                "indexed_files": conn.execute(
                    "SELECT COUNT(*) FROM files WHERE repo_id = ? AND indexed = 1",
                    (self.profile.repo_id,),
                ).fetchone()[0],
                "nodes": conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE repo_id = ?", (self.profile.repo_id,)
                ).fetchone()[0],
                "edges": conn.execute(
                    "SELECT COUNT(*) FROM edges WHERE repo_id = ?", (self.profile.repo_id,)
                ).fetchone()[0],
            }

    def write_json_artifacts(self, manifest: list[dict[str, Any]], status: dict[str, Any]) -> None:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        (self.repo_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (self.repo_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (self.repo_dir / "profile.json").write_text(
            json.dumps(self.profile.to_dict(), indent=2), encoding="utf-8"
        )

    def read_status_file(self) -> dict[str, Any] | None:
        status_path = self.repo_dir / "status.json"
        if not status_path.exists():
            return None
        return json.loads(status_path.read_text(encoding="utf-8"))

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        self.initialize()
        with self.connect() as conn:
            return list(conn.execute(sql, params).fetchall())

    def delete_repository_index(self) -> None:
        self.initialize()
        with self.connect() as conn:
            for table in [
                "repositories",
                "files",
                "nodes",
                "edges",
                "search_index",
                "index_runs",
                "runtime_traces",
            ]:
                conn.execute(f"DELETE FROM {table} WHERE repo_id = ?", (self.profile.repo_id,))

    def save_runtime_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        observed_at = trace.get("observed_at") or utc_now()
        trace_id = trace.get("id") or _hash_parts(
            self.profile.repo_id,
            trace.get("event_type"),
            trace.get("label"),
            trace.get("path"),
            trace.get("symbol"),
            trace.get("route"),
            trace.get("endpoint"),
            observed_at,
        )
        row = {
            "id": trace_id,
            "repo_id": self.profile.repo_id,
            "event_type": str(trace.get("event_type") or "event"),
            "label": str(trace.get("label") or trace.get("event_type") or "event"),
            "path": trace.get("path"),
            "symbol": trace.get("symbol"),
            "route": trace.get("route"),
            "endpoint": trace.get("endpoint"),
            "metadata": trace.get("metadata") or {},
            "observed_at": observed_at,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_traces(
                    id, repo_id, event_type, label, path, symbol, route, endpoint, metadata, observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["repo_id"],
                    row["event_type"],
                    row["label"],
                    row["path"],
                    row["symbol"],
                    row["route"],
                    row["endpoint"],
                    json.dumps(row["metadata"], sort_keys=True),
                    row["observed_at"],
                ),
            )
        return row

    def list_runtime_traces(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.query(
            """
            SELECT *
            FROM runtime_traces
            WHERE repo_id = ?
            ORDER BY observed_at DESC
            LIMIT ?
            """,
            (self.profile.repo_id, limit),
        )
        results = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item["metadata"])
            except json.JSONDecodeError:
                item["metadata"] = {}
            results.append(item)
        return results
