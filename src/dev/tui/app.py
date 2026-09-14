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

    class SecretInputModal(ModalScreen):
        def __init__(self, done):
            super().__init__()
            self.done = done

        def compose(self) -> ComposeResult:
            with Vertical(id="secret-dialog"):
                yield Label("Enter API key (input is masked; it will not be shown in the conversation)")
                yield Input(placeholder="API key", password=True, id="secret-input")
                yield Button("Save", id="save")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "save":
                value = self.query_one("#secret-input", Input).value
                self.done(value)
            self.dismiss()

    class DevTUI(App):
        CSS_PATH = None

        def __init__(self, session_id: str | None = None):
            super().__init__()
            self.session_id = session_id or "default"
            self._cancellation = None
            self._requested_agent = "supervisor"

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
                self.query_one("#chat-view", RichLog).write("/help /provider /model /api-key /config /session /agent /clear /rollback /cancel /exit")
            elif value == "/provider list":
                from dev.configuration import PROVIDERS
                names = ", ".join(sorted(PROVIDERS))
                self.query_one("#chat-view", RichLog).write("Providers: " + names)
            elif value.startswith("/provider use "):
                from dev.configuration import ConfigurationError, UserConfig
                provider = value.partition(" ")[2].partition(" ")[2].strip()
                try:
                    UserConfig().set_provider(provider)
                    self.query_one("#chat-view", RichLog).write(f"Provider saved: {provider}. New runs will use it.")
                except ConfigurationError as exc:
                    self.query_one("#chat-view", RichLog).write(str(exc))
            elif value == "/model list":
                from dev.config import Settings
                from dev.configuration import ConfigurationError, list_models
                settings = Settings.load()
                try:
                    models = list_models(settings.base_url, settings.api_key)
                    if not models:
                        self.query_one("#chat-view", RichLog).write("No models returned by the provider.")
                    else:
                        lines = [f"{item.identifier}"
                                 + (" [free]" if item.free else "")
                                 + (" [tools]" if item.tool_calling else "") for item in models[:100]]
                        self.query_one("#chat-view", RichLog).write("\n".join(lines))
                except ConfigurationError as exc:
                    self.query_one("#chat-view", RichLog).write(str(exc))
            elif value.startswith("/model use "):
                from dev.configuration import ConfigurationError, UserConfig
                model = value.partition(" ")[2].partition(" ")[2].strip()
                try:
                    UserConfig().set_model(model)
                    self.query_one("#chat-view", RichLog).write(f"Model saved: {model}. New runs will use it.")
                except ConfigurationError as exc:
                    self.query_one("#chat-view", RichLog).write(str(exc))
            elif value == "/api-key set":
                from dev.configuration import ConfigurationError, UserConfig
                def save_key(api_key: str) -> None:
                    try:
                        UserConfig().set_api_key(api_key)
                        self.query_one("#chat-view", RichLog).write("API key saved securely to the user configuration file.")
                    except ConfigurationError as exc:
                        self.query_one("#chat-view", RichLog).write(str(exc))
                self.push_screen(SecretInputModal(save_key))
            elif value == "/config show":
                from dev.config import Settings
                from dev.configuration import mask_secret
                settings = Settings.load()
                self.query_one("#chat-view", RichLog).write(
                    f"provider: {settings.provider}\nbase_url: {settings.base_url}\nmodel: {settings.model}\napi_key: {mask_secret(settings.api_key)}\nworkspace: {settings.workspace}"
                )
            elif value == "/config reload":
                from dev.config import Settings
                settings = Settings.load()
                self.query_one("#chat-view", RichLog).write(f"Configuration reloaded: {settings.provider} / {settings.model}")
            elif value == "/session":
                from dev.config import Settings
                from dev.harness.session import SessionStore
                sessions = SessionStore(Settings.load().session_db).list_sessions()
                self.query_one("#chat-view", RichLog).write("\n".join(f"{item['id'][:8]}  {item['name']}" for item in sessions) or "No saved sessions.")
            elif (value.startswith("/session ") and not value.startswith("/session rename ")
                  and not value.startswith("/session export ") and not value.startswith("/session import ")):
                self.session_id = value.partition(" ")[2].strip()
                self.query_one("#chat-view", RichLog).write(f"Switched to session: {self.session_id}")
            elif value.startswith("/agent"):
                requested = value.partition(" ")[2].strip() or "supervisor"
                if requested not in {"supervisor", "planner", "coder", "tester"}:
                    self.query_one("#chat-view", RichLog).write("Choose: supervisor, planner, coder, or tester")
                else:
                    self._requested_agent = requested
                    self.query_one("#status-bar", Static).update(f"agent: {requested}")
            elif value == "/cancel":
                if self._cancellation:
                    self._cancellation.cancel()
                    self.query_one("#chat-view", RichLog).write("Cancellation requested.")
            elif value == "/rollback":
                from dev.config import Settings
                from dev.harness.changes import ChangeJournal
                restored = ChangeJournal(Settings.load().session_db).rollback(self.session_id or "")
                self.query_one("#chat-view", RichLog).write("Restored: " + ", ".join(restored) if restored else "No safe changes to restore.")
            elif value.startswith("/session rename "):
                from dev.config import Settings
                from dev.harness.session import SessionStore
                name = value.partition(" ")[2].partition(" ")[2].strip()
                if SessionStore(Settings.load().session_db).rename(self.session_id, name):
                    self.session_id = name
                    self.query_one("#chat-view", RichLog).write(f"Renamed session to: {name}")
                else:
                    self.query_one("#chat-view", RichLog).write("Session not found.")
            elif value.startswith("/session export "):
                from dev.config import Settings
                from dev.harness.session import SessionStore
                destination = value.partition(" ")[2].partition(" ")[2].strip()
                try:
                    exported = SessionStore(Settings.load().session_db).export_session(self.session_id, destination)
                    self.query_one("#chat-view", RichLog).write(f"Exported session: {exported}")
                except (KeyError, OSError, ValueError) as exc:
                    self.query_one("#chat-view", RichLog).write(f"Export failed: {exc}")
            elif value.startswith("/session import "):
                from dev.config import Settings
                from dev.harness.session import SessionStore
                source = value.partition(" ")[2].partition(" ")[2].strip()
                try:
                    self.session_id = SessionStore(Settings.load().session_db).import_session(source)
                    self.query_one("#chat-view", RichLog).write(f"Imported session: {self.session_id}")
                except (OSError, TypeError, ValueError, KeyError) as exc:
                    self.query_one("#chat-view", RichLog).write(f"Import failed: {exc}")
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
                    if event.get("type") == "token":
                        self.call_from_thread(self.query_one("#chat-view", RichLog).write, event.get("text", ""))
                    else:
                        self.call_from_thread(self.query_one("#status-bar", Static).update, f"agent: {event.get('agent', event.get('type', 'running'))}")
                initial = {"task": cleaned, "messages": previous["state"].get("messages", []) if previous else [],
                           "events": previous["state"].get("events", []) if previous else [],
                           "iteration": previous["state"].get("iteration", 0) if previous else 0,
                           "requested_agent": self._requested_agent}
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
