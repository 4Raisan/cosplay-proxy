"""Cosplay proxy — token estimation helpers.

Uses tiktoken (cl100k_base) when available and falls back to a character
heuristic otherwise. Estimates are used for the input_tokens field because
most upstream providers only report usage at the end of a stream.
"""

from __future__ import annotations

from typing import Any

_tiktoken_encoder = None


def _get_encoder():
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            import tiktoken

            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_encoder = False
    return _tiktoken_encoder if _tiktoken_encoder else None


def estimate_tokens(text: str) -> int:
    """Estimate the token count for a string."""
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    return max(1, int(len(text) / 4))


def estimate_messages_tokens(
    messages: list[Any], system: str | None = None
) -> int:
    """Estimate the token count for a message list (plus optional system)."""
    total = 0
    for msg in messages:
        total += 4
        if msg.get("role") == "assistant":
            total += 8
        content = msg.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                text = _block_text(block)
                if text:
                    total += estimate_tokens(text)
    if system:
        total += estimate_tokens(system)
    return total


def _block_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    if block.get("type") == "tool_result":
        return _tool_result_text(block.get("content"))
    if block.get("type") == "text":
        return str(block.get("text", ""))
    return ""


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(str(c.get("text", "")))
            elif isinstance(c, str):
                parts.append(c)
        return "".join(parts)
    return ""
