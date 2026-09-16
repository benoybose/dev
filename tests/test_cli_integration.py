from pathlib import Path

from typer.testing import CliRunner

from devx.cli.app import app
from devx.config import Settings
from devx.harness.session import SessionStore

runner = CliRunner()


def test_cli_doctor_command():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "status: ok" in result.output
    assert "provider:" in result.output
    assert "model:" in result.output


def test_cli_sessions_and_session_management(tmp_path: Path):
    db_file = tmp_path / "sessions.db"
    store = SessionStore(db_file)
    sid = store.save(None, "integration-session", {"task": "test task"})
    store.append_event(sid, "run-1", {"type": "test_event", "payload": "hello"})

    settings = Settings(session_db=db_file)

    # Test sessions listing
    import devx.cli.app as cli_module
    orig_load = cli_module.Settings.load
    cli_module.Settings.load = classmethod(lambda cls, *args, **kwargs: settings)
    try:
        result = runner.invoke(app, ["sessions"])
        assert result.exit_code == 0
        assert "integration-session" in result.output

        # Test session list alias
        result_list = runner.invoke(app, ["session", "list"])
        assert result_list.exit_code == 0
        assert sid in result_list.output
        assert "integration-session" in result_list.output

        # Test session events
        result_events = runner.invoke(app, ["session", "events", sid])
        assert result_events.exit_code == 0
        assert "test_event" in result_events.output

        # Test session delete
        result_del = runner.invoke(app, ["session", "delete", sid])
        assert result_del.exit_code == 0
        assert store.load(sid) is None

        # Test delete nonexistent session
        result_del_missing = runner.invoke(app, ["session", "delete", "nonexistent"])
        assert result_del_missing.exit_code != 0

        # Test invalid session sub-action
        result_invalid = runner.invoke(app, ["session", "unknown"])
        assert result_invalid.exit_code != 0
        assert "devx session" in result_invalid.output
    finally:
        cli_module.Settings.load = orig_load


def test_config_env_precedence_and_backward_compatibility(monkeypatch, tmp_path: Path):
    home_dir = tmp_path / "fake_home"
    devx_dir = home_dir / ".devx"
    devx_dir.mkdir(parents=True)
    (devx_dir / "config.env").write_text(
        'DEVX_MODEL="gpt-4o-mini"\nDEV_MODEL="gpt-3.5-turbo"\nDEVX_BASE_URL="http://devx.local:8000/v1"\n',
        encoding="utf-8"
    )

    monkeypatch.setattr(Path, "home", lambda: home_dir)

    # DEVX_* should take precedence over DEV_* in config file
    s = Settings.load(workspace=tmp_path)
    assert s.model == "gpt-4o-mini"
    assert s.base_url == "http://devx.local:8000/v1"

    # Environment variable DEVX_* overrides file
    monkeypatch.setenv("DEVX_MODEL", "claude-3-5-sonnet")
    s2 = Settings.load(workspace=tmp_path)
    assert s2.model == "claude-3-5-sonnet"

    # Legacy DEV_* env var fallback works when DEVX_* not set
    monkeypatch.delenv("DEVX_MODEL")
    monkeypatch.setenv("DEV_MODEL", "legacy-dev-model")
    s3 = Settings.load(workspace=tmp_path)
    assert s3.model == "legacy-dev-model"
