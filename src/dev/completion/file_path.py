from __future__ import annotations

from pathlib import Path

try:
    from prompt_toolkit.completion import Completer, Completion
except ImportError:  # pragma: no cover
    Completer = object


class FilePathCompleter(Completer):
    def __init__(self, workspace: Path | None = None, limit: int = 30):
        self.workspace, self.limit = (workspace or Path.cwd()).resolve(), limit

    def get_completions(self, document, complete_event):
        token = document.text_before_cursor.split()[-1] if document.text_before_cursor.split() else ""
        if not token.startswith("@"):
            return
        query = token[1:].replace("\\", "/")
        base = self.workspace / query.rsplit("/", 1)[0] if "/" in query else self.workspace
        try:
            base = base.resolve(strict=False)
            base.relative_to(self.workspace)
        except ValueError:
            return
        partial = query.rsplit("/", 1)[-1]
        if not base.is_dir():
            return
        prefix = query.rsplit("/", 1)[0] + "/" if "/" in query else ""
        for item in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if partial.lower() in item.name.lower():
                display = "@" + prefix + item.name + ("/" if item.is_dir() else "")
                yield Completion(display, start_position=-len(token))
