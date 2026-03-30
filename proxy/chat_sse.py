"""Cosplay proxy — OpenAI chat SSE to Anthropic Messages SSE translation."""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from .tokens import estimate_tokens


def sse(event: str, data: dict[str, Any]) -> str:
    """Frame one SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class AnthropicStreamTranslator:
    """Translate OpenAI chat-completions SSE chunks into Anthropic events."""

    def __init__(
        self,
        gateway_model: str,
        *,
        request_id: str | None = None,
        input_tokens: int = 0,
    ) -> None:
        self.gateway_model = gateway_model
        self.request_id = request_id
        self.input_tokens = input_tokens
        self.message_id = f"msg_{request_id or uuid.uuid4()}"
        self._started = False
        self._ended = False

        # Block bookkeeping (ordered like Anthropic expects).
        self._thinking_started = False
        self._thinking_stopped = False
        self._text_started = False
        self._text_stopped = False
        self._tool_blocks: dict[int, dict[str, Any]] = {}
        self._next_index = 0

        self._usage: dict[str, Any] = {}
        self._stop_reason: str | None = None
        self._stop_sequence: str | None = None
        self._streamed_chars = 0

    # -- lifecycle ----------------------------------------------------------

    def _ensure_started(self) -> list[str]:
        if self._started:
            return []
        self._started = True
        message = {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "model": self.gateway_model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": 0,
            },
        }
        return [
            sse(
                "message_start",
                {"type": "message_start", "message": message},
            )
        ]

    def translate(self, chunk: dict[str, Any]) -> list[str]:
        """Translate one upstream chunk into a list of Anthropic SSE strings."""
        events: list[str] = []
        events.extend(self._ensure_started())

        if "usage" in chunk and chunk["usage"]:
            self._usage = chunk["usage"] or self._usage

        choices = chunk.get("choices") or []
        for choice in choices:
            delta = choice.get("delta") or {}
            if choice.get("finish_reason"):
                self._stop_reason = self._map_stop_reason(
                    choice.get("finish_reason")
                )
            events.extend(self._translate_delta(delta))

        if self._usage.get("completion_tokens") is not None:
            # Reflect cumulative output tokens on each usage-bearing chunk.
            events.extend(self._maybe_usage_delta())
        return events

    def finish(self) -> list[str]:
        """Flush remaining blocks and emit terminal events."""
        if self._ended:
            return []
        self._ended = True
        events: list[str] = []
        if not self._started:
            events.extend(self._ensure_started())

        events.extend(self._close_thinking())
        events.extend(self._close_text())
        events.extend(self._close_tool_blocks())
        events.append(self._usage_delta())
        events.append(sse("message_stop", {"type": "message_stop"}))
        return events

    # -- delta routing ------------------------------------------------------

    def _translate_delta(self, delta: dict[str, Any]) -> list[str]:
        events: list[str] = []

        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning:
            events.extend(self._reasoning_delta(str(reasoning)))

        content = delta.get("content")
        if content:
            events.extend(self._text_delta(str(content)))

        tool_calls = delta.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                events.extend(self._tool_call_delta(tc))

        return events

    # -- reasoning ----------------------------------------------------------

    def _reasoning_delta(self, text: str) -> list[str]:
        events: list[str] = []
        if not self._thinking_started:
            self._thinking_started = True
            events.append(
                sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": self._next_index,
                        "content_block": {"type": "thinking", "thinking": ""},
                    },
                )
            )
            self._next_index += 1
        if not self._thinking_stopped:
            self._streamed_chars += len(text)
            events.append(
                sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": self._thinking_index,
                        "delta": {"type": "thinking_delta", "thinking": text},
                    },
                )
            )
        return events

    @property
    def _thinking_index(self) -> int:
        # Thinking is always emitted before text/tool blocks, so its index is 0.
        return 0

    def _close_thinking(self) -> list[str]:
        if not self._thinking_started or self._thinking_stopped:
            return []
        self._thinking_stopped = True
        return [sse("content_block_stop", {"type": "content_block_stop", "index": 0})]

    # -- text ---------------------------------------------------------------

    def _text_delta(self, text: str) -> list[str]:
        events: list[str] = []
        events.extend(self._close_thinking())
        if not self._text_started:
            self._text_started = True
            events.append(
                sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": self._text_index,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            )
        if not self._text_stopped:
            self._streamed_chars += len(text)
            events.append(
                sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": self._text_index,
                        "delta": {"type": "text_delta", "text": text},
                    },
                )
            )
        return events

    @property
    def _text_index(self) -> int:
        return 1 if self._thinking_started else 0

    def _close_text(self) -> list[str]:
        if not self._text_started or self._text_stopped:
            return []
        self._text_stopped = True
        return [
            sse(
                "content_block_stop",
                {"type": "content_block_stop", "index": self._text_index},
            )
        ]

    # -- tool calls ---------------------------------------------------------

    def _tool_call_delta(self, tc: dict[str, Any]) -> list[str]:
        events: list[str] = []
        index = int(tc.get("index", 0))
        block = self._tool_blocks.get(index)
        if block is None:
            block = {
                "started": False,
                "block_index": None,
                "id": tc.get("id") or "",
                "name": "",
                "args": "",
            }
            self._tool_blocks[index] = block

        if tc.get("id"):
            block["id"] = tc["id"]

        function = tc.get("function") or {}
        if function.get("name"):
            block["name"] = function["name"]

        if not block["started"]:
            block["started"] = True
            block["block_index"] = self._next_index
            self._next_index += 1
            events.extend(self._close_thinking())
            events.extend(self._close_text())
            events.append(
                sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block["block_index"],
                        "content_block": {
                            "type": "tool_use",
                            "id": block["id"] or f"toolu_{index}",
                            "name": block["name"],
                            "input": {},
                        },
                    },
                )
            )

        if function.get("arguments"):
            block["args"] += function["arguments"]
            events.append(
                sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block["block_index"],
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": function["arguments"],
                        },
                    },
                )
            )
        return events

    def _close_tool_blocks(self) -> list[str]:
        events: list[str] = []
        for index in sorted(self._tool_blocks):
            block = self._tool_blocks[index]
            if block["started"]:
                events.append(
                    sse(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": block["block_index"]},
                    )
                )
        return events

    # -- usage / stop -------------------------------------------------------

    def _map_stop_reason(self, finish_reason: str | None) -> str | None:
        if not finish_reason:
            return None
        if finish_reason == "stop":
            return "end_turn"
        if finish_reason in ("tool_calls", "function_call"):
            return "tool_use"
        if finish_reason == "length":
            return "max_tokens"
        return "end_turn"

    def _usage_delta(self) -> str:
        return sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": self._stop_reason or "end_turn",
                    "stop_sequence": self._stop_sequence,
                },
                "usage": {
                    "input_tokens": self.input_tokens,
                    "output_tokens": self._output_tokens,
                },
            },
        )

    def _maybe_usage_delta(self) -> list[str]:
        # Intermediate usage deltas are optional; skip to keep the stream clean.
        return []

    @property
    def _output_tokens(self) -> int:
        completion = self._usage.get("completion_tokens")
        if completion is not None:
            return int(completion)
        return estimate_tokens(("x" * self._streamed_chars))


def translate_nonstream_response(
    data: dict[str, Any],
    gateway_model: str,
    *,
    request_id: str | None = None,
    input_tokens: int = 0,
) -> dict[str, Any]:
    """Build an Anthropic Messages response from a non-streaming completion."""
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}

    content: list[dict[str, Any]] = []
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if reasoning:
        content.append({"type": "thinking", "thinking": str(reasoning)})
    text = message.get("content")
    if text:
        content.append({"type": "text", "text": str(text)})
    for tc in message.get("tool_calls") or []:
        function = tc.get("function") or {}
        try:
            parsed_input = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            parsed_input = {}
        content.append(
            {
                "type": "tool_use",
                "id": tc.get("id") or f"toolu_{len(content)}",
                "name": function.get("name") or "",
                "input": parsed_input,
            }
        )

    finish = choice.get("finish_reason")
    if finish in ("tool_calls", "function_call"):
        stop_reason = "tool_use"
    elif finish == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    output_tokens = int(usage.get("completion_tokens") or 0)
    return {
        "id": f"msg_{request_id or uuid.uuid4()}",
        "type": "message",
        "role": "assistant",
        "model": gateway_model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or input_tokens),
            "output_tokens": output_tokens,
        },
    }
