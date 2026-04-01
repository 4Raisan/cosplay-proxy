"""Cosplay proxy — OpenAI Responses API endpoint (streaming)."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from config.routing import RoutingManager
from providers.registry import ProviderRegistry

from .auth import require_proxy_auth
from .chat_convert import build_chat_payload
from .chat_sse import sse
from .errors import ProxyError, anthropic_error_payload, upstream_error_message
from .routing import resolve_route, resolve_slot
from .schemas import (
    MessagesRequest,
    OutputConfig,
    AnthropicMessage,
    ContentBlock,
    ToolDefinition,
)
from .upstream import UpstreamClient

router = APIRouter()

SSE_HEADERS = {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "x-accel-buffering": "no",
}


class ResponsesInputItem(BaseModel):
    """One OpenAI Responses input item."""

    model_config = ConfigDict(extra="ignore")

    type: str = "message"
    role: str = "user"
    content: str | list[Any] = ""
    output: list[Any] | None = None


class ResponsesRequest(BaseModel):
    """OpenAI Responses request payload (subset used by Claude Code/SDKs)."""

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    input: str | list[ResponsesInputItem | str] = ""
    instructions: str | None = None
    max_output_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    output_config: dict[str, Any] | None = None

    def to_messages_request(self) -> MessagesRequest:
        """Convert the Responses request into an Anthropic MessagesRequest."""
        system = self.instructions
        messages: list[AnthropicMessage] = []
        raw_input = self.input

        if isinstance(raw_input, str):
            messages.append(
                AnthropicMessage(role="user", content=raw_input)
            )
        else:
            for item in raw_input:
                if isinstance(item, str):
                    messages.append(AnthropicMessage(role="user", content=item))
                    continue
                role = getattr(item, "role", "user") or "user"
                if getattr(item, "type", "message") == "function_call_output":
                    messages.append(
                        AnthropicMessage(
                            role="user",
                            content=[
                                ContentBlock(
                                    type="tool_result",
                                    tool_use_id=getattr(item, "call_id", ""),
                                    content=str(getattr(item, "output", "")),
                                )
                            ],
                        )
                    )
                    continue
                messages.append(
                    AnthropicMessage(
                        role=role,
                        content=_normalize_content(getattr(item, "content", "")),
                    )
                )

        tools = [
            ToolDefinition(
                name=t.get("name", "") if isinstance(t, dict) else "",
                description=(t.get("description") or "") if isinstance(t, dict) else "",
                input_schema=(t.get("parameters") or {}) if isinstance(t, dict) else {},
            )
            for t in (self.tools or [])
            if isinstance(t, dict) and t.get("name")
        ]
        return MessagesRequest(
            model=self.model,
            max_tokens=self.max_output_tokens,
            messages=messages,
            system=system,
            tools=tools or None,
            stream=self.stream,
            temperature=self.temperature,
            top_p=self.top_p,
            output_config=(
                OutputConfig.model_validate(self.output_config)
                if self.output_config
                else None
            ),
        )


def _normalize_content(content: str | list[Any]) -> str | list[ContentBlock]:
    if isinstance(content, str):
        return content
    blocks = []
    for part in content:
        if isinstance(part, str):
            blocks.append(ContentBlock(type="text", text=part))
        elif isinstance(part, dict):
            if part.get("type") == "text":
                blocks.append(
                    ContentBlock(type="text", text=part.get("text", ""))
                )
            elif part.get("type") == "input_text":
                blocks.append(
                    ContentBlock(type="text", text=part.get("text", ""))
                )
    return blocks or ""


@router.post("/v1/responses")
async def create_response(
    request: Request,
    _auth: None = Depends(require_proxy_auth),
) -> Any:
    rid = request.headers.get("x-request-id") or request.headers.get(
        "request-id"
    ) or uuid.uuid4().hex
    try:
        raw = await request.json()
        payload = ResponsesRequest.model_validate(raw)
    except Exception as exc:
        return StreamingResponse(
            _error_stream(f"Invalid request body: {exc}", rid),
            media_type="text/event-stream",
            headers={**SSE_HEADERS, "request-id": rid, "x-request-id": rid},
        )

    try:
        routing = RoutingManager().get()
        registry = ProviderRegistry()
        target = resolve_route(payload.model or "claude-cosplay-default", routing, registry)
    except ProxyError as exc:
        return StreamingResponse(
            _error_stream(str(exc), rid),
            media_type="text/event-stream",
            headers={**SSE_HEADERS, "request-id": rid, "x-request-id": rid},
        )

    if not payload.stream:
        return StreamingResponse(
            _error_stream(
                "FCC-style non-streaming Responses is not supported; set stream=true.",
                rid,
            ),
            media_type="text/event-stream",
            headers={**SSE_HEADERS, "request-id": rid, "x-request-id": rid},
        )

    messages_request = payload.to_messages_request()
    slot = resolve_slot(payload.model)
    body = build_chat_payload(messages_request, target, slot=slot)
    gateway_model = payload.model or "claude-cosplay-default"

    stream = _responses_stream(body, target, gateway_model, rid)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={**SSE_HEADERS, "request-id": rid, "x-request-id": rid},
    )


async def _responses_stream(
    body: dict[str, Any],
    target: Any,
    gateway_model: str,
    rid: str,
) -> AsyncIterator[str]:
    client = UpstreamClient(target)
    payload = dict(body)
    payload["model"] = target.model

    response_id = f"resp_{rid}"
    item_id = f"msg_{rid}"
    created = int(time.time())

    yield sse(
        "response.created",
        {
            "type": "response.created",
            "response": _response_skeleton(
                response_id, gateway_model, created, status="in_progress"
            ),
        },
    )
    yield sse("response.in_progress", {"type": "response.in_progress"})
    yield sse(
        "response.output_item.added",
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": item_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        },
    )
    yield sse(
        "response.content_part.added",
        {
            "type": "response.content_part.added",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        },
    )

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: dict[str, Any] = {}
    tool_calls: list[dict[str, Any]] = []
    current_tool: dict[str, Any] | None = None
    finish_reason: str | None = None

    try:
        first_chunk = True
        async for chunk in client.stream_chat(payload):
            if first_chunk:
                first_chunk = False
                _mark_model_used(target)
            if chunk.get("usage"):
                usage = chunk["usage"] or usage
            for choice in chunk.get("choices") or []:
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
                delta = choice.get("delta") or {}

                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    reasoning_parts.append(str(reasoning))

                content = delta.get("content")
                if content:
                    text_parts.append(str(content))
                    yield sse(
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "delta": str(content),
                        },
                    )

                for tc in delta.get("tool_calls") or []:
                    index = int(tc.get("index", 0))
                    while len(tool_calls) <= index:
                        tool_calls.append(
                            {
                                "id": "",
                                "type": "function_call",
                                "name": "",
                                "arguments": "",
                                "status": "in_progress",
                            }
                        )
                    target_tool = tool_calls[index]
                    if tc.get("id"):
                        target_tool["id"] = tc["id"]
                    function = tc.get("function") or {}
                    if function.get("name"):
                        target_tool["name"] = function["name"]
                    if function.get("arguments"):
                        target_tool["arguments"] += function["arguments"]
                        yield sse(
                            "response.function_call_arguments.delta",
                            {
                                "type": "response.function_call_arguments.delta",
                                "item_id": f"fc_{rid}_{index}",
                                "output_index": index + 1,
                                "delta": function["arguments"],
                            },
                        )
    except Exception as exc:
        yield sse(
            "response.failed",
            {
                "type": "response.failed",
                "response": _error_response_skeleton(
                    response_id, gateway_model, created, str(exc)
                ),
            },
        )
        yield sse(
            "error",
            anthropic_error_payload("api_error", upstream_error_message(exc)),
        )
        return

    text = "".join(text_parts)

    if reasoning_parts:
        reasoning_text = "".join(reasoning_parts)
        yield sse(
            "response.reasoning_summary_text.delta",
            {
                "type": "response.reasoning_summary_text.delta",
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "summary_text": reasoning_text,
            },
        )

    yield sse(
        "response.output_text.done",
        {
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "text": text,
        },
    )
    yield sse(
        "response.content_part.done",
        {
            "type": "response.content_part.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": text, "annotations": []},
        },
    )

    content_items: list[dict[str, Any]] = [
        {"type": "output_text", "text": text, "annotations": []}
    ]
    if tool_calls:
        for i, tc in enumerate(tool_calls):
            content_items.append(
                {
                    "type": "function_call",
                    "id": tc["id"] or f"fc_{i}",
                    "call_id": tc["id"] or f"fc_{i}",
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                    "status": "completed",
                }
            )

    yield sse(
        "response.output_item.done",
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": content_items,
            },
        },
    )

    for i in range(1, len(tool_calls) + 1):
        tc = tool_calls[i - 1]
        yield sse(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "output_index": i,
                "item": {
                    "id": f"fc_{rid}_{i - 1}",
                    "type": "function_call",
                    "status": "completed",
                    "call_id": tc["id"] or f"fc_{i - 1}",
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            },
        )

    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    total = input_tokens + output_tokens

    response = _response_skeleton(
        response_id, gateway_model, created, status="completed"
    )
    response["output"] = [
        {
            "id": item_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": content_items,
        }
    ]
    response["usage"] = {
        "input_tokens": input_tokens,
        "input_tokens_details": {},
        "output_tokens": output_tokens,
        "output_tokens_details": {},
        "total_tokens": total,
    }
    response["incomplete_details"] = (
        {"reason": "max_output_tokens"} if finish_reason == "length" else None
    )
    yield sse("response.completed", {"type": "response.completed", "response": response})


def _response_skeleton(
    response_id: str, model: str, created: int, *, status: str
) -> dict[str, Any]:
    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": status,
        "model": model,
        "output": [],
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": None,
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": None,
        "store": True,
        "temperature": 1.0,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 0,
            "input_tokens_details": {},
            "output_tokens": 0,
            "output_tokens_details": {},
            "total_tokens": 0,
        },
        "user": None,
    }


def _error_response_skeleton(
    response_id: str, model: str, created: int, message: str
) -> dict[str, Any]:
    skeleton = _response_skeleton(response_id, model, created, status="failed")
    skeleton["error"] = {
        "code": "server_error",
        "message": message,
        "param": None,
        "type": "server_error",
    }
    return skeleton


async def _error_stream(message: str, rid: str) -> AsyncIterator[str]:
    yield sse(
        "error",
        anthropic_error_payload("api_error", message, request_id=rid),
    )


def _mark_model_used(target: Any) -> None:
    """Remember a model that actually served a successful upstream request."""
    try:
        from config.model_caps import ModelCapsManager
        from .effort import _heuristic_rank

        ModelCapsManager().mark_model_used(
            target.provider_id,
            target.model,
            supports_thinking=True,
            max_rank=_heuristic_rank(target.model),
        )
    except Exception:
        pass
