import asyncio

from dev.completion.suggester import CommandMentionSuggester


def suggest(suggester: CommandMentionSuggester, value: str) -> str | None:
    return asyncio.run(suggester.get_suggestion(value))


def test_slash_command_suggestions_cover_commands_and_subcommands(tmp_path):
    suggester = CommandMentionSuggester(tmp_path)

    assert suggest(suggester, "/pro") == "/provider"
    assert suggest(suggester, "/help m") == "/help model"
    assert suggest(suggester, "/provider ") == "/provider list"
    assert suggest(suggester, "/model c") == "/model catalog"
    assert suggest(suggester, "/model l") == "/model live"
    assert suggest(suggester, "/model t") == "/model tools"
    assert suggest(suggester, "/sess") == "/session"
    assert suggest(suggester, "/set") == "/setup"
    assert suggest(suggester, "/api") == "/api-key set"
    assert suggest(suggester, "/does-not-exist") is None


def test_slash_command_suggestions_cover_help_topics_and_session_actions(tmp_path):
    suggester = CommandMentionSuggester(tmp_path)

    assert suggest(suggester, "/help s") == "/help setup"
    assert suggest(suggester, "/help sh") == "/help shortcuts"
    assert suggest(suggester, "/model live t") == "/model live tools"
    assert suggest(suggester, "/session u") == "/session use"
    assert suggest(suggester, "/session r") == "/session rename"
    assert suggest(suggester, "/session e") == "/session export"


def test_mention_suggestions_cover_nested_directories_and_partial_files(tmp_path):
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "api.py").write_text("", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("", encoding="utf-8")
    suggester = CommandMentionSuggester(tmp_path)

    assert suggest(suggester, "inspect @src/") == "inspect @src/app/"
    assert suggest(suggester, "inspect @src/api") == "inspect @src/api.py"
    assert suggest(suggester, "read @src/app/") == "read @src/app/main.py"
    assert suggest(suggester, "read @docs/RE") == "read @docs/README.md"


def test_mention_suggestions_preserve_prompt_context(tmp_path):
    (tmp_path / "one.py").write_text("", encoding="utf-8")
    suggester = CommandMentionSuggester(tmp_path)

    assert suggest(suggester, "fix this file: @one") == "fix this file: @one.py"
    assert suggest(suggester, "fix @missing") is None
    assert suggest(suggester, "email user@example.com") is None


def test_mention_suggestions_never_escape_workspace(tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("", encoding="utf-8")
    suggester = CommandMentionSuggester(tmp_path)

    assert suggest(suggester, "inspect @../out") is None
