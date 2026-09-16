from __future__ import annotations

import json
from pathlib import Path


def detect_test_command(workspace: Path) -> str | None:
    """Return a conservative project test command based on repository metadata."""
    if (workspace / "pyproject.toml").exists() or (workspace / "pytest.ini").exists() or (workspace / "tests").is_dir():
        return "python -m pytest -q"
    if (workspace / "package.json").is_file():
        try:
            package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
            if "test" in package.get("scripts", {}):
                return "npm test"
        except (OSError, ValueError):
            pass
    if (workspace / "Cargo.toml").exists():
        return "cargo test"
    if (workspace / "go.mod").exists():
        return "go test ./..."
    return None

