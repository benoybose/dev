from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path


class PermissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Approval:
    action: str
    target: str
    reason: str


class PermissionPolicy:
    def __init__(self, workspace: Path, approval_required: bool = True):
        self.workspace = workspace.resolve()
        self.approval_required = approval_required

    def path(self, path: Path, *, write: bool = False, approved: bool = False) -> Path:
        candidate = path.expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        candidate = candidate.resolve(strict=False)
        try:
            candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise PermissionError(f"Path is outside workspace: {candidate}") from exc
        if write and self.approval_required and not approved:
            raise PermissionError("Write requires explicit approval")
        return candidate

    def command(self, command: list[str] | str, *, approved: bool = False) -> list[str]:
        args = shlex.split(command, posix=os.name != "nt") if isinstance(command, str) else list(command)
        if not args:
            raise PermissionError("Empty command")
        if any(re.search(r"(?i)(^|[/\\])(?:format|diskpart|cipher|takeown|icacls)$", arg) for arg in args):
            raise PermissionError("System-level command is not permitted")
        if any(re.search(r"(?i)(^|\s)(del|erase|rm|rmdir|remove-item|shutdown|reboot)(\s|$)", arg) for arg in args):
            raise PermissionError("Destructive command is not permitted")
        if self.approval_required and not approved:
            raise PermissionError("Command requires explicit approval")
        return args
