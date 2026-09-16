from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

_SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)\S+")


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET.sub(r"\1\2[REDACTED]", value)
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(r"(?i)(key|token|password|secret)", str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(redact({"level": record.levelname, "message": record.getMessage(), "logger": record.name}), ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=[handler], force=True)

