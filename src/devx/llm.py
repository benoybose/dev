from __future__ import annotations

import time
from typing import Any


class ModelConfigurationError(RuntimeError):
    pass


def invoke_with_retry(model: Any, prompt: Any, *, attempts: int = 3, base_delay: float = 0.5):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return model.invoke(prompt)
        except (TimeoutError, ConnectionError, OSError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(base_delay * (2 ** attempt))
    raise last_error or RuntimeError("Model invocation failed")


def create_llm(settings: Any):
    """Create a LangChain chat model lazily so the base package remains offline-capable."""
    try:
        if settings.provider in {"openai", "azure"}:
            from langchain_openai import ChatOpenAI
            kwargs = {"model": settings.model, "api_key": settings.api_key, "temperature": 0.1, "max_retries": 2}
            if settings.provider == "azure":
                kwargs.update(azure_deployment=settings.model)
            else:
                kwargs["base_url"] = settings.base_url
            return ChatOpenAI(**kwargs)
        if settings.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=settings.model, api_key=settings.api_key, temperature=0.1, max_retries=2)
        if settings.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=settings.model, google_api_key=settings.api_key, temperature=0.1)
    except ImportError as exc:
        raise ModelConfigurationError(f"Install the optional dependency for provider '{settings.provider}'") from exc
    raise ModelConfigurationError(f"Unsupported provider: {settings.provider}")
