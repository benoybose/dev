import pytest

from scripts.version import normalize, version_for_branch, write_version


def test_release_and_hotfix_branches_set_exact_versions():
    assert version_for_branch("0.1.0", "release/1.2.0") == "1.2.0"
    assert version_for_branch("1.2.0", "hotfix/v1.2.1") == "1.2.1"
    assert version_for_branch("1.2.0", "release/1.3") == "1.3.0"
    assert version_for_branch("1.2.0", "refs/heads/release/1.3") == "1.3.0"


def test_develop_uses_next_minor_dev_version():
    assert version_for_branch("1.2.0", "develop") == "1.3.0-dev.0"
    assert version_for_branch("1.3.0-dev.0", "develop") == "1.3.0-dev.0"


def test_feature_branches_do_not_change_version():
    assert version_for_branch("1.2.0", "feature/agent-tools") == "1.2.0"


def test_invalid_versions_are_rejected():
    with pytest.raises(ValueError):
        normalize("not-a-version")


def test_write_version_updates_project_and_runtime_metadata(tmp_path):
    (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    package = tmp_path / "src" / "dev"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    write_version("1.2.0", tmp_path)

    assert 'version = "1.2.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "1.2.0"' in (package / "__init__.py").read_text(encoding="utf-8")
