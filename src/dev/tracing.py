from __future__ import annotations

import os
from typing import Any


def configure_tracing(settings: Any) -> dict[str, str]:
    """Return safe opt-in tracing environment settings without exposing credentials."""
    if not settings.tracing_enabled:
        return {}
    values = {"LANGCHAIN_TRACING_V2": "true"}
    project = os.getenv("LANGCHAIN_PROJECT", "dev-coding-agent")
    values["LANGCHAIN_PROJECT"] = project
    # LangChain reads the API key from the process environment; never copy it into logs/state.
    return values

