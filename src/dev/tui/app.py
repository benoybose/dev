from __future__ import annotations

try:
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Input, Label, RichLog, Static
except ImportError:  # pragma: no cover
    App = object


if App is not object:
    class ApprovalModal(ModalScreen):
        def __init__(self, request, done):
            super().__init__()
            self.request, self.done = request, done

        def compose(self) -> ComposeResult:
            with Vertical(id="approval-dialog"):
                yield Label(f"Approve {self.request.action}: {self.request.target}")
                yield Label(self.request.reason[:4000])
                yield Button("Approve", id="approve")
                yield Button("Deny", id="deny")
                yield Button("Cancel run", id="cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            from dev.harness.approval import ApprovalDecision
            decision = {"approve": ApprovalDecision.APPROVE, "deny": ApprovalDecision.DENY, "cancel": ApprovalDecision.CANCEL}[event.button.id]
            self.done(decision)
            self.dismiss(decision)

    class DevTUI(App):
        CSS_PATH = None

        def __init__(self, session_id: str | None = None):
            super().__init__()
            self.session_id = session_id or "default"
            self._cancellation = None

        def compose(self) -> ComposeResult:
            with Vertical():
                yield RichLog(id="chat-view", wrap=True)
                yield Input(placeholder="Enter a task... use @ to reference files", id="input-bar")
                yield Static("agent: idle", id="status-bar")

        def on_input_submitted(self, event: Input.Submitted) -> None:
            value = event.value.strip()
            event.input.value = ""
            if value == "/exit":
                self.exit()
            elif value == "/clear":
                self.query_one("#chat-view", RichLog).clear()
            elif value == "/help":
                self.query_one("#chat-view", RichLog).write("/help /session /agent /clear /rollback /cancel /exit")
            elif value == "/session":
                from dev.config import Settings
                from dev.harness.session import SessionStore
                sessions = SessionStore(Settings.load().session_db).list_sessions()
                self.query_one("#chat-view", RichLog).write("\n".join(f"{item['id'][:8]}  {item['name']}" for item in sessions) or "No saved sessions.")
            elif value.startswith("/session "):
                self.session_id = value.partition(" ")[2].strip()
                self.query_one("#chat-view", RichLog).write(f"Switched to session: {self.session_id}")
            elif value.startswith("/agent"):
                self.query_one("#status-bar", Static).update(value.partition(" ")[2] or "agent: supervisor")
            elif value == "/cancel":
                if self._cancellation:
                    self._cancellation.cancel()
                    self.query_one("#chat-view", RichLog).write("Cancellation requested.")
            elif value == "/rollback":
                from dev.config import Settings
                from dev.harness.changes import ChangeJournal
                restored = ChangeJournal(Settings.load().session_db).rollback(self.session_id or "")
                self.query_one("#chat-view", RichLog).write("Restored: " + ", ".join(restored) if restored else "No safe changes to restore.")
            else:
                self.query_one("#chat-view", RichLog).write(f"> {value}")
                self.run_worker(self._ask(value), exclusive=False)

        async def _ask(self, value: str) -> None:
            from dev.agents.graph import build_supervisor_graph
            from dev.completion.parser import parse_file_mentions
            from dev.config import Settings
            from dev.harness.approval import ApprovalDecision, ApprovalManager, ApprovalRequest
            from dev.harness.runtime import CancellationToken
            from dev.harness.session import SessionStore
            settings = Settings.load()
            store = SessionStore(settings.session_db)
            previous = store.load(self.session_id)
            self._cancellation = CancellationToken()
            cleaned, files, missing = parse_file_mentions(value, settings.workspace)
            log = self.query_one("#chat-view", RichLog)
            if missing:
                log.write("Unknown mentions: " + ", ".join(missing))
                return
            try:
                import threading
                def ask_approval(action: str, target: str, reason: str = "") -> ApprovalDecision:
                    completed = threading.Event()
                    answer = {"value": ApprovalDecision.DENY}
                    request = ApprovalRequest("tui", action, target, reason)
                    def finish(decision):
                        answer["value"] = decision
                        completed.set()
                    self.call_from_thread(self.push_screen, ApprovalModal(request, finish))
                    completed.wait()
                    return answer["value"]
                def approval_handler(request: ApprovalRequest) -> ApprovalDecision:
                    return ask_approval(request.action, request.target, request.reason)
                def event_sink(event):
                    self.call_from_thread(self.query_one("#status-bar", Static).update, f"agent: {event.get('agent', event.get('type', 'running'))}")
                initial = {"task": cleaned, "messages": previous["state"].get("messages", []) if previous else [],
                           "events": previous["state"].get("events", []) if previous else [],
                           "iteration": previous["state"].get("iteration", 0) if previous else 0}
                result = await build_supervisor_graph(settings, ApprovalManager(approval_handler), [str(path) for path in files],
                                                      cancellation=self._cancellation, event_sink=event_sink,
                                                      session_id=self.session_id).ainvoke(initial)
                store.save(previous["id"] if previous else self.session_id, self.session_id, result)
                log.write(result["result"])
            except (OSError, RuntimeError, ValueError) as exc:
                log.write(f"Agent error: {exc}")
else:
    class DevTUI:  # pragma: no cover
        def __init__(self, session_id=None): self.session_id = session_id
        def run(self): raise RuntimeError("Install the TUI extra: pip install 'dev-coding-agent[tui]'")
