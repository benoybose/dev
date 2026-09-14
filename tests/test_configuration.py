import json
from pathlib import Path

import pytest

from dev import configuration
from dev.configuration import ConfigurationError, ModelInfo, UserConfig, list_models, mask_secret


def test_user_config_updates_values_without_duplicate_keys(tmp_path: Path):
    config = UserConfig(tmp_path / "config.env")
    config.set_provider("openrouter")
    config.set_api_key("secret")
    config.update({"DEV_API_KEY": "new-secret"})

    text = config.path.read_text(encoding="utf-8")
    assert "DEV_PROVIDER=openrouter" in text
    assert "DEV_BASE_URL=https://openrouter.ai/api/v1" in text
    assert text.count("DEV_API_KEY=") == 1
    assert "DEV_API_KEY=new-secret" in text


def test_secret_masking_never_returns_short_or_placeholder_secret():
    assert mask_secret("sk-placeholder") == "<not configured>"
    assert mask_secret("short") == "<configured>"
    assert mask_secret("sk-or-v1-abcdefgh") == "sk-o…efgh"


def test_list_models_sorts_and_identifies_free_and_tool_models(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({
                "data": [
                    {"id": "paid-model", "pricing": {"prompt": "1", "completion": "1"}},
                    {"id": "free-model:free", "supported_parameters": ["tools"]},
                    {"id": "zero-priced", "pricing": {"prompt": "0", "completion": "0"}},
                    {"name": "invalid-without-id"},
                ]
            }).encode()

    monkeypatch.setattr(configuration, "urlopen", lambda request, timeout: Response())

    models = list_models("https://example.test/v1", "secret")

    assert [model.identifier for model in models] == ["free-model:free", "paid-model", "zero-priced"]
    assert models[0] == ModelInfo("free-model:free", free=True, tool_calling=True)
    assert models[2].free is True


def test_list_models_converts_provider_errors_to_configuration_error(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(configuration, "urlopen", fail)

    with pytest.raises(ConfigurationError, match="Unable to discover models"):
        list_models("https://example.test/v1")
