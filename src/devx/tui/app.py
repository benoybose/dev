from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, TextArea
except ImportError:  # pragma: no cover
    App = object


def copy_to_clipboard(text: str) -> None:
    """Copy text using a native clipboard command on the current platform."""
    if not text:
        raise RuntimeError("The transcript is empty.")
    system = platform.system()
    commands = {
        "Windows": [["clip.exe"], ["clip"]],
        "Darwin": [["pbcopy"]],
        "Linux": [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]],
    }.get(system, [])
    for command in commands:
        if shutil.which(command[0]):
            try:
                subprocess.run(command, input=text, text=True, check=True, timeout=5)  # nosec B603
                return
            except (OSError, subprocess.SubprocessError) as exc:
                raise RuntimeError(f"Unable to copy transcript with {command[0]}: {exc}") from exc
    raise RuntimeError("No clipboard utility found. Install wl-copy, xclip, or xsel.")


if App is not object:
    class ApprovalModal(ModalScreen):
        def __init__(self, request, done):
            super().__init__()
            self.request, self.done = request, done

        def compose(self) -> ComposeResult:
            with Vertical(id="approval-dialog"):
                yield Label(f"Approve {self.request.action}: {self.request.target}")
                yield Label("Proposed action")
                yield Static(self.request.reason[:12000], markup=False, id="approval-preview")
                yield Button("Approve", id="approve")
                yield Button("Deny", id="deny")
                yield Button("Cancel run", id="cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            from devx.harness.approval import ApprovalDecision
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

    class ProviderSetupModal(ModalScreen):
        def __init__(self, settings, done, *, first_time: bool = True):
            super().__init__()
            self.settings = settings
            self.done = done
            self.first_time = first_time

        def compose(self) -> ComposeResult:
            from devx.configuration import PROVIDERS, catalog_models

            options = [(name.title(), name) for name in sorted(PROVIDERS)]
            provider = self.settings.provider if self.settings.provider in PROVIDERS else "openrouter"
            models = catalog_models(provider)
            model_options = self._model_options(models)
            selected_model = self.settings.model if self.settings.model in {item.identifier for item in models} else (
                models[0].identifier if models else Select.BLANK
            )
            with Vertical(id="setup-dialog"):
                title = "First-time provider setup" if self.first_time else "Provider and model setup"
                help_text = (
                    "Configure a provider before starting your first agent run."
                    if self.first_time else "Choose a provider and coding model for future agent runs."
                )
                yield Label(title, id="setup-title")
                yield Label(help_text, id="setup-help")
                yield Select(options, value=provider, prompt="Provider", id="setup-provider")
                yield Input(value="" if self.settings.api_key == "sk-placeholder" else self.settings.api_key,
                            placeholder="API key (not required for Ollama)", password=True, id="setup-api-key")
                yield Input(value=self.settings.base_url, placeholder="Base URL", id="setup-base-url")
                yield Select(model_options, value=selected_model, prompt="Coding model", id="setup-model")
                yield Label("", id="setup-error")
                with Horizontal(id="setup-actions"):
                    yield Button("Save and continue", id="setup-save")
                    yield Button("Exit", id="setup-exit")

        def on_mount(self) -> None:
            self.query_one("#setup-provider", Select).focus()

        def on_key(self, event) -> None:
            if event.key == "escape":
                event.stop()
                self.dismiss()

        def on_select_changed(self, event: Select.Changed) -> None:
            from devx.configuration import PROVIDERS

            if event.select.id != "setup-provider":
                return
            provider = str(event.value)
            base_url = PROVIDERS.get(provider, {}).get("base_url", "")
            if base_url:
                self.query_one("#setup-base-url", Input).value = base_url
            from devx.configuration import catalog_models
            models = catalog_models(provider)
            model_select = self.query_one("#setup-model", Select)
            model_select.set_options(self._model_options(models))
            model_select.value = models[0].identifier if models else Select.BLANK

        @staticmethod
        def _model_options(models) -> list[tuple[str, str]]:
            return [
                (f"{item.identifier}{' [free]' if item.free else ''}", item.identifier)
                for item in models
                if item.agent_ready
            ]

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "setup-exit":
                self.app.exit()
                return
            if event.button.id != "setup-save":
                return
            from devx.configuration import ConfigurationError, UserConfig

            provider = str(self.query_one("#setup-provider", Select).value)
            api_key = self.query_one("#setup-api-key", Input).value.strip()
            base_url = self.query_one("#setup-base-url", Input).value.strip()
            model_value = self.query_one("#setup-model", Select).value
            model = "" if model_value in {None, Select.BLANK} else str(model_value).strip()
            if provider == str(Select.BLANK):
                self.query_one("#setup-error", Label).update("Select a provider.")
                return
            if provider != "ollama" and not api_key:
                self.query_one("#setup-error", Label).update("Enter an API key, or choose Ollama for a local model.")
                return
            if not base_url or not model:
                self.query_one("#setup-error", Label).update("Base URL and model are required.")
                return
            try:
                workspace_env = self.settings.workspace / ".env"
                config = UserConfig(workspace_env if workspace_env.is_file() else None)
                config.set_provider(provider)
                config.update({"DEVX_BASE_URL": base_url, "DEVX_MODEL": model})
                if api_key:
                    config.set_api_key(api_key)
            except (ConfigurationError, OSError) as exc:
                self.query_one("#setup-error", Label).update(str(exc))
                return
            self.done()
            self.dismiss()

    class DevTUI(App):
        CSS_PATH = None
        TITLE = "devx • coding agent"
        SUB_TITLE = "local-first • approval-gated"
        BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
            ("f1", "show_help", "Help"),
            ("ctrl+l", "clear_chat", "Clear"),
            ("ctrl+shift+c", "copy_transcript", "Copy"),
            ("ctrl+insert", "copy_transcript", "Copy"),
            ("f2", "copy_transcript", "Copy"),
            ("ctrl+c", "copy_or_cancel", "Copy/Cancel"),
        ]
        CSS = """
        $primary: #303030;
        $secondary: #4a4a4a;
        $accent: #bdbdbd;
        $success: #d0d0d0;
        $warning: #b0b0b0;
        $error: #bdbdbd;
        $surface: #111111;
        $panel: #1c1c1c;
        $text: #f2f2f2;
        $text-muted: #999999;
        $surface-lighten-1: #1b1b1b;
        $surface-lighten-2: #242424;

        Screen {
            background: #111111;
            width: 100%;
            height: 100%;
        }
        Screen > Vertical {
            width: 100%;
            height: 100%;
        }
        Header {
            background: #202020;
            color: #f2f2f2;
        }
        Footer {
            background: #1c1c1c;
            color: #bdbdbd;
        }
        ProviderSetupModal {
            align: center middle;
        }
        #welcome {
            height: auto;
            width: 100%;
            margin: 0;
            padding: 1 2 0 2;
            background: #111111;
        }
        #welcome-title {
            color: #e0e0e0;
            text-style: bold;
        }
        #welcome-subtitle {
            color: #999999;
            padding: 0 0 1 0;
        }
        #chat-view {
            height: 1fr;
            width: 100%;
            border: none;
            padding: 1 2;
            margin: 0;
            background: #111111;
            scrollbar-size: 1 1;
        }
        #input-bar {
            height: 3;
            width: 100%;
            margin: 0;
            border: none;
            background: #1b1b1b;
        }
        #status-bar {
            height: 1;
            width: 100%;
            margin: 0;
            padding: 0 1;
            background: #1c1c1c;
            color: #d0d0d0;
        }
        #status-bar .status-item {
            width: 1fr;
        }
        #status-text {
            color: #d0d0d0;
        }
        #input-bar:focus {
            border: none;
            background: #242424;
        }
        Button {
            background: #303030;
            color: #f2f2f2;
            border: none;
        }
        Button:hover, Button:focus {
            background: #4a4a4a;
            color: #ffffff;
        }
        #setup-dialog {
            width: 72;
            max-width: 90%;
            height: auto;
            padding: 1 2;
            background: #151515;
            border: round #bdbdbd;
        }
        #setup-title {
            color: #e0e0e0;
            text-style: bold;
        }
        #setup-help, #setup-error {
            color: #999999;
            margin-bottom: 1;
        }
        #setup-error {
            color: #bdbdbd;
        }
        #setup-actions {
            width: 100%;
            height: auto;
            align: center middle;
        }
        #setup-actions Button {
            margin: 1 1;
            padding: 1 2;
        }
        #setup-save {
            background: #3a3a3a;
            color: #ffffff;
        }
        #setup-exit {
            background: #252525;
            color: #d0d0d0;
        }
        """

        def __init__(self, session_id: str | None = None):
            super().__init__()
            self.session_id = session_id or "default"
            try:
                from devx.config import Settings
                self._workspace = Settings.load().workspace
            except (OSError, ValueError):
                self._workspace = Path.cwd()
            self._cancellation = None
            self._requested_agent = "supervisor"
            self._provider_choices: list[str] = []
            self._model_choices: list[str] = []
            self._transcript: list[str] = []
            self._run_active = False

        def compose(self) -> ComposeResult:
            from devx.completion.suggester import CommandMentionSuggester

            with Vertical():
                yield Header(show_clock=True)
                with Vertical(id="welcome"):
                    yield Static("DEVX CODING AGENT", id="welcome-title")
                    yield Static(
                        "Describe a task, reference files with @path, or use /help for commands.",
                        id="welcome-subtitle",
                    )
                yield TextArea(
                    id="chat-view",
                    read_only=True,
                    soft_wrap=True,
                    show_line_numbers=False,
                    placeholder="Transcript will appear here...",
                )
                yield Input(
                    placeholder="Enter a task... use /commands or @file mentions",
                    suggester=CommandMentionSuggester(self._workspace),
                    id="input-bar",
                )
                with Horizontal(id="status-bar"):
                    yield Static("● ready", id="status-text", classes="status-item")
                    yield Static(f"session: {self.session_id}", id="session-text", classes="status-item")
                    yield Static("hint: /help • /setup • /model", id="hint-text", classes="status-item")
                yield Footer()

        def on_mount(self) -> None:
            from devx.config import Settings

            settings = Settings.load()
            if self._needs_provider_setup(settings):
                self.push_screen(ProviderSetupModal(settings, self._finish_setup))
            else:
                self._finish_setup()

        @staticmethod
        def _needs_provider_setup(settings) -> bool:
            return settings.provider != "ollama" and settings.api_key in {"", "sk-placeholder"}

        def _finish_setup(self) -> None:
            self.query_one("#input-bar", Input).focus()
            self._write("Ready. Type a task or /help for commands.")

        def _open_setup(self) -> None:
            from devx.config import Settings

            self.push_screen(ProviderSetupModal(Settings.load(), self._finish_reconfiguration, first_time=False))

        def _finish_reconfiguration(self) -> None:
            from devx.config import Settings

            settings = Settings.load()
            self._write(f"Configuration saved: {settings.provider} / {settings.model}")
            self.query_one("#input-bar", Input).focus()

        def action_show_help(self, topic: str = "") -> None:
            topic = topic.strip().lower()
            help_topics = {
                "setup": (
                    "SETUP\n"
                    "/setup or /configure  Open provider, API key, base URL, and coding-model setup.\n"
                    "/api-key set           Change only the masked API key."
                ),
                "provider": (
                    "PROVIDER\n"
                    "/provider              List configured providers.\n"
                    "/provider <number>     Select a listed provider.\n"
                    "/provider use <name>   Select a provider by name.\n"
                    "Use /setup when changing provider and model together."
                ),
                "model": (
                    "MODEL\n"
                    "/model                 Show curated coding models.\n"
                    "/model <number>        Select a listed curated model.\n"
                    "/model live             Discover models from the provider API.\n"
                    "/model live tools      Show live tool-capable models.\n"
                    "/model use <id>         Select a model by identifier."
                ),
                "session": (
                    "SESSION\n"
                    "/session                List saved sessions.\n"
                    "/session use <id>       Switch and restore a saved session.\n"
                    "/session rename <name>  Rename the current session.\n"
                    "/session export <path>  Export the current session.\n"
                    "/session import <path>  Import a session."
                ),
                "shortcuts": (
                    "SHORTCUTS\n"
                    "F1                     Show this help.\n"
                    "Ctrl+L                 Clear the transcript.\n"
                    "F2 / Ctrl+Insert       Copy selected or full transcript.\n"
                    "Ctrl+C                 Copy a selection or cancel a run.\n"
                    "Right arrow             Accept an autocomplete suggestion."
                ),
            }
            if topic in {"commands", "command", "all"}:
                topic = ""
            if topic:
                self._write(help_topics.get(topic, f"No help topic: {topic}. Try /help."))
                return
            self._write(
                "QUICK START\n"
                "Describe a task in the prompt. Mention files with @path.\n"
                "First run: /setup    Change settings later: /setup\n"
                "\n"
                "COMMANDS\n"
                "/help [topic]         Show help or: setup, provider, model, session, shortcuts.\n"
                "/setup                 Configure provider and coding model.\n"
                "/provider              List or select a provider.\n"
                "/model                 Select a curated coding model.\n"
                "/session               List or switch saved sessions.\n"
                "/agent [name]          Choose supervisor, planner, coder, or tester.\n"
                "/config show           Show active settings with the API key masked.\n"
                "/copy /clear /diff      Copy, clear, or show the Git diff.\n"
                "/undo /plan <task>      Undo the last run or preview a plan.\n"
                "/cancel                 Cancel a running task.\n"
                "/exit                  Quit the TUI.\n"
                "\n"
                "Try /help model or /help shortcuts for details."
            )

        def action_clear_chat(self) -> None:
            self.query_one("#chat-view", TextArea).text = ""
            self._transcript.clear()
            self._write("Chat cleared. Ready for your next task.")

        def action_copy_transcript(self) -> None:
            panel = self.query_one("#chat-view", TextArea)
            selected = panel.selected_text
            content = selected if selected else "\n".join(self._transcript)
            try:
                copy_to_clipboard(content)
            except RuntimeError as exc:
                self.query_one("#status-text", Static).update(f"● copy failed: {exc}")
            else:
                label = "selection" if selected else "transcript"
                self.query_one("#status-text", Static).update(f"● copied {label} to clipboard")

        def action_copy_or_cancel(self) -> None:
            panel = self.query_one("#chat-view", TextArea)
            if panel.selected_text:
                self.action_copy_transcript()
            else:
                self.action_cancel_run()

        def _show_diff(self) -> None:
            from devx.config import Settings
            from devx.harness.permissions import PermissionPolicy
            from devx.harness.tools import WorkspaceTools

            settings = Settings.load()
            result = WorkspaceTools(
                PermissionPolicy(settings.workspace, settings.approval_required),
                max_bytes=settings.max_file_bytes,
                timeout=settings.command_timeout,
            ).git_diff()
            self._write(result.output or "No uncommitted changes.")

        def _undo_last_run(self) -> None:
            from devx.config import Settings
            from devx.harness.changes import ChangeJournal
            from devx.harness.session import SessionStore

            settings = Settings.load()
            session = SessionStore(settings.session_db).load(self.session_id)
            run_id = (session or {}).get("metadata", {}).get("last_run_id")
            if not run_id:
                self._write("No completed run is available to undo.")
                return
            restored = ChangeJournal(settings.session_db).rollback(run_id)
            self._write("Restored: " + ", ".join(restored) if restored else "No safe changes to restore.")

        def action_cancel_run(self) -> None:
            if self._cancellation:
                self._cancellation.cancel()
                self._write("Cancellation requested.")
            else:
                self._write("No active run to cancel.")

        def _write(self, message: str) -> None:
            self._transcript.append(message)
            panel = self.query_one("#chat-view", TextArea)
            panel.text = "\n".join(self._transcript)
            panel.scroll_end(animate=False)

        def _show_providers(self) -> None:
            from devx.configuration import PROVIDERS

            self._provider_choices = sorted(PROVIDERS)
            lines = ["Providers (use /provider <number> or /provider <name>):"]
            lines.extend(f"{index}. {name}" for index, name in enumerate(self._provider_choices, 1))
            self._write("\n".join(lines))

        def _switch_session(self, requested: str) -> None:
            from devx.config import Settings
            from devx.harness.session import SessionStore

            requested = requested.strip()
            if not requested:
                self._write("Usage: /session use <id-or-name>")
                return
            try:
                session = SessionStore(Settings.load().session_db).load(requested)
            except OSError as exc:
                self._write(f"Unable to load session: {exc}")
                return
            if not session:
                self._write(f"Session not found: {requested}")
                return
            self.session_id = session["id"]
            messages = session.get("state", {}).get("messages", [])
            self._transcript = [
                f"{message.get('role', 'agent')}: {message['content']}"
                for message in messages
                if isinstance(message, dict) and isinstance(message.get("content"), str)
            ]
            panel = self.query_one("#chat-view", TextArea)
            panel.text = "\n".join(self._transcript)
            self.query_one("#session-text", Static).update(f"session: {self.session_id}")
            self._write(f"Switched to session: {session['name']}")

        def _select_provider(self, value: str) -> None:
            from devx.configuration import PROVIDERS, ConfigurationError, UserConfig

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
            from devx.config import Settings
            from devx.configuration import ConfigurationError, list_models

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

        def _show_catalog(self, filter_text: str = "") -> None:
            from devx.config import Settings
            from devx.configuration import catalog_models

            settings = Settings.load()
            query = filter_text.strip().lower()
            models = catalog_models(settings.provider)
            if query:
                models = [item for item in models if query in item.identifier.lower()]
            self._model_choices = [item.identifier for item in models]
            if not self._model_choices:
                self._write(f"No curated coding models found for provider: {settings.provider}.")
                return
            lines = [
                (
                    f"Curated coding models for {settings.provider} "
                    "(use /model <number> or /model use <id>):"
                )
            ]
            lines.extend(
                f"{index}. {item.identifier}"
                + (" [free]" if item.free else "")
                + " [tools, coding]"
                for index, item in enumerate(models, 1)
            )
            self._write("\n".join(lines))

        def _select_model(self, value: str) -> None:
            from devx.configuration import ConfigurationError, UserConfig

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
            if not value:
                return
            if value == "/exit":
                self.exit()
            elif value in {"/setup", "/configure"}:
                self._open_setup()
            elif value == "/clear":
                self.action_clear_chat()
            elif value == "/help":
                self.action_show_help()
            elif value.startswith("/help "):
                self.action_show_help(value.partition(" ")[2])
            elif value == "/copy":
                self.action_copy_transcript()
            elif value == "/diff":
                self._show_diff()
            elif value in {"/undo", "/rollback"}:
                self._undo_last_run()
            elif value.startswith("/plan "):
                task = value.partition(" ")[2].strip()
                if not task:
                    self._write("Usage: /plan <task>")
                elif self._run_active:
                    self._write("A run is already active. Use /cancel before starting another task.")
                else:
                    self._write(f"> {task} (plan only)")
                    self._run_active = True
                    self.run_worker(self._ask(task, plan_only=True), exclusive=False)
            elif value == "/provider" or value == "/provider list":
                self._show_providers()
            elif value.startswith("/provider use "):
                self._select_provider(value.partition(" ")[2].partition(" ")[2])
            elif value.startswith("/provider "):
                self._select_provider(value.partition(" ")[2])
            elif value == "/model" or value in {"/model catalog", "/model list"}:
                self._show_catalog()
            elif value.startswith("/model catalog "):
                self._show_catalog(value.partition(" ")[2].partition(" ")[2])
            elif value == "/model live":
                self._show_models()
            elif value.startswith("/model live "):
                self._show_models(value.partition(" ")[2].partition(" ")[2])
            elif value.startswith("/model use "):
                self._select_model(value.partition(" ")[2].partition(" ")[2])
            elif value.startswith("/model "):
                model_value = value.partition(" ")[2]
                if model_value.isdigit():
                    self._select_model(model_value)
                else:
                    self._show_models(model_value)
            elif value == "/api-key set":
                from devx.configuration import ConfigurationError, UserConfig
                def save_key(api_key: str) -> None:
                    try:
                        UserConfig().set_api_key(api_key)
                        self._write("API key saved securely to the user configuration file.")
                    except ConfigurationError as exc:
                        self._write(str(exc))
                self.push_screen(SecretInputModal(save_key))
            elif value == "/config show":
                from devx.config import Settings
                from devx.configuration import mask_secret
                settings = Settings.load()
                self._write(
                    f"provider: {settings.provider}\nbase_url: {settings.base_url}\nmodel: {settings.model}\napi_key: {mask_secret(settings.api_key)}\nworkspace: {settings.workspace}"
                )
            elif value == "/config reload":
                from devx.config import Settings
                settings = Settings.load()
                self._workspace = settings.workspace
                self._write(f"Configuration reloaded for future runs: {settings.provider} / {settings.model}")
            elif value == "/session":
                from devx.config import Settings
                from devx.harness.session import SessionStore
                try:
                    sessions = SessionStore(Settings.load().session_db).list_sessions()
                    self._write("\n".join(f"{item['id']}  {item['name']}" for item in sessions) or "No saved sessions.")
                except OSError as exc:
                    self._write(f"Unable to list sessions: {exc}")
            elif value.startswith("/session use "):
                self._switch_session(value.partition(" ")[2].partition(" ")[2])
            elif (value.startswith("/session ") and not value.startswith("/session rename ")
                  and not value.startswith("/session export ") and not value.startswith("/session import ")):
                self._switch_session(value.partition(" ")[2].strip())
            elif value.startswith("/agent"):
                requested = value.partition(" ")[2].strip() or "supervisor"
                if requested not in {"supervisor", "planner", "coder", "tester"}:
                    self._write("Choose: supervisor, planner, coder, or tester")
                else:
                    self._requested_agent = requested
                    self.query_one("#status-text", Static).update(f"● agent: {requested}")
            elif value == "/cancel":
                if self._cancellation:
                    self._cancellation.cancel()
                    self._write("Cancellation requested.")
            elif value.startswith("/session rename "):
                from devx.config import Settings
                from devx.harness.session import SessionStore
                name = value.partition(" ")[2].partition(" ")[2].strip()
                if SessionStore(Settings.load().session_db).rename(self.session_id, name):
                    self.query_one("#session-text", Static).update(f"session: {self.session_id}")
                    self._write(f"Renamed session to: {name}")
                else:
                    self._write("Session not found.")
            elif value.startswith("/session export "):
                from devx.config import Settings
                from devx.harness.session import SessionStore
                destination = value.partition(" ")[2].partition(" ")[2].strip()
                try:
                    exported = SessionStore(Settings.load().session_db).export_session(self.session_id, destination)
                    self._write(f"Exported session: {exported}")
                except (KeyError, OSError, ValueError) as exc:
                    self._write(f"Export failed: {exc}")
            elif value.startswith("/session import "):
                from devx.config import Settings
                from devx.harness.session import SessionStore
                source = value.partition(" ")[2].partition(" ")[2].strip()
                try:
                    self.session_id = SessionStore(Settings.load().session_db).import_session(source)
                    self._write(f"Imported session: {self.session_id}")
                except (OSError, TypeError, ValueError, KeyError) as exc:
                    self._write(f"Import failed: {exc}")
            elif value.startswith("/"):
                self._write(f"Unknown command: {value.split(maxsplit=1)[0]}. Type /help for commands.")
            else:
                if self._run_active:
                    self._write("A run is already active. Use /cancel before starting another task.")
                    return
                self._write(f"> {value}")
                self._run_active = True
                self.run_worker(self._ask(value), exclusive=False)

        async def _ask(self, value: str, *, plan_only: bool = False) -> None:
            from devx.agents.graph import build_supervisor_graph
            from devx.completion.parser import parse_file_mentions
            from devx.config import Settings
            from devx.harness.approval import ApprovalDecision, ApprovalManager, ApprovalRequest
            from devx.harness.runtime import CancellationToken
            from devx.harness.session import SessionStore
            try:
                settings = Settings.load()
                store = SessionStore(settings.session_db)
                previous = store.load(self.session_id)
            except (OSError, ValueError) as exc:
                self._write(f"Agent error: {exc}")
                self._run_active = False
                return
            self._cancellation = CancellationToken()
            cleaned, files, missing = parse_file_mentions(value, settings.workspace)
            if missing:
                self._write("Unknown mentions: " + ", ".join(missing))
                self._run_active = False
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
                    decision = answer["value"]
                    if decision == ApprovalDecision.CANCEL and self._cancellation:
                        self._cancellation.cancel()
                    return decision
                def approval_handler(request: ApprovalRequest) -> ApprovalDecision:
                    return ask_approval(request.action, request.target, request.reason)
                def event_sink(event):
                    if event.get("type") == "token":
                        self.call_from_thread(self._write, event.get("text", ""))
                    else:
                        self.call_from_thread(self.query_one("#status-text", Static).update, f"● {event.get('agent', event.get('type', 'running'))}")
                initial = {"task": cleaned, "messages": previous["state"].get("messages", []) if previous else [],
                           "events": previous["state"].get("events", []) if previous else [],
                           "iteration": previous["state"].get("iteration", 0) if previous else 0,
                           "requested_agent": self._requested_agent}
                import uuid
                run_id = str(uuid.uuid4())
                result = await build_supervisor_graph(
                    settings,
                    ApprovalManager(approval_handler),
                    [str(path) for path in files],
                    run_id=run_id,
                    cancellation=self._cancellation,
                    event_sink=event_sink,
                    session_id=self.session_id,
                    plan_only=plan_only,
                ).ainvoke(initial)
                store.save(
                    previous["id"] if previous else self.session_id,
                    self.session_id,
                    result,
                    {"last_run_id": run_id},
                )
                self._write(result["result"])
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                self._write(f"Agent error: {exc}")
            finally:
                self._run_active = False
else:
    class DevTUI:  # pragma: no cover
        def __init__(self, session_id=None): self.session_id = session_id
        def run(self): raise RuntimeError("Install the TUI extra: pip install 'devx-coding-agent[tui]'")

if App is not object:
    DevxTUI = DevTUI
else:
    DevxTUI = DevTUI
