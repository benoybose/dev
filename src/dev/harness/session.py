from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = (db_path or Path.home() / ".dev" / "sessions.db").expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            if conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
                conn.execute("INSERT INTO schema_version VALUES (1)")
            conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, state TEXT NOT NULL, metadata TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS session_events (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, run_id TEXT NOT NULL,
                event TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, session_id: str | None, name: str, state: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
        sid = session_id or str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            old = conn.execute("SELECT created_at FROM sessions WHERE id=?", (sid,)).fetchone()
            created = old[0] if old else now
            conn.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                         (sid, name, created, now, json.dumps(state), json.dumps(metadata or {})))
        return sid

    def load(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id=? OR name=? LIMIT 1", (session_id, session_id)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "name": row["name"], "state": json.loads(row["state"]), "metadata": json.loads(row["metadata"]), "updated_at": row["updated_at"]}

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id,name,created_at,updated_at FROM sessions ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def delete(self, session_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM sessions WHERE id=? OR name=?", (session_id, session_id)).rowcount > 0

    def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO session_events(session_id,run_id,event) VALUES(?,?,?)",
                         (session_id, run_id, json.dumps(event, default=str)))

    def events(self, session_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT run_id,event,created_at FROM session_events WHERE session_id=?"
        args: tuple[Any, ...] = (session_id,)
        if run_id:
            query += " AND run_id=?"
            args += (run_id,)
        query += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [{"run_id": row[0], "event": json.loads(row[1]), "created_at": row[2]} for row in rows]
