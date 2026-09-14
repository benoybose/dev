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

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "secret-input":
                self.done(event.value)
                self.dismiss()

    class DevTUI(App):
        CSS_PATH = None

        def __init__(self, session_id: str | None = None):
            super().__init__()
            self.session_id = session_id or "default"
            self._cancellation = None
            self._requested_agent = "supervisor"
            self._provider_choices: list[str] = []
            self._model_choices: list[str] = []

        def compose(self) -> ComposeResult:
            with Vertical():
                yield RichLog(id="chat-view", wrap=True)
                yield Input(placeholder="Enter a task... use @ to reference files", id="input-bar")
                yield Static("agent: idle", id="status-bar")

        def _write(self, message: str) -> None:
            self.query_one("#chat-view", RichLog).write(message)

        def _show_providers(self) -> None:
            from dev.configuration import PROVIDERS

            self._provider_choices = sorted(PROVIDERS)
            lines = ["Providers (use /provider <number> or /provider <name>):"]
            lines.extend(f"{index}. {name}" for index, name in enumerate(self._provider_choices, 1))
            self._write("\n".join(lines))

        def _select_provider(self, value: str) -> None:
            from dev.configuration import PROVIDERS, ConfigurationError, UserConfig

            value = value.strip()
            if value.isdigit():
                if not self._provider_choices:
                    self._provider_choices = sorted(PROVIDERS)
                index = int(value)
                if not 0 < index <= len(self._provider_choices):
                    self._write("Choose a provider number from the latest /provider list.")
                    return
                value = self._provider_choices[index - 1]
            try:
                UserConfig().set_provider(value)
                self._write(f"Provider saved: {value}. New runs will use it.")
            except ConfigurationError as exc:
                self._write(str(exc))

        def _show_models(self, filter_text: str = "") -> None:
            from dev.config import Settings
            from dev.configuration import ConfigurationError, list_models

            settings = Settings.load()
            try:
                models = list_models(settings.base_url, settings.api_key)
            except ConfigurationError as exc:
                self._write(str(exc))
                return
            query = filter_text.strip().lower()
            if query == "free":
                models = [item for item in models if item.free]
            elif query == "tools":
                models = [item for item in models if item.tool_calling]
            elif query:
                models = [item for item in models if query in item.identifier.lower()]
            self._model_choices = [item.identifier for item in models[:50]]
            if not self._model_choices:
                self._write("No matching models returned by the active provider.")
                return
            heading = "Models (use /model <number> or /model use <id>)"
            if query:
                heading += f" — filter: {filter_text}"
            lines = [heading]
            lines.extend(
                f"{index}. {item.identifier}"
                + (" [free]" if item.free else "")
                + (" [tools]" if item.tool_calling else "")
                for index, item in enumerate(models[:50], 1)
            )
            self._write("\n".join(lines))

        def _select_model(self, value: str) -> None:
            from dev.configuration import ConfigurationError, UserConfig

            value = value.strip()
            if value.isdigit():
                index = int(value)
                if not 0 < index <= len(self._model_choices):
                    self._write("Choose a model number from the latest /model list.")
                    return
                value = self._model_choices[index - 1]
            if not value:
                self._write("Enter a model name or run /model first.")
                return
            try:
                UserConfig().set_model(value)
                self._write(f"Model saved: {value}. New runs will use it.")
            except ConfigurationError as exc:
                self._write(str(exc))

        def on_input_submitted(self, event: Input.Submitted) -> None:
            value = event.value.strip()
            event.input.value = ""
            if value == "/exit":
                self.exit()
            elif value == "/clear":
                self.query_one("#chat-view", RichLog).clear()
            elif value == "/help":
                self._write("/provider [list|<number>|<name>] /model [list|free|tools|<filter>|<number>|<id>] /api-key set /config show /config reload /session /agent /clear /rollback /cancel /exit")
            elif value == "/provider" or value == "/provider list":
                self._show_providers()
            elif value.startswith("/provider use "):
                self._select_provider(value.partition(" ")[2].partition(" ")[2])
            elif value.startswith("/provider "):
                self._select_provider(value.partition(" ")[2])
            elif value == "/model" or value == "/model list":
                self._show_models()
            elif value.startswith("/model use "):
                self._select_model(value.partition(" ")[2].partition(" ")[2])
            elif value.startswith("/model "):
                model_value = value.partition(" ")[2]
                if model_value.isdigit():
                    self._select_model(model_value)
                else:
                    self._show_models(model_value)
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
