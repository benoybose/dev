import asyncio

import pytest

from dev import configuration
from dev.configuration import ModelInfo
from dev.tui import app as tui_app
from dev.tui.app import DevTUI


@pytest.fixture(autouse=True)
def configured_provider(monkeypatch):
    """Keep ordinary TUI interaction tests behind the first-run setup gate."""
    monkeypatch.setenv("DEV_PROVIDER", "openrouter")
    monkeypatch.setenv("DEV_API_KEY", "test-key")


async def submit_command(pilot, command: str) -> None:
    await pilot.click("#input-bar")
    await pilot.press(*list(command), "enter")
    await pilot.pause()


def test_textual_app_smoke():
    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            assert pilot.app.focused.id == "input-bar"
            await pilot.press(*list("hello"))
            assert pilot.app.query_one("#input-bar").value == "hello"
            await pilot.press("ctrl+a", "backspace")
            await pilot.press("h", "e", "l", "p", "enter")
            await pilot.pause()

    asyncio.run(run())


def test_textual_layout_has_chrome_and_keyboard_actions():
    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            assert pilot.app.query_one("#welcome")
            assert pilot.app.query_one("Header")
            assert pilot.app.query_one("Footer")
            await pilot.press("f1")
            await pilot.press("ctrl+l")
            await pilot.pause()

    asyncio.run(run())


def test_unconfigured_provider_opens_setup_gate(monkeypatch):
    monkeypatch.setattr(DevTUI, "_needs_provider_setup", staticmethod(lambda _settings: True))

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            assert pilot.app.screen.query_one("#setup-dialog")
            assert pilot.app.screen.query_one("#setup-provider")
            assert pilot.app.screen.query_one("#setup-save")

    asyncio.run(run())


def test_setup_saves_to_workspace_env_when_it_controls_precedence(monkeypatch, tmp_path):
    from dev.config import Settings

    workspace_env = tmp_path / ".env"
    workspace_env.write_text("DEV_API_KEY=sk-placeholder\n", encoding="utf-8")
    settings = Settings(
        provider="openrouter",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        model="test-model",
        workspace=tmp_path,
    )
    saved = {}

    class FakeUserConfig:
        def __init__(self, path=None):
            saved["path"] = path

        def set_provider(self, provider):
            saved["provider"] = provider

        def update(self, values):
            saved.update(values)

        def set_api_key(self, api_key):
            saved["api_key"] = api_key

    monkeypatch.setattr("dev.config.Settings.load", staticmethod(lambda: settings))
    monkeypatch.setattr(configuration, "UserConfig", FakeUserConfig)
    monkeypatch.setattr(DevTUI, "_needs_provider_setup", staticmethod(lambda _settings: True))

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await pilot.click("#setup-save")
            await pilot.pause()

    asyncio.run(run())
    assert saved["path"] == workspace_env


def test_prompt_has_command_and_mention_suggester(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")

    from dev.completion.suggester import CommandMentionSuggester

    async def run() -> None:
        suggester = CommandMentionSuggester(tmp_path)
        assert await suggester.get_suggestion("/pro") == "/provider"
        assert await suggester.get_suggestion("fix @src/") == "fix @src/main.py"

    asyncio.run(run())


def test_copy_command_copies_transcript_and_keyboard_shortcut(monkeypatch):
    copied = []
    monkeypatch.setattr(tui_app, "copy_to_clipboard", copied.append)

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            pilot.app._write("hello transcript")
            panel = pilot.app.query_one("#chat-view")
            panel.focus()
            panel.select_line(1)
            await pilot.press("ctrl+shift+c")
            assert copied == ["hello transcript"]
            panel.select_all()
            await submit_command(pilot, "/copy")
            assert copied[-1].startswith("Ready. Type a task or /help for commands.\nhello transcript")

    asyncio.run(run())


def test_textual_command_surface_smoke():
    async def run() -> None:
        async with DevTUI(session_id="command-test").run_test() as pilot:
            for command in ("/help", "/provider", "/session", "/agent planner", "/clear", "/cancel"):
                await pilot.press(*list(command))
                await pilot.press("enter")
                await pilot.pause()

    asyncio.run(run())


def test_provider_number_shortcut_persists_selected_provider(monkeypatch):
    saved = []

    class FakeUserConfig:
        def set_provider(self, provider):
            saved.append(provider)

    monkeypatch.setattr(configuration, "UserConfig", FakeUserConfig)

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await submit_command(pilot, "/provider 2")

    asyncio.run(run())
    assert saved == [sorted(configuration.PROVIDERS)[1]]


def test_model_listing_filters_and_number_shortcut_persists_model(monkeypatch):
    saved = []
    models = [
        ModelInfo("paid-model", free=False, tool_calling=False),
        ModelInfo("free-model:free", free=True, tool_calling=True),
        ModelInfo("tools-model", free=False, tool_calling=True),
    ]

    class FakeUserConfig:
        def set_model(self, model):
            saved.append(model)

    monkeypatch.setattr(configuration, "UserConfig", FakeUserConfig)
    monkeypatch.setattr(configuration, "list_models", lambda *_args: models)

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await submit_command(pilot, "/model free")
            assert pilot.app._model_choices == ["free-model:free"]
            await submit_command(pilot, "/model 1")

    asyncio.run(run())
    assert saved == ["free-model:free"]


def test_model_filter_supports_tools_and_text(monkeypatch):
    models = [
        ModelInfo("alpha", tool_calling=True),
        ModelInfo("beta", free=True),
        ModelInfo("alpha-free:free", free=True, tool_calling=True),
    ]
    monkeypatch.setattr(configuration, "list_models", lambda *_args: models)

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await submit_command(pilot, "/model tools")
            assert pilot.app._model_choices == ["alpha", "alpha-free:free"]
            await submit_command(pilot, "/model alpha-free")
            assert pilot.app._model_choices == ["alpha-free:free"]

    asyncio.run(run())


def test_invalid_model_number_does_not_persist(monkeypatch):
    saved = []

    class FakeUserConfig:
        def set_model(self, model):
            saved.append(model)

    monkeypatch.setattr(configuration, "UserConfig", FakeUserConfig)

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await submit_command(pilot, "/model 99")

    asyncio.run(run())
    assert saved == []


def test_api_key_modal_accepts_enter(monkeypatch):
    saved = []

    class FakeUserConfig:
        def set_api_key(self, api_key):
            saved.append(api_key)

    monkeypatch.setattr(configuration, "UserConfig", FakeUserConfig)

    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await submit_command(pilot, "/api-key set")
            await pilot.click("#secret-input")
            await pilot.press(*list("test-secret"), "enter")
            await pilot.pause()

    asyncio.run(run())
    assert saved == ["test-secret"]
