import asyncio

from dev import configuration
from dev.configuration import ModelInfo
from dev.tui.app import DevTUI


async def submit_command(pilot, command: str) -> None:
    await pilot.click("#input-bar")
    await pilot.press(*list(command), "enter")
    await pilot.pause()


def test_textual_app_smoke():
    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await pilot.press("h", "e", "l", "p", "enter")
            await pilot.pause()

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
