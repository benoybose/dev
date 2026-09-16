from __future__ import annotations

import json

try:
    import typer
except ImportError:  # pragma: no cover
    typer = None

from devx.config import Settings
from devx.harness.session import SessionStore
from devx.observability import configure_logging
from devx.tracing import configure_tracing


def main() -> None:
    if typer is None:
        raise SystemExit("Install the CLI extra: pip install 'devx-coding-agent[cli]'")
    app()


if typer:
    app = typer.Typer(help="devx - local-first AI coding agent")

    @app.command()
    def ask(prompt: str, session: str | None = typer.Option(None), json_output: bool = typer.Option(False, "--json"), approve: bool = typer.Option(False, "--approve-all")):
        """Run a single coding-agent query."""
        from devx.agents.graph import DevxState, build_supervisor_graph
        from devx.completion.parser import parse_file_mentions
        from devx.harness.approval import ApprovalManager, ApprovalRequest
        configure_logging()
        settings = Settings.load(); settings.validate()
        configure_tracing(settings)
        cleaned, files, missing = parse_file_mentions(prompt, settings.workspace)
        if missing:
            raise typer.BadParameter("Unknown or out-of-workspace mentions: " + ", ".join(missing))
        store = SessionStore(settings.session_db)
        previous = store.load(session) if session else None
        state = DevxState(task=cleaned, files_in_context=[str(path) for path in files])
        if previous:
            prior_state = previous["state"]
            state.messages = prior_state.get("messages", [])
            state.events = prior_state.get("events", [])
            state.iteration = prior_state.get("iteration", 0)
        def ask_approval(request: ApprovalRequest) -> bool:
            if approve:
                return True
            typer.echo(f"\nRequested action: {request.action}\nTarget: {request.target}\n{request.reason}")
            return typer.confirm("Approve this action?", default=False)
        result = build_supervisor_graph(settings, ApprovalManager(ask_approval), state.files_in_context,
                                        session_id=previous["id"] if previous else session).invoke(state)
        if session:
            store.save(previous["id"] if previous else None, session, result)
        print(json.dumps(result) if json_output else result["result"])

    @app.command()
    def sessions():
        """List saved sessions."""
        for item in SessionStore(Settings.load().session_db).list_sessions():
            print(f"{item['id'][:8]}  {item['name']}  {item['updated_at']}")

    @app.command("session")
    def session_command(action: str = typer.Argument(..., help="list, events, or delete"), identifier: str | None = typer.Argument(None)):
        """Inspect or remove a saved session."""
        store = SessionStore(Settings.load().session_db)
        if action == "list":
            for item in store.list_sessions():
                print(f"{item['id']}  {item['name']}  {item['updated_at']}")
        elif action == "events" and identifier:
            for event in store.events(identifier):
                print(json.dumps(event))
        elif action == "delete" and identifier:
            if not store.delete(identifier):
                raise typer.BadParameter(f"Session not found: {identifier}")
        else:
            raise typer.BadParameter("Use: devx session list|events ID|delete ID")

    @app.command()
    def doctor():
        """Check local configuration and optional dependencies."""
        settings = Settings.load(); settings.validate()
        optional = {}
        for package in ("langchain", "langgraph", "textual", "sentence_transformers"):
            try:
                __import__(package)
                optional[package] = "installed"
            except ImportError:
                optional[package] = "missing"
        print(f"workspace: {settings.workspace}\nprovider: {settings.provider}\nmodel: {settings.model}\noptional: {optional}\nstatus: ok")

    @app.command()
    def tui(session: str | None = typer.Option(None)):
        """Launch the interactive terminal UI."""
        try:
            from devx.tui.app import DevxTUI
        except ImportError:
            raise typer.BadParameter("Install the TUI extra: pip install 'devx-coding-agent[tui]'")
        DevxTUI(session_id=session).run()
