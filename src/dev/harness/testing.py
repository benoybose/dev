from __future__ import annotations

import json
from pathlib import Path


def detect_test_command(workspace: Path) -> str | None:
    """Return a conservative test command based on project metadata.

    Commands are selected from repository markers only; user configuration
    remains authoritative through ``DEV_TEST_COMMAND``. The returned command
    is later passed through the normal approval and command-policy gates.
    """
    if ((workspace / "pyproject.toml").exists() or (workspace / "pytest.ini").exists()
            or (workspace / "tox.ini").exists() or (workspace / "noxfile.py").exists()
            or (workspace / "tests").is_dir()):
        return "python -m pytest -q"
    if (workspace / "package.json").is_file():
        try:
            package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
            if "test" in package.get("scripts", {}):
                if (workspace / "pnpm-lock.yaml").is_file():
                    return "pnpm test"
                if (workspace / "yarn.lock").is_file():
                    return "yarn test"
                if (workspace / "bun.lockb").is_file() or (workspace / "bun.lock").is_file():
                    return "bun test"
                return "npm test"
        except (OSError, ValueError):
            pass
    if (workspace / "Makefile").is_file():
        try:
            makefile = (workspace / "Makefile").read_text(encoding="utf-8")
            if any(line.startswith("test:") for line in makefile.splitlines()):
                return "make test"
        except OSError:
            pass
    if (workspace / "Cargo.toml").exists():
        return "cargo test"
    if (workspace / "go.mod").exists():
        return "go test ./..."
    return None
