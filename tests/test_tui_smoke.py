import asyncio

from dev.tui.app import DevTUI


def test_textual_app_smoke():
    async def run() -> None:
        async with DevTUI().run_test() as pilot:
            await pilot.press("h", "e", "l", "p", "enter")
            await pilot.pause()

    asyncio.run(run())


def test_textual_command_surface_smoke():
    async def run() -> None:
        async with DevTUI(session_id="command-test").run_test() as pilot:
            for command in ("/help", "/session", "/agent planner", "/clear", "/cancel"):
                await pilot.press(*list(command))
                await pilot.press("enter")
                await pilot.pause()

    asyncio.run(run())
