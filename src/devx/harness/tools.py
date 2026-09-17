from __future__ import annotations

import difflib
import os
import shutil
import subprocess  # nosec B404 - commands are tokenized, shell=False, approval-gated, and policy-validated.
import threading
import time
import uuid
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
    _preview_bytes = 12_000

    def __init__(self, policy: PermissionPolicy, *, max_bytes: int = 1_000_000, timeout: float = 120,
                 journal: ChangeJournal | None = None, run_id: str = "adhoc", cancellation: CancellationToken | None = None):
        self.policy, self.max_bytes, self.timeout = policy, max_bytes, timeout
        self.journal, self.run_id = journal, run_id
        self.cancellation = cancellation or CancellationToken()

    def requires_approval(self, action: str, target: str | Path) -> bool:
        """Return whether a configured policy still needs an approval callback."""
        return self.policy.requires_approval(action, target)

    def read(self, path: str | Path) -> ToolResult:
        target = self.policy.path(Path(path))
        try:
            with target.open("rb") as stream:
                data = stream.read(self.max_bytes)
            return ToolResult(True, data.decode("utf-8", errors="replace"))
        except (OSError, UnicodeError) as exc:
            return ToolResult(False, str(exc))

    def write(self, path: str | Path, content: str, *, approved: bool = False) -> ToolResult:
        target = self._approved_path(path, approved)
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_bytes:
            return ToolResult(False, f"Content exceeds the {self.max_bytes}-byte file limit")
        before = file_hash(target)
        backup = None
        if self.journal and target.exists():
            backup_dir = self.journal.db_path.parent / "backups" / self.run_id
            relative = target.relative_to(self.policy.workspace)
            backup = backup_dir / relative.parent / f"{relative.name}.{before}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(target, backup)
        temporary = target.with_name(f".{target.name}.devx-tmp-{uuid.uuid4().hex}")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(encoded)
            temporary.replace(target)
            if self.journal:
                self.journal.record(self.run_id, target, before, file_hash(target), approved, backup)
            return ToolResult(True, f"Wrote {target}")
        except (OSError, UnicodeError) as exc:
            return ToolResult(False, str(exc))
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def preview_write(self, path: str | Path, content: str) -> str:
        """Return a bounded unified diff for a proposed write without mutating files."""
        target = self.policy.path(Path(path))
        current = self._read_preview(target)
        proposed = content.encode("utf-8")[: self._preview_bytes].decode("utf-8", errors="replace")
        diff = difflib.unified_diff(
            current.splitlines(True),
            proposed.splitlines(True),
            fromfile=str(target),
            tofile=str(target),
        )
        return self._bound_text("".join(diff))

    def replace(self, path: str | Path, old: str, new: str, *, expected_hash: str | None = None,
                approved: bool = False) -> ToolResult:
        """Apply an exact, optimistic-concurrency-checked text replacement."""
        target = self._approved_path(path, approved)
        try:
            if target.stat().st_size > self.max_bytes:
                return ToolResult(False, f"File exceeds the {self.max_bytes}-byte file limit")
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
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

    def preview_replace(self, path: str | Path, old: str, new: str) -> str:
        """Return a bounded diff for an exact replacement proposal."""
        target = self.policy.path(Path(path))
        current = self._read_preview(target)
        proposed = current.replace(old, new, 1)
        diff = difflib.unified_diff(
            current.splitlines(True),
            proposed.splitlines(True),
            fromfile=str(target),
            tofile=str(target),
        )
        return self._bound_text("".join(diff))

    def search(self, query: str, path: str | Path = ".") -> ToolResult:
        target = self.policy.path(Path(path))
        try:
            output = bytearray()
            for candidate in target.rglob("*") if target.is_dir() else [target]:
                try:
                    candidate = self.policy.path(candidate)
                    if not candidate.is_file() or candidate.stat().st_size > self.max_bytes:
                        continue
                except (OSError, PermissionError):
                    continue
                try:
                    for number, line in enumerate(candidate.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if query.lower() in line.lower():
                            encoded = f"{candidate}:{number}:{line}\n".encode()
                            remaining = self.max_bytes - len(output)
                            if remaining <= 0:
                                return ToolResult(True, bytes(output).decode("utf-8", errors="replace"))
                            output.extend(encoded[:remaining])
                except OSError:
                    continue
            return ToolResult(True, bytes(output).decode("utf-8", errors="replace"))
        except OSError as exc:
            return ToolResult(False, str(exc))

    def git_diff(self) -> ToolResult:
        return self.run(["git", "diff", "--no-ext-diff", "--", "."], approved=True)

    def run(self, command: list[str] | str, *, approved: bool = False) -> ToolResult:
        try:
            # Validate the command first so dangerous commands still raise a
            # policy error, while preserving the historical ToolResult-based
            # response for an ordinary command that simply needs approval.
            args = self.policy.command(command, approved=True)
            if self.policy.requires_approval("shell", " ".join(args)) and not approved:
                return ToolResult(False, "Command requires explicit approval")
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(  # nosec B603
                args,
                cwd=self.policy.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            started = time.monotonic()
            output = bytearray()

            def drain_output() -> None:
                if process.stdout is None:
                    return
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        return
                    remaining = self.max_bytes - len(output)
                    if remaining > 0:
                        output.extend(chunk[:remaining])

            reader = threading.Thread(target=drain_output, daemon=True)
            reader.start()
            timed_out = False
            while process.poll() is None:
                if self.cancellation.cancelled:
                    self._terminate(process)
                    raise RunCancelled("Command cancelled")
                if time.monotonic() - started > self.timeout:
                    self._terminate(process)
                    timed_out = True
                    break
                time.sleep(0.02)
            process.wait()
            reader.join(timeout=1)
            if reader.is_alive() and process.stdout is not None:
                process.stdout.close()
                reader.join(timeout=1)
            text = bytes(output).decode("utf-8", errors="replace")
            if timed_out:
                bounded = ("Command timed out\n" + text).encode("utf-8")[:self.max_bytes].decode(
                    "utf-8", errors="replace"
                )
                return ToolResult(False, bounded, process.returncode)
            return ToolResult(process.returncode == 0, text, process.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(False, str(exc))

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)  # nosec B603 B607
            else:
                import signal

                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()

    def _approved_path(self, path: str | Path, approved: bool) -> Path:
        return self.policy.path(Path(path), write=True, approved=approved)

    def _read_preview(self, target: Path) -> str:
        try:
            with target.open("rb") as stream:
                return stream.read(self._preview_bytes).decode("utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _bound_text(self, value: str) -> str:
        return value.encode("utf-8")[: self._preview_bytes].decode("utf-8", errors="replace")

    @staticmethod
    def _args(command: list[str] | str) -> list[str]:
        import shlex
        return shlex.split(command, posix=False) if isinstance(command, str) else list(command)
