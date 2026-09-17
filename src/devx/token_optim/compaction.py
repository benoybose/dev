from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompactionResult:
    messages: list[dict[str, str]]
    compacted: bool
    removed_messages: int = 0


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", message))


def _bounded_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def compact_messages(messages: list[dict[str, str]], *, max_messages: int = 24,
                     max_chars: int = 24_000, summary_chars: int = 4_000) -> CompactionResult:
    """Keep session history bounded without requiring another model call.

    The newest messages are retained verbatim. Older messages are represented
    by a bounded, role-labelled summary so persisted sessions remain useful
    even when a long repair loop produces many events.
    """
    normalized = [
        {"role": str(item.get("role", "assistant")), "content": _message_text(item)}
        for item in messages
        if isinstance(item, dict)
    ]
    if not normalized:
        return CompactionResult([], False)
    total_chars = sum(len(item["role"]) + len(item["content"]) for item in normalized)
    if len(normalized) <= max_messages and total_chars <= max_chars:
        return CompactionResult(normalized, False)

    keep = max(2, min(len(normalized), max_messages - 1))
    older = normalized[:-keep]
    recent = normalized[-keep:]
    lines: list[str] = []
    remaining = max(128, summary_chars)
    for item in older:
        line = f"{item['role']}: {item['content'].strip()}"
        if not line.strip():
            continue
        piece = _bounded_text(line, min(remaining, 1_000))
        if len(piece) + 1 > remaining:
            break
        lines.append(piece)
        remaining -= len(piece) + 1
    summary = "Compacted session history:\n" + "\n".join(lines)
    compacted = [{"role": "summary", "content": _bounded_text(summary, summary_chars)}] + recent

    # A summary plus recent messages should be bounded even if a single
    # message is unusually large.
    while len(compacted) > 1 and (
        len(compacted) > max_messages
        or sum(len(item["role"]) + len(item["content"]) for item in compacted) > max_chars
    ):
        compacted.pop(1)
    if len(compacted) == 1 and len(compacted[0]["content"]) > max_chars:
        compacted[0] = {"role": "summary", "content": _bounded_text(compacted[0]["content"], max_chars)}
    return CompactionResult(compacted, True, len(older))


def append_message(messages: list[dict[str, str]], role: str, content: str, *, enabled: bool = True,
                   max_messages: int = 24, max_chars: int = 24_000, summary_chars: int = 4_000) -> CompactionResult:
    updated = [*messages, {"role": role, "content": str(content)}]
    result = compact_messages(
        updated,
        max_messages=max_messages,
        max_chars=max_chars,
        summary_chars=summary_chars,
    ) if enabled else CompactionResult(updated, False)
    messages[:] = result.messages
    return result
