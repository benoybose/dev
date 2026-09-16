from __future__ import annotations

import re
from pathlib import Path

MENTION_PATTERN = re.compile(r"(?<!\w)@([A-Za-z0-9._~\\/ -]+?)(?=\s|$|[,;:!?])")


def parse_file_mentions(text: str, workspace: Path | None = None) -> tuple[str, list[Path], list[str]]:
    root = (workspace or Path.cwd()).resolve()
    files: list[Path] = []
    missing: list[str] = []
    for match in MENTION_PATTERN.finditer(text):
        raw = match.group(1).rstrip()
        path = Path(raw).expanduser()
        resolved = (path if path.is_absolute() else root / path).resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError:
            missing.append(raw)
            continue
        if resolved.exists():
            if resolved not in files:
                files.append(resolved)
        else:
            missing.append(raw)
    cleaned = MENTION_PATTERN.sub(lambda m: f"[file:{m.group(1).rstrip()}]", text)
    return cleaned, files, missing

