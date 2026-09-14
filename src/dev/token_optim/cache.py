from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path


def fingerprint_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(item) for item in paths), key=lambda item: str(item)):
        digest.update(str(path).encode())
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
    return digest.hexdigest()


class SemanticCache:
    """Optional cache; callers supply an embedder to avoid mandatory model downloads."""
    def __init__(self, db_path: Path, threshold: float = 0.95, embedder=None):
        self.db_path, self.threshold, self.embedder = Path(db_path).expanduser(), threshold, embedder
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, query TEXT, response TEXT, embedding TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(cache)")}
            if "embedding" not in columns:
                conn.execute("ALTER TABLE cache ADD COLUMN embedding TEXT")
            if "embedding_model" not in columns:
                conn.execute("ALTER TABLE cache ADD COLUMN embedding_model TEXT")

    @property
    def embedding_model(self) -> str:
        return str(getattr(self.embedder, "identity", "none"))

    def key(self, query: str, fingerprint: str = "") -> str:
        namespace = self.embedding_model
        return hashlib.sha256((namespace + "\0" + query.strip() + "\0" + fingerprint).encode()).hexdigest()

    def get(self, query: str, fingerprint: str = "") -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT response FROM cache WHERE key=?", (self.key(query, fingerprint),)).fetchone()
            if row:
                return row[0]
            if self.embedder is None:
                return None
            query_vector = self.embedder.embed([query])[0]
            for response, serialized in conn.execute("SELECT response,embedding FROM cache WHERE embedding IS NOT NULL AND embedding_model=?", (self.embedding_model,)):
                vector = json.loads(serialized)
                denominator = math.sqrt(sum(x * x for x in query_vector) * sum(x * x for x in vector))
                if denominator and sum(a * b for a, b in zip(query_vector, vector)) / denominator >= self.threshold:
                    return response
        return None

    def set(self, query: str, response: str, fingerprint: str = "") -> None:
        embedding = None
        if self.embedder is not None:
            embedding = json.dumps([float(value) for value in self.embedder.embed([query])[0]])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO cache(key,query,response,embedding,embedding_model) VALUES(?,?,?,?,?)",
                         (self.key(query, fingerprint), query, response, embedding, self.embedding_model))
