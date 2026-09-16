from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Change:
    run_id: str
    path: str
    before_hash: str | None
    after_hash: str | None
    approved: bool
    backup_path: str | None = None


class ChangeJournal:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, path TEXT NOT NULL,
                before_hash TEXT, after_hash TEXT, approved INTEGER NOT NULL,
                backup_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(changes)")}
            if "backup_path" not in columns:
                conn.execute("ALTER TABLE changes ADD COLUMN backup_path TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def record(self, run_id: str, path: Path, before_hash: str | None, after_hash: str | None, approved: bool,
               backup_path: Path | None = None) -> Change:
        change = Change(run_id, str(path), before_hash, after_hash, approved, str(backup_path) if backup_path else None)
        with self._connect() as conn:
            conn.execute("INSERT INTO changes(run_id,path,before_hash,after_hash,approved,backup_path) VALUES(?,?,?,?,?,?)",
                         (run_id, change.path, before_hash, after_hash, int(approved), change.backup_path))
        return change

    def for_run(self, run_id: str) -> list[Change]:
        with self._connect() as conn:
            rows = conn.execute("SELECT run_id,path,before_hash,after_hash,approved,backup_path FROM changes WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [Change(row[0], row[1], row[2], row[3], bool(row[4]), row[5]) for row in rows]

    def rollback(self, run_id: str) -> list[str]:
        """Restore only files that still match the recorded post-change hash."""
        restored: list[str] = []
        for change in reversed(self.for_run(run_id)):
            target = Path(change.path)
            if file_hash(target) != change.after_hash:
                continue
            if change.backup_path:
                backup = Path(change.backup_path)
                if backup.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
                    restored.append(str(target))
            elif change.before_hash is None and target.exists():
                target.unlink()
                restored.append(str(target))
        return restored
