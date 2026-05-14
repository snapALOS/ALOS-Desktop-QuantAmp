from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .ids import now


class AlosCurrentStore:
    def __init__(self, home: Path | str | None = None) -> None:
        self.home = Path(home).expanduser().resolve() if home else (Path.home() / ".alos" / "current").resolve()
        self.db_path = self.home / "alos_current.sqlite"

    def connect(self) -> sqlite3.Connection:
        self.home.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_version_id TEXT,
                    draft_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_versions (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    graph_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    UNIQUE(workflow_id, version)
                );
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_node_id TEXT,
                    variables_json TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS execution_steps (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    error TEXT,
                    started_at TEXT,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    workflow_id TEXT,
                    execution_id TEXT,
                    node_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    delivery_status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT,
                    execution_id TEXT,
                    node_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    department_id TEXT,
                    assignee_id TEXT,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    acceptance_criteria TEXT NOT NULL,
                    due_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS departments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    head_id TEXT NOT NULL,
                    authority_tier INTEGER NOT NULL,
                    capabilities_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    department_id TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    available INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
        self.seed_swarm()

    def seed_swarm(self) -> None:
        departments = [
            ("operations", "Automation Operations", "dh_operations", 2, ["automation", "process", "monitoring"]),
            ("code", "Code Technical", "dh_code", 3, ["code", "testing", "architecture"]),
            ("research", "Research Intelligence", "dh_research", 2, ["research", "analysis", "sourcing"]),
            ("quality", "Quality Testing", "dh_quality", 2, ["qa", "validation", "testing"]),
            ("security", "Security Compliance", "dh_security", 3, ["security", "compliance", "risk"]),
        ]
        agents = [
            ("dh_operations", "Head of Automation Operations", "department_head", "operations", ["automation", "process"], 1),
            ("dh_code", "Head of Code Technical", "department_head", "code", ["code", "testing"], 1),
            ("dh_research", "Head of Research Intelligence", "department_head", "research", ["research", "analysis"], 1),
            ("dh_quality", "Head of Quality Testing", "department_head", "quality", ["qa", "validation"], 1),
            ("dh_security", "Head of Security Compliance", "department_head", "security", ["security", "compliance"], 1),
            ("agent_research_1", "Research Sub-Agent", "sub_agent", "research", ["research", "sourcing"], 1),
            ("agent_code_1", "Code Sub-Agent", "sub_agent", "code", ["code", "implementation"], 1),
            ("agent_qa_1", "QA Sub-Agent", "sub_agent", "quality", ["qa", "testing"], 1),
        ]
        with self.connect() as conn:
            for item in departments:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO departments(id, name, head_id, authority_tier, capabilities_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (item[0], item[1], item[2], item[3], json.dumps(item[4])),
                )
            for item in agents:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO agents(id, name, kind, department_id, capabilities_json, available)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item[0], item[1], item[2], item[3], json.dumps(item[4]), item[5]),
                )

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [self._decode(dict(row)) for row in conn.execute(sql, params).fetchall()]

    def row(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            result = conn.execute(sql, params).fetchone()
            return self._decode(dict(result)) if result else None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as conn:
            conn.execute(sql, params)

    def audit(self, audit_id: str, action: str, target_type: str, target_id: str, payload: dict[str, Any], actor: str = "local") -> None:
        self.execute(
            """
            INSERT INTO audit_log(id, action, actor, target_type, target_id, payload_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (audit_id, action, actor, target_type, target_id, json.dumps(payload), now()),
        )

    def _decode(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, value in row.items():
            if key.endswith("_json") and isinstance(value, str):
                decoded[key[:-5]] = json.loads(value)
            else:
                decoded[key] = value
        return decoded
