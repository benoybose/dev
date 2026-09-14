#!/usr/bin/env python3
"""Apply the repository's GitFlow semantic-version policy."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SEMVER = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)(?:\.(?P<patch>0|[1-9]\d*))?(?:[-.]?(?P<pre>[0-9A-Za-z.-]+))?$")
BRANCH_VERSION = re.compile(r"^(?:release|hotfix)/v?(\d+)(?:\.(\d+))(?:\.(\d+))?(?:[-.]([0-9A-Za-z.-]+))?$")


def normalize(version: str) -> tuple[int, int, int, str | None]:
    match = SEMVER.match(version.removeprefix("v"))
    if not match:
        raise ValueError(f"Invalid semantic version: {version}")
    return int(match["major"]), int(match["minor"]), int(match["patch"] or 0), match["pre"]


def version_for_branch(current: str, branch: str) -> str:
    major, minor, patch, pre = normalize(current)
    branch = branch.removeprefix("refs/heads/")
    match = BRANCH_VERSION.match(branch)
    if match:
        suffix = match.group(4)
        release = f"{int(match.group(1))}.{int(match.group(2))}.{int(match.group(3) or 0)}"
        return f"{release}-{suffix}" if suffix else release
    if branch == "develop":
        # Development versions advance the next minor line without changing the
        # stable version that is currently published from main.
        if pre and pre.startswith("dev"):
            return current
        return f"{major}.{minor + 1}.0-dev.0"
    if branch == "main":
        # Release/hotfix branches establish the version before merging to main.
        return f"{major}.{minor}.{patch}" if pre else current
    return current


def write_version(version: str, root: Path) -> None:
    pyproject = root / "pyproject.toml"
    init_file = root / "src" / "dev" / "__init__.py"
    pyproject_text = pyproject.read_text(encoding="utf-8")
    updated = re.sub(r'(?m)^version\s*=\s*"[^"]+"$', f'version = "{version}"', pyproject_text, count=1)
    if updated == pyproject_text:
        raise RuntimeError("Could not find project version in pyproject.toml")
    pyproject.write_text(updated, encoding="utf-8")
    init_text = init_file.read_text(encoding="utf-8")
    init_updated = re.sub(r'(?m)^__version__\s*=\s*"[^"]+"$', f'__version__ = "{version}"', init_text, count=1)
    if init_updated == init_text:
        raise RuntimeError("Could not find __version__ in src/dev/__init__.py")
    init_file.write_text(init_updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    current_text = (args.root / "pyproject.toml").read_text(encoding="utf-8")
    current = re.search(r'(?m)^version\s*=\s*"([^"]+)"$', current_text)
    if not current:
        raise SystemExit("Project version not found")
    target = version_for_branch(current.group(1), args.branch)
    print(target)
    if args.write and target != current.group(1):
        write_version(target, args.root)


if __name__ == "__main__":
    main()
