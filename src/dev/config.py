from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    base_url: str = "http://localhost:4000/v1"
    api_key: str = "sk-placeholder"
    model: str = "gpt-4o"
    provider: str = "openai"
    workspace: Path = field(default_factory=Path.cwd)
    session_db: Path = field(default_factory=lambda: Path.home() / ".dev" / "sessions.db")
    cache_db: Path = field(default_factory=lambda: Path.home() / ".dev" / "cache.db")
    approval_required: bool = True
    max_iterations: int = 8
    max_tool_calls: int = 40
    command_timeout: float = 120.0
    test_command: str = ""
    max_file_bytes: int = 1_000_000
    embeddings_enabled: bool = False
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "dev" / "embeddings")
    embeddings_offline: bool = False
    tracing_enabled: bool = False

    @classmethod
    def load(cls, *, workspace: Path | None = None) -> Settings:
        file_values = _load_env_file(Path.home() / ".dev" / "config.env")
        def get(name: str, default: str) -> str:
            return os.getenv(name, file_values.get(name, default))
        def boolean(name: str, default: bool) -> bool:
            return get(name, str(default)).lower() in {"1", "true", "yes", "on"}
        root = (workspace or Path(get("DEV_WORKSPACE", str(Path.cwd())))).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Workspace does not exist: {root}")
        return cls(
            base_url=get("DEV_BASE_URL", cls.base_url), api_key=get("DEV_API_KEY", cls.api_key),
            model=get("DEV_MODEL", cls.model), provider=get("DEV_PROVIDER", cls.provider),
            workspace=root, session_db=Path(get("DEV_SESSION_DB", str(Path.home() / ".dev" / "sessions.db"))).expanduser(),
            cache_db=Path(get("DEV_CACHE_DB", str(Path.home() / ".dev" / "cache.db"))).expanduser(),
            approval_required=boolean("DEV_APPROVAL_REQUIRED", True),
            max_iterations=int(get("DEV_MAX_ITERATIONS", "8")),
            max_tool_calls=int(get("DEV_MAX_TOOL_CALLS", "40")),
            command_timeout=float(get("DEV_COMMAND_TIMEOUT", "120")),
            test_command=get("DEV_TEST_COMMAND", ""),
            max_file_bytes=int(get("DEV_MAX_FILE_BYTES", "1000000")),
            embeddings_enabled=boolean("DEV_EMBEDDINGS_ENABLED", False),
            embedding_model=get("DEV_EMBEDDING_MODEL", cls.embedding_model),
            embedding_cache_dir=Path(get("DEV_EMBEDDING_CACHE_DIR", str(Path.home() / ".cache" / "dev" / "embeddings"))).expanduser(),
            embeddings_offline=boolean("DEV_EMBEDDINGS_OFFLINE", False),
            tracing_enabled=boolean("LANGSMITH_TRACING", False),
        )

    def validate(self) -> None:
        if self.max_iterations < 1 or self.max_tool_calls < 1:
            raise ValueError("Iteration and tool-call limits must be positive")
        if self.command_timeout <= 0 or self.max_file_bytes <= 0:
            raise ValueError("Timeout and file-size limits must be positive")
