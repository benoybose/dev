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
    session_db: Path = field(default_factory=lambda: Path.home() / ".devx" / "sessions.db")
    cache_db: Path = field(default_factory=lambda: Path.home() / ".devx" / "cache.db")
    approval_required: bool = True
    max_iterations: int = 8
    max_tool_calls: int = 40
    command_timeout: float = 120.0
    test_command: str = ""
    max_file_bytes: int = 1_000_000
    embeddings_enabled: bool = False
    tracing_enabled: bool = False

    @classmethod
    def load(cls, *, workspace: Path | None = None) -> Settings:
        config_path = Path.home() / ".devx" / "config.env"
        if not config_path.is_file():
            legacy_path = Path.home() / ".dev" / "config.env"
            if legacy_path.is_file():
                config_path = legacy_path
        file_values = _load_env_file(config_path)

        def get(name: str, default: str, legacy_name: str | None = None) -> str:
            val = os.getenv(name)
            if val is not None:
                return val
            if legacy_name:
                legacy_val = os.getenv(legacy_name)
                if legacy_val is not None:
                    return legacy_val
            if name in file_values:
                return file_values[name]
            if legacy_name and legacy_name in file_values:
                return file_values[legacy_name]
            return default

        def boolean(name: str, default: bool, legacy_name: str | None = None) -> bool:
            return get(name, str(default), legacy_name).lower() in {"1", "true", "yes", "on"}

        root = (workspace or Path(get("DEVX_WORKSPACE", str(Path.cwd()), "DEV_WORKSPACE"))).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Workspace does not exist: {root}")
        return cls(
            base_url=get("DEVX_BASE_URL", cls.base_url, "DEV_BASE_URL"),
            api_key=get("DEVX_API_KEY", cls.api_key, "DEV_API_KEY"),
            model=get("DEVX_MODEL", cls.model, "DEV_MODEL"),
            provider=get("DEVX_PROVIDER", cls.provider, "DEV_PROVIDER"),
            workspace=root,
            session_db=Path(get("DEVX_SESSION_DB", str(Path.home() / ".devx" / "sessions.db"), "DEV_SESSION_DB")).expanduser(),
            cache_db=Path(get("DEVX_CACHE_DB", str(Path.home() / ".devx" / "cache.db"), "DEV_CACHE_DB")).expanduser(),
            approval_required=boolean("DEVX_APPROVAL_REQUIRED", True, "DEV_APPROVAL_REQUIRED"),
            max_iterations=int(get("DEVX_MAX_ITERATIONS", "8", "DEV_MAX_ITERATIONS")),
            max_tool_calls=int(get("DEVX_MAX_TOOL_CALLS", "40", "DEV_MAX_TOOL_CALLS")),
            command_timeout=float(get("DEVX_COMMAND_TIMEOUT", "120", "DEV_COMMAND_TIMEOUT")),
            test_command=get("DEVX_TEST_COMMAND", "", "DEV_TEST_COMMAND"),
            max_file_bytes=int(get("DEVX_MAX_FILE_BYTES", "1000000", "DEV_MAX_FILE_BYTES")),
            embeddings_enabled=boolean("DEVX_EMBEDDINGS_ENABLED", False, "DEV_EMBEDDINGS_ENABLED"),
            tracing_enabled=boolean("LANGSMITH_TRACING", False),
        )

    def validate(self) -> None:
        if self.max_iterations < 1 or self.max_tool_calls < 1:
            raise ValueError("Iteration and tool-call limits must be positive")
        if self.command_timeout <= 0 or self.max_file_bytes <= 0:
            raise ValueError("Timeout and file-size limits must be positive")
