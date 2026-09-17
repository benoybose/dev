from devx.harness.testing import detect_test_command


def test_detects_python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert detect_test_command(tmp_path) == "python -m pytest -q"


def test_detects_javascript_package_manager(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n", encoding="utf-8")
    assert detect_test_command(tmp_path) == "pnpm test"


def test_detects_make_test_target(tmp_path):
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    assert detect_test_command(tmp_path) == "make test"
