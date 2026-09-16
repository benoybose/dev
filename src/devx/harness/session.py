from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            default_path = Path.home() / ".devx" / "sessions.db"
            legacy_path = Path.home() / ".dev" / "sessions.db"
            self.db_path = (legacy_path if not default_path.exists() and legacy_path.exists() else default_path).expanduser()
        else:
            self.db_path = Path(db_path).expanduser()
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
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
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

    def rename(self, session_id: str, name: str) -> bool:
        """Rename a saved session, returning whether it existed."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Session name must not be empty")
        with self._connect() as conn:
            return conn.execute("UPDATE sessions SET name=? WHERE id=? OR name=?",
                                (clean_name, session_id, session_id)).rowcount > 0

    def export_session(self, session_id: str, path: Path) -> Path:
        """Export one session and its event history as portable JSON."""
        session = self.load(session_id)
        if not session:
            raise KeyError(f"Session not found: {session_id}")
        payload = {"session": session, "events": self.events(session["id"])}
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return destination

    def import_session(self, path: Path, name: str | None = None) -> str:
        """Import a previously exported session and return its new session ID."""
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        source = payload.get("session")
        if not isinstance(source, dict) or not isinstance(source.get("state"), dict):
            raise TypeError("Invalid session export")
        sid = self.save(None, name or str(source.get("name", "imported")), source["state"], source.get("metadata", {}))
        for item in payload.get("events", []):
            event = item.get("event")
            if isinstance(event, dict):
                self.append_event(sid, str(item.get("run_id", sid)), event)
        return sid

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
