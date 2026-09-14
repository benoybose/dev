from pathlib import Path

from dev.configuration import UserConfig, mask_secret


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
