from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {"adapter": "openai", "base_url": "https://api.openai.com/v1"},
    "openrouter": {"adapter": "openai", "base_url": "https://openrouter.ai/api/v1"},
    "anthropic": {"adapter": "anthropic", "base_url": "https://api.anthropic.com"},
    "google": {"adapter": "google", "base_url": ""},
    "azure": {"adapter": "azure", "base_url": ""},
    "ollama": {"adapter": "openai", "base_url": "http://localhost:11434/v1"},
}


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelInfo:
    identifier: str
    context_length: int | None = None
    free: bool = False
    tool_calling: bool = False


class UserConfig:
    """Manage user-wide settings without exposing secrets to session storage."""

    def __init__(self, path: Path | None = None):
        self.path = (path or Path.home() / ".dev" / "config.env").expanduser()

    def update(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        remaining = dict(values)
        output: list[str] = []
        for line in existing:
            stripped = line.strip()
            key = stripped.split("=", 1)[0].removeprefix("export ").strip() if "=" in stripped else ""
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
            else:
                output.append(line)
        if output and output[-1].strip():
            output.append("")
        output.extend(f"{key}={value}" for key, value in remaining.items())
        self.path.write_text("\n".join(output) + "\n", encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def set_provider(self, provider: str) -> None:
        name = provider.lower().strip()
        if name not in PROVIDERS:
            raise ConfigurationError(f"Unknown provider: {provider}")
        details = PROVIDERS[name]
        values = {"DEV_PROVIDER": name}
        if details["base_url"]:
            values["DEV_BASE_URL"] = details["base_url"]
        self.update(values)

    def set_model(self, model: str) -> None:
        if not model.strip():
            raise ConfigurationError("Model identifier must not be empty")
        self.update({"DEV_MODEL": model.strip()})

    def set_api_key(self, api_key: str) -> None:
        if not api_key.strip():
            raise ConfigurationError("API key must not be empty")
        self.update({"DEV_API_KEY": api_key.strip()})


def list_models(base_url: str, api_key: str = "") -> list[ModelInfo]:
    """Discover models from an OpenAI-compatible ``/models`` endpoint."""
    endpoint = base_url.rstrip("/") + "/models"
    headers = {"Accept": "application/json", "User-Agent": "dev-coding-agent"}
    if api_key and api_key != "sk-placeholder":
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(endpoint, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10) as response:  # nosec B310 - URL comes from configured provider.
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise ConfigurationError(f"Unable to discover models from {endpoint}: {exc}") from exc
    models: list[ModelInfo] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        identifier = str(item["id"])
        pricing = item.get("pricing", {}) or {}
        free = identifier.endswith(":free") or (pricing.get("prompt") == "0" and pricing.get("completion") == "0")
        parameters = item.get("supported_parameters", []) or []
        models.append(ModelInfo(identifier, item.get("context_length"), free, "tools" in parameters))
    return sorted(models, key=lambda model: model.identifier.lower())


def mask_secret(value: str) -> str:
    if not value or value == "sk-placeholder":
        return "<not configured>"
    return value[:4] + "…" + value[-4:] if len(value) > 10 else "<configured>"
