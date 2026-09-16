from __future__ import annotations

import difflib
import os
import subprocess  # nosec B404 - commands are tokenized, shell=False, approval-gated, and policy-validated.
import time
from dataclasses import dataclass
from pathlib import Path

from devx.harness.changes import ChangeJournal, file_hash
from devx.harness.permissions import PermissionError, PermissionPolicy
from devx.harness.runtime import CancellationToken, RunCancelled


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str
    exit_code: int | None = None


class WorkspaceTools:
    def __init__(self, policy: PermissionPolicy, *, max_bytes: int = 1_000_000, timeout: float = 120,
                 journal: ChangeJournal | None = None, run_id: str = "adhoc", cancellation: CancellationToken | None = None):
        self.policy, self.max_bytes, self.timeout = policy, max_bytes, timeout
        self.journal, self.run_id = journal, run_id
        self.cancellation = cancellation or CancellationToken()

    def read(self, path: str | Path) -> ToolResult:
        target = self.policy.path(Path(path))
        try:
            data = target.read_text(encoding="utf-8", errors="replace")
            return ToolResult(True, data[:self.max_bytes])
        except OSError as exc:
            return ToolResult(False, str(exc))

    def write(self, path: str | Path, content: str, *, approved: bool = False) -> ToolResult:
        target = self._approved_path(path, approved)
        before = file_hash(target)
        backup = None
        if self.journal and target.exists():
            backup_dir = self.journal.db_path.parent / "backups" / self.run_id
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"{target.name}.{before}"
            if not backup.exists():
                backup.write_bytes(target.read_bytes())
        temporary = target.with_name(f".{target.name}.devx-tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)
            if self.journal:
                self.journal.record(self.run_id, target, before, file_hash(target), approved, backup)
            return ToolResult(True, f"Wrote {target}")
        except OSError as exc:
            return ToolResult(False, str(exc))
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def replace(self, path: str | Path, old: str, new: str, *, expected_hash: str | None = None,
                approved: bool = False) -> ToolResult:
        """Apply an exact, optimistic-concurrency-checked text replacement."""
        target = self._approved_path(path, approved)
        try:
            current = target.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(False, str(exc))
        current_hash = file_hash(target)
        if expected_hash is not None and current_hash != expected_hash:
            return ToolResult(False, "CONFLICT: file changed since it was inspected")
        if old not in current:
            return ToolResult(False, "PATCH FAILED: expected text was not found")
        if current.count(old) != 1:
            return ToolResult(False, "PATCH FAILED: expected text is not unique")
        preview = "".join(difflib.unified_diff(current.splitlines(True), current.replace(old, new).splitlines(True), fromfile=str(target), tofile=str(target)))
        result = self.write(target, current.replace(old, new), approved=approved)
        return ToolResult(result.ok, (preview + "\n" + result.output)[:self.max_bytes], result.exit_code)

    def search(self, query: str, path: str | Path = ".") -> ToolResult:
        target = self.policy.path(Path(path))
        try:
            matches: list[str] = []
            for candidate in target.rglob("*") if target.is_dir() else [target]:
                if not candidate.is_file() or candidate.stat().st_size > self.max_bytes:
                    continue
                try:
                    for number, line in enumerate(candidate.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if query.lower() in line.lower():
                            matches.append(f"{candidate}:{number}:{line}")
                except OSError:
                    continue
            return ToolResult(True, "\n".join(matches)[:self.max_bytes])
        except OSError as exc:
            return ToolResult(False, str(exc))

    def git_diff(self) -> ToolResult:
        return self.run(["git", "diff", "--no-ext-diff", "--", "."], approved=True)

    def run(self, command: list[str] | str, *, approved: bool = False) -> ToolResult:
        if self.policy.approval_required and not approved:
            return ToolResult(False, "Command requires explicit approval")
        try:
            args = self.policy.command(command, approved=approved)
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(args, cwd=self.policy.workspace, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,  # nosec B603
                                       text=True, creationflags=creationflags)
            started = time.monotonic()
            chunks: list[str] = []
            while process.poll() is None:
                if self.cancellation.cancelled:
                    self._terminate(process)
                    raise RunCancelled("Command cancelled")
                if time.monotonic() - started > self.timeout:
                    self._terminate(process)
                    return ToolResult(False, "Command timed out", None)
                try:
                    output, _ = process.communicate(timeout=0.05)
                    chunks.append(output or "")
                except subprocess.TimeoutExpired as exc:
                    if exc.output:
                        chunks.append(exc.output if isinstance(exc.output, str) else exc.output.decode(errors="replace"))
                time.sleep(0.02)
            output, _ = process.communicate()
            if output:
                chunks.append(output)
            output = "".join(chunks)[:self.max_bytes]
            return ToolResult(process.returncode == 0, output, process.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(False, str(exc))

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)  # nosec B603 B607
            else:
                process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()

    def _approved_path(self, path: str | Path, approved: bool) -> Path:
        if self.policy.approval_required and not approved:
            raise PermissionError("Write requires explicit approval")
        return self.policy.path(Path(path), write=True, approved=approved)

    @staticmethod
    def _args(command: list[str] | str) -> list[str]:
        import shlex
        return shlex.split(command, posix=False) if isinstance(command, str) else list(command)
