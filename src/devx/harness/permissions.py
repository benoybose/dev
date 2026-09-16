from __future__ import annotations

import os
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


SYSTEM_COMMANDS = {"format", "diskpart", "cipher", "takeown", "icacls"}
DESTRUCTIVE_COMMANDS = {"del", "erase", "rm", "rmdir", "remove-item", "shutdown", "reboot"}
CHAIN_OPERATORS = {"&&", "||", ";", "|", "&"}
SHELL_FLAGS = {"-c", "/c", "/k", "-command"}


def _get_command_verbs(args: list[str]) -> list[str]:
    verbs: list[str] = []
    expect_verb = True
    for i, token in enumerate(args):
        cleaned = token.strip("\"'")
        if not cleaned:
            continue
        if expect_verb:
            cmd = Path(cleaned).name.lower().removesuffix(".exe")
            verbs.append(cmd)
            expect_verb = False
        elif cleaned in CHAIN_OPERATORS or cleaned.lower() == "sudo":
            expect_verb = True
        elif cleaned.lower() in SHELL_FLAGS and i + 1 < len(args):
            sub_str = args[i + 1].strip("\"'")
            try:
                sub_args = shlex.split(sub_str, posix=os.name != "nt")
            except ValueError:
                sub_args = sub_str.split()
            verbs.extend(_get_command_verbs(sub_args))
    return verbs


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
        verbs = _get_command_verbs(args)
        if any(v in SYSTEM_COMMANDS for v in verbs):
            raise PermissionError("System-level command is not permitted")
        if any(v in DESTRUCTIVE_COMMANDS for v in verbs):
            raise PermissionError("Destructive command is not permitted")
        if self.approval_required and not approved:
            raise PermissionError("Command requires explicit approval")
        return args
