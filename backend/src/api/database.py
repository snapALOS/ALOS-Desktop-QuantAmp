import sqlite3
import json
import os
import re
from datetime import datetime
from uuid import uuid4

from src.core.config import USER_DATA_DIR

DB_PATH = os.environ.get("ALOS_DB_PATH", str(USER_DATA_DIR / "alos_memory.db"))

def get_db_connection():
    """Get a connection to the ALOS database for internal auth logic."""
    return sqlite3.connect(DB_PATH)

_SECRET_PATTERNS = [
    re.compile(r"\b(nvapi-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{16,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{16,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
]
_REDACTION = "[REDACTED_SECRET]"
_MEMORY_TYPES = {
    "checkpoint",
    "execution_insight",
    "decision",
    "project_fact",
    "user_preference",
    "failure_pattern",
    "tool_result",
    "run_summary",
    "integration_note",
}


def _columns(cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _add_column_if_missing(cursor, table_name: str, column_name: str, definition: str) -> None:
    if column_name not in _columns(cursor, table_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _redact_memory_text(value) -> tuple[str, int]:
    text = str(value or "")
    total = 0
    for pattern in _SECRET_PATTERNS:
        def replacement(match):
            if match.re.pattern.lower().startswith("(?i)\\b(bearer"):
                return f"{match.group(1)}{_REDACTION}"
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}={_REDACTION}"
            return _REDACTION

        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


def _redact_memory_metadata(metadata) -> tuple[dict, int]:
    redacted = {}
    total = 0
    for key, value in (metadata or {}).items():
        if isinstance(value, dict):
            redacted_value, count = _redact_memory_metadata(value)
            redacted[str(key)] = redacted_value
            total += count
        elif isinstance(value, list):
            items = []
            for item in value:
                item_text, count = _redact_memory_text(item)
                items.append(item_text)
                total += count
            redacted[str(key)] = items
        else:
            text, count = _redact_memory_text(value)
            redacted[str(key)] = text
            total += count
    return redacted, total

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#6366f1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                state_json TEXT,
                project_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                objective TEXT,
                status TEXT NOT NULL,
                active_worker TEXT,
                error TEXT,
                token_total INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        ''')
        _add_column_if_missing(cursor, "agent_runs", "last_event_id", "TEXT")
        _add_column_if_missing(cursor, "agent_runs", "resume_state_json", "TEXT DEFAULT '{}'")
        _add_column_if_missing(cursor, "agent_runs", "cancellation_reason", "TEXT")
        _add_column_if_missing(cursor, "agent_runs", "cancelled_at", "TIMESTAMP")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS run_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                node TEXT,
                active_worker TEXT,
                payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        ''')
        _add_column_if_missing(cursor, "run_events", "active_worker", "TEXT")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS run_checkpoints (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                node TEXT,
                state_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_checkpoints_run ON run_checkpoints(run_id, sequence)")
        _add_column_if_missing(cursor, "chat_sessions", "project_id", "TEXT REFERENCES projects(id) ON DELETE SET NULL")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_idempotency (
                idempotency_key TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategic_memories (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL,
                source TEXT,
                confidence REAL NOT NULL,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategic_memories_session ON strategic_memories(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategic_memories_type ON strategic_memories(memory_type)")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scout_events (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT,
                module TEXT,
                run_id TEXT,
                session_id TEXT,
                payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scout_events_created ON scout_events(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scout_events_source ON scout_events(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scout_events_level ON scout_events(level)")
        conn.commit()

# ── Projects ─────────────────────────────────────────────────────────────────

def create_project(name: str, description: str = "", color: str = "#6366f1") -> dict:
    project_id = str(uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO projects (id, name, description, color) VALUES (?, ?, ?, ?)",
            (project_id, name.strip() or "New Project", description, color),
        )
        conn.commit()
    return {"id": project_id, "name": name, "description": description, "color": color}


def get_all_projects() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, color, created_at FROM projects ORDER BY created_at ASC")
        rows = cursor.fetchall()
        return [{"id": r[0], "name": r[1], "description": r[2], "color": r[3], "created_at": r[4]} for r in rows]


def update_project(project_id: str, name: str = None, description: str = None, color: str = None) -> bool:
    fields, values = [], []
    if name is not None:
        fields.append("name = ?"); values.append(name.strip() or "Project")
    if description is not None:
        fields.append("description = ?"); values.append(description)
    if color is not None:
        fields.append("color = ?"); values.append(color)
    if not fields:
        return False
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(project_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_project(project_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(project_id: str = None) -> dict:
    session_id = str(uuid4())
    title = "New Encounter"
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_sessions (id, title, state_json, project_id) VALUES (?, ?, ?, ?)",
            (session_id, title, json.dumps({}), project_id),
        )
        conn.commit()
    return {"id": session_id, "title": title, "project_id": project_id}


def get_all_sessions() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, created_at, project_id FROM chat_sessions ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
        return [{"id": r[0], "title": r[1], "created_at": r[2], "project_id": r[3]} for r in rows]


def assign_session_project(session_id: str, project_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_sessions SET project_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id, session_id),
        )
        conn.commit()

def get_session_state(session_id: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT state_json FROM chat_sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            try:
                state_data = json.loads(row[0])
                return state_data if isinstance(state_data, dict) else {}
            except Exception:
                return {}
        return {}

def update_session(session_id: str, state_dict: dict, title: str = None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if title:
             cursor.execute(
                "UPDATE chat_sessions SET state_json = ?, title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(state_dict), title, session_id)
            )
        else:
            cursor.execute(
                "UPDATE chat_sessions SET state_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(state_dict), session_id)
            )
        conn.commit()

def delete_session(session_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        conn.commit()


def create_run(session_id: str, objective: str, resume_state: dict = None) -> str:
    run_id = str(uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_runs (id, session_id, objective, status, resume_state_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, session_id, objective, "running", json.dumps(resume_state or {}))
        )
        conn.commit()
    return run_id


def update_run(
    run_id: str,
    *,
    status: str = None,
    active_worker: str = None,
    error: str = None,
    token_total: int = None,
    resume_state: dict = None,
    last_event_id: str = None,
    cancellation_reason: str = None,
):
    fields = ["updated_at = CURRENT_TIMESTAMP"]
    values = []
    if status:
        fields.append("status = ?")
        values.append(status)
        if status in {"completed", "cancelled", "failed", "stuck"}:
            fields.append("ended_at = CURRENT_TIMESTAMP")
        if status == "cancelled":
            fields.append("cancelled_at = CURRENT_TIMESTAMP")
    if active_worker is not None:
        fields.append("active_worker = ?")
        values.append(active_worker)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if token_total is not None:
        fields.append("token_total = ?")
        values.append(int(token_total))
    if resume_state is not None:
        fields.append("resume_state_json = ?")
        values.append(json.dumps(resume_state))
    if last_event_id is not None:
        fields.append("last_event_id = ?")
        values.append(last_event_id)
    if cancellation_reason is not None:
        fields.append("cancellation_reason = ?")
        values.append(cancellation_reason)
    values.append(run_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE agent_runs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()


def _run_from_row(row) -> dict:
    try:
        resume_state = json.loads(row[10] or "{}")
    except Exception:
        resume_state = {}
    return {
        "id": row[0],
        "session_id": row[1],
        "objective": row[2],
        "status": row[3],
        "active_worker": row[4],
        "error": row[5],
        "token_total": row[6],
        "started_at": row[7],
        "ended_at": row[8],
        "last_event_id": row[9],
        "resume_state": resume_state,
        "cancellation_reason": row[11],
        "cancelled_at": row[12],
    }


def get_recent_runs(session_id: str, limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, objective, status, active_worker, error, token_total,
                   started_at, ended_at, last_event_id, resume_state_json,
                   cancellation_reason, cancelled_at
            FROM agent_runs
            WHERE session_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (session_id, limit)
        )
        rows = cursor.fetchall()
        return [_run_from_row(row) for row in rows]


def get_run(run_id: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, objective, status, active_worker, error, token_total,
                   started_at, ended_at, last_event_id, resume_state_json,
                   cancellation_reason, cancelled_at
            FROM agent_runs
            WHERE id = ?
            """,
            (run_id,)
        )
        row = cursor.fetchone()
        return _run_from_row(row) if row else {}


def get_active_run_for_session(session_id: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, objective, status, active_worker, error, token_total,
                   started_at, ended_at, last_event_id, resume_state_json,
                   cancellation_reason, cancelled_at
            FROM agent_runs
            WHERE session_id = ? AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        return _run_from_row(row) if row else {}


def record_run_event(
    run_id: str,
    session_id: str,
    event_type: str,
    payload: dict = None,
    *,
    node: str = None,
    active_worker: str = None,
) -> dict:
    event_id = str(uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO run_events (id, run_id, session_id, event_type, node, active_worker, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, run_id, session_id, event_type, node, active_worker, json.dumps(payload or {}))
        )
        cursor.execute(
            "UPDATE agent_runs SET last_event_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (event_id, run_id)
        )
        conn.commit()
    return {
        "id": event_id,
        "run_id": run_id,
        "session_id": session_id,
        "event_type": event_type,
        "node": node,
        "active_worker": active_worker,
        "payload": payload or {},
        "created_at": None,
    }


def get_run_events(run_id: str, limit: int = 500) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, run_id, session_id, event_type, node, active_worker, payload_json, created_at
            FROM run_events
            WHERE run_id = ?
            ORDER BY created_at ASC, rowid ASC
            LIMIT ?
            """,
            (run_id, limit)
        )
        rows = cursor.fetchall()
        events = []
        for row in rows:
            try:
                payload = json.loads(row[6] or "{}")
            except Exception:
                payload = {}
            events.append({
                "id": row[0],
                "run_id": row[1],
                "session_id": row[2],
                "event_type": row[3],
                "node": row[4],
                "active_worker": row[5],
                "payload": payload,
                "created_at": row[7],
            })
        return events


def _safe_scout_payload(payload) -> dict:
    def redact_sensitive_keys(value):
        if isinstance(value, dict):
            redacted = {}
            for key, child in value.items():
                key_text = str(key)
                if re.search(r"(?i)(api[_-]?key|token|secret|password)", key_text):
                    redacted[key_text] = _REDACTION
                else:
                    redacted[key_text] = redact_sensitive_keys(child)
            return redacted
        if isinstance(value, list):
            return [redact_sensitive_keys(item) for item in value[:100]]
        return value

    if payload is None:
        return {}
    source = payload if isinstance(payload, dict) else {"value": payload}
    redacted, _ = _redact_memory_metadata(redact_sensitive_keys(source))
    encoded = json.dumps(redacted, default=str)
    max_chars = 60_000
    if len(encoded) <= max_chars:
        return redacted
    return {
        "truncated": True,
        "original_chars": len(encoded),
        "preview": encoded[:max_chars],
    }


def _scout_event_from_row(row) -> dict:
    try:
        payload = json.loads(row[8] or "{}")
    except Exception:
        payload = {}
    return {
        "id": row[0],
        "source": row[1],
        "level": row[2],
        "event_type": row[3],
        "message": row[4] or "",
        "module": row[5],
        "run_id": row[6],
        "session_id": row[7],
        "payload": payload,
        "created_at": row[9],
    }


def record_scout_event(
    *,
    source: str,
    level: str,
    event_type: str,
    message: str = "",
    module: str = None,
    run_id: str = None,
    session_id: str = None,
    payload: dict = None,
) -> dict:
    event_id = str(uuid4())
    safe_message, _ = _redact_memory_text(message or "")
    safe_payload = _safe_scout_payload(payload)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO scout_events
                (id, source, level, event_type, message, module, run_id, session_id, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                str(source or "unknown")[:120],
                str(level or "info").lower()[:40],
                str(event_type or "event")[:160],
                safe_message[:8_000],
                module,
                run_id,
                session_id,
                json.dumps(safe_payload, default=str),
            ),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT id, source, level, event_type, message, module, run_id, session_id, payload_json, created_at
            FROM scout_events
            WHERE id = ?
            """,
            (event_id,),
        )
        row = cursor.fetchone()
    return _scout_event_from_row(row)


def list_scout_events(
    *,
    limit: int = 500,
    source: str = None,
    level: str = None,
    module: str = None,
    run_id: str = None,
    session_id: str = None,
    q: str = None,
) -> list[dict]:
    limit = max(1, min(int(limit or 500), 2_000))
    clauses = []
    params = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if level:
        clauses.append("level = ?")
        params.append(level.lower())
    if module:
        clauses.append("module = ?")
        params.append(module)
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if q:
        clauses.append(
            "(source LIKE ? OR level LIKE ? OR event_type LIKE ? OR message LIKE ? OR module LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, source, level, event_type, message, module, run_id, session_id, payload_json, created_at
            FROM scout_events
            {where}
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        rows = cursor.fetchall()
    return [_scout_event_from_row(row) for row in rows]


def create_run_checkpoint(
    run_id: str,
    session_id: str,
    *,
    node: str = None,
    state: dict = None,
) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_checkpoints WHERE run_id = ?",
            (run_id,),
        )
        sequence = int(cursor.fetchone()[0] or 1)
        checkpoint_id = str(uuid4())
        cursor.execute(
            """
            INSERT INTO run_checkpoints (id, run_id, session_id, sequence, node, state_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (checkpoint_id, run_id, session_id, sequence, node, json.dumps(state or {}, default=str)),
        )
        conn.commit()
    return {
        "id": checkpoint_id,
        "run_id": run_id,
        "session_id": session_id,
        "sequence": sequence,
        "node": node,
        "state": state or {},
    }


def get_run_checkpoints(run_id: str, limit: int = 100) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, run_id, session_id, sequence, node, state_json, created_at
            FROM run_checkpoints
            WHERE run_id = ?
            ORDER BY sequence ASC
            LIMIT ?
            """,
            (run_id, limit),
        )
        rows = cursor.fetchall()
    checkpoints = []
    for row in rows:
        try:
            state = json.loads(row[5] or "{}")
        except Exception:
            state = {}
        checkpoints.append({
            "id": row[0],
            "run_id": row[1],
            "session_id": row[2],
            "sequence": row[3],
            "node": row[4],
            "state": state,
            "created_at": row[6],
        })
    return checkpoints


def get_tool_idempotency(idempotency_key: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT idempotency_key, run_id, session_id, tool_name, status, result_json, created_at
            FROM tool_idempotency
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()
    if not row:
        return {}
    try:
        result = json.loads(row[5] or "{}")
    except Exception:
        result = {}
    return {
        "idempotency_key": row[0],
        "run_id": row[1],
        "session_id": row[2],
        "tool_name": row[3],
        "status": row[4],
        "result": result,
        "created_at": row[6],
    }


def record_tool_idempotency(
    idempotency_key: str,
    run_id: str,
    session_id: str,
    tool_name: str,
    *,
    status: str,
    result: dict,
) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO tool_idempotency
                (idempotency_key, run_id, session_id, tool_name, status, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                idempotency_key,
                run_id,
                session_id,
                tool_name,
                status,
                json.dumps(result or {}, default=str),
            ),
        )
        conn.commit()
    return get_tool_idempotency(idempotency_key)


def record_strategic_memory(memory: dict) -> dict:
    memory = dict(memory or {})
    metadata, metadata_redactions = _redact_memory_metadata(memory.get("metadata") or {})
    content, content_redactions = _redact_memory_text(memory.get("content", ""))
    if content_redactions or metadata_redactions:
        metadata["redaction_count"] = str(content_redactions + metadata_redactions)
    memory_type = str(memory.get("memory_type") or "execution_insight")
    if memory_type not in _MEMORY_TYPES:
        memory_type = "execution_insight"
    memory.update({
        "memory_type": memory_type,
        "content": content,
        "metadata": metadata,
    })
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO strategic_memories
                (id, session_id, memory_type, content, importance, source, confidence, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory["id"],
                memory["session_id"],
                memory["memory_type"],
                memory["content"],
                float(memory.get("importance", 0.5)),
                memory.get("source", "system"),
                float(memory.get("confidence", 0.75)),
                json.dumps(memory.get("metadata") or {}),
                memory.get("created_at") or datetime.utcnow().isoformat(),
            )
        )
        conn.commit()
    return memory


def _memory_from_row(row) -> dict:
    try:
        metadata = json.loads(row[7] or "{}")
    except Exception:
        metadata = {}
    return {
        "id": row[0],
        "session_id": row[1],
        "memory_type": row[2],
        "content": row[3],
        "importance": row[4],
        "source": row[5],
        "confidence": row[6],
        "metadata": metadata,
        "created_at": row[8],
    }


def list_strategic_memories(
    *,
    session_id: str = None,
    memory_type: str = None,
    include_checkpoints: bool = True,
    limit: int = 500,
) -> list[dict]:
    clauses = []
    values = []
    if session_id:
        clauses.append("session_id = ?")
        values.append(session_id)
    if memory_type:
        clauses.append("memory_type = ?")
        values.append(memory_type)
    if not include_checkpoints:
        clauses.append("memory_type != 'checkpoint'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(int(limit))
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, session_id, memory_type, content, importance, source, confidence, metadata_json, created_at
            FROM strategic_memories
            {where}
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            values,
        )
        return [_memory_from_row(row) for row in cursor.fetchall()]


def clear_strategic_memories(session_id: str = None) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if session_id:
            cursor.execute("DELETE FROM strategic_memories WHERE session_id = ?", (session_id,))
        else:
            cursor.execute("DELETE FROM strategic_memories")
        conn.commit()


init_db()
