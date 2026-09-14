from pathlib import Path

import pytest

from dev.agents.graph import build_dev_graph
from dev.completion.parser import parse_file_mentions
from dev.config import Settings
from dev.harness.approval import ApprovalDecision, ApprovalManager, ApprovalRequest
from dev.harness.permissions import PermissionError, PermissionPolicy
from dev.harness.session import SessionStore
from dev.harness.tools import WorkspaceTools
from dev.token_optim.cache import fingerprint_files
from dev.token_optim.context import read_context, select_relevant_files


def test_mentions_resolve_and_report_missing(tmp_path: Path):
    (tmp_path / "a.py").write_text("print(1)")
    cleaned, files, missing = parse_file_mentions("fix @a.py and @missing.py", tmp_path)
    assert files == [(tmp_path / "a.py").resolve()]
    assert missing == ["missing.py"]
    assert "[file:a.py]" in cleaned


def test_workspace_escape_is_rejected(tmp_path: Path):
    policy = PermissionPolicy(tmp_path, approval_required=False)
    with pytest.raises(PermissionError):
        policy.path(Path("..") / "secret.txt")


def test_writes_are_approval_gated(tmp_path: Path):
    with pytest.raises(PermissionError):
        PermissionPolicy(tmp_path).path(Path("x"), write=True)


def test_approved_write_is_atomic_and_readable(tmp_path: Path):
    tools = WorkspaceTools(PermissionPolicy(tmp_path), timeout=2)
    result = tools.write("x.txt", "hello", approved=True)
    assert result.ok
    assert tools.read("x.txt").output == "hello"


def test_replace_requires_unique_match_and_expected_hash(tmp_path: Path):
    path = tmp_path / "x.txt"
    path.write_text("one\none\n")
    tools = WorkspaceTools(PermissionPolicy(tmp_path), timeout=2)
    assert not tools.replace(path, "one", "two", approved=True).ok
    path.write_text("one\n")
    from dev.harness.changes import file_hash
    assert tools.replace(path, "one", "two", expected_hash="stale", approved=True).ok is False
    assert tools.replace(path, "one", "two", expected_hash=file_hash(path), approved=True).ok


def test_fingerprint_changes_when_file_changes(tmp_path: Path):
    path = tmp_path / "x.txt"
    path.write_text("one")
    first = fingerprint_files([path])
    path.write_text("two")
    assert fingerprint_files([path]) != first


def test_settings_loads_workspace_dotenv_with_environment_precedence(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(
        "DEV_BASE_URL=https://workspace.example/v1\nDEV_MODEL=workspace-model\nDEV_APPROVAL_REQUIRED=false\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DEV_BASE_URL", raising=False)
    monkeypatch.setenv("DEV_MODEL", "environment-model")
    monkeypatch.delenv("DEV_APPROVAL_REQUIRED", raising=False)

    settings = Settings.load(workspace=tmp_path)

    assert settings.base_url == "https://workspace.example/v1"
    assert settings.model == "environment-model"
    assert settings.approval_required is False


def test_settings_load_uses_runtime_default_paths():
    settings = Settings.load(workspace=Path.cwd())
    assert settings.session_db.name == "sessions.db"
    assert settings.cache_db.name == "cache.db"


def test_cli_workspace_is_always_current_directory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEV_WORKSPACE", str(Path.cwd().parent))

    settings = Settings.load()

    assert settings.workspace == tmp_path.resolve()


def test_commands_are_gated_and_dangerous_commands_rejected(tmp_path: Path):
    tools = WorkspaceTools(PermissionPolicy(tmp_path), timeout=2)
    assert not tools.run(["python", "-c", "print(1)"]).ok
    with pytest.raises(PermissionError):
        tools.run(["rm", "-rf", "."], approved=True)


def test_approval_manager_defaults_to_deny_and_records_request():
    manager = ApprovalManager()
    assert not manager.allows("r1", "write", "x.py")
    assert manager.requests == [ApprovalRequest("r1", "write", "x.py", "")]


def test_approval_manager_accepts_typed_decisions():
    manager = ApprovalManager(lambda request: ApprovalDecision.APPROVE)
    assert manager.allows("r1", "write", "x.py")


def test_sessions_round_trip(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    sid = store.save(None, "demo", {"task": "hello"})
    assert store.load(sid)["state"] == {"task": "hello"}
    assert store.list_sessions()[0]["name"] == "demo"


def test_sessions_can_rename_export_and_import(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    sid = store.save(None, "demo", {"task": "hello"})
    store.append_event(sid, "run-1", {"type": "completed"})
    assert store.rename(sid, "renamed")
    export_path = store.export_session("renamed", tmp_path / "session.json")

    imported = SessionStore(tmp_path / "imported.db").import_session(export_path, "copy")
    imported_store = SessionStore(tmp_path / "imported.db")
    assert imported_store.load(imported)["name"] == "copy"
    assert imported_store.events(imported)[0]["event"] == {"type": "completed"}


def test_graph_has_bounded_result():
    result = build_dev_graph(max_iterations=1).invoke({"task": "test"})
    assert result["status"] == "completed"
    assert result["messages"][-1]["role"] == "assistant"


def test_context_is_bounded_and_deterministic(tmp_path: Path):
    paths = []
    for name in ("one.py", "two.py", "three.py"):
        path = tmp_path / name; path.write_text(name)
        paths.append(path)
    assert len(select_relevant_files("one", paths, max_files=2)) == 2
    context = read_context(paths, max_total_bytes=10)
    assert len(context.encode("utf-8")) <= 10
