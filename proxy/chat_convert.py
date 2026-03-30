"""Cosplay proxy — Anthropic request to OpenAI chat payload conversion."""

from __future__ import annotations

import base64
import json
from typing import Any

from .effort import (
    admin_level_for_slot,
    apply_effort,
    resolve_effort,
)
from .routing import RouteTarget
from .schemas import MessagesRequest, ToolDefinition, block_text

# Server tool types declared by Claude Code.
SERVER_TOOL_TYPES = {"web_search_20250305", "web_fetch_20250404"}


def build_chat_payload(
    request: MessagesRequest,
    target: RouteTarget,
    *,
    extra_tools: list[dict[str, Any]] | None = None,
    include_server_tools: bool = True,
    slot: str | None = None,
) -> dict[str, Any]:
    """Convert an Anthropic MessagesRequest to an OpenAI chat payload."""
    payload: dict[str, Any] = {
        "model": target.model,
        "messages": _build_messages(request),
        "stream": True,
    }

    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.stop_sequences:
        payload["stop"] = request.stop_sequences

    # Thinking / effort arbitration (admin level, client /effort, model cap).
    directive = resolve_effort(
        admin_level_for_slot(slot),
        request.client_effort(),
        target,
    )
    apply_effort(payload, directive)

    tools: list[dict[str, Any]] = []
    if request.tools:
        for tool in request.tools:
            converted = _convert_tool(tool)
            if converted is not None:
                tools.append(converted)
    if include_server_tools:
        for extra in extra_tools or []:
            tools.append(extra)

    if tools:
        payload["tools"] = tools
        tool_choice = _convert_tool_choice(request, tools)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

    return payload


def _build_messages(request: MessagesRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    system_text = request.system_text()
    if system_text:
        out.append({"role": "system", "content": system_text})

    for msg in request.messages:
        role = msg.role
        content = msg.content
        if isinstance(content, str):
            if not content:
                continue
            out.append({"role": _openai_role(role), "content": content})
            continue

        blocks = content or []
        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in blocks:
                if block.type == "text":
                    text_parts.append(block.text or "")
                elif block.type == "tool_use" and block.name:
                    tool_calls.append(
                        {
                            "id": block.id or f"toolu_{len(tool_calls)}",
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(
                                    block.input or {}, ensure_ascii=False
                                ),
                            },
                        }
                    )
                # thinking / redacted_thinking blocks are dropped upstream.
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(text_parts) or None,
            }
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
            continue

        if role == "user":
            text_parts = []
            tool_results: list[dict[str, Any]] = []
            images: list[dict[str, Any]] = []
            for block in blocks:
                if block.type == "text":
                    text_parts.append(block.text or "")
                elif block.type == "image":
                    image_url = _image_url(block)
                    if image_url:
                        images.append(
                            {"type": "image_url", "image_url": {"url": image_url}}
                        )
                elif block.type == "tool_result" and block.tool_use_id:
                    tool_results.append(
                        {
                            "tool_call_id": block.tool_use_id,
                            "content": _tool_result_text(block),
                        }
                    )
            if tool_results:
                for tr in tool_results:
                    out.append({"role": "tool", **tr})
                continue
            parts: list[str] = []
            parts.extend(
                {"type": "text", "text": t} for t in text_parts if t
            )
            parts.extend(images)
            if not parts:
                continue
            if len(parts) == 1 and parts[0].get("type") == "text":
                out.append({"role": "user", "content": parts[0]["text"]})
            else:
                out.append({"role": "user", "content": parts})
            continue

        # Any other role (e.g. a stray assistant turn) is passed through.
        out.append({"role": _openai_role(role), "content": block_text_all(blocks)})

    return out


def block_text_all(blocks: list[Any]) -> str:
    parts = []
    for block in blocks:
        try:
            parts.append(block_text(block))
        except Exception:
            continue
    return "\n".join(parts)


def _tool_result_text(block: Any) -> str:
    content = block.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return block_text_all(content)
    return ""


def _image_url(block: Any) -> str | None:
    source = block.content
    if not isinstance(source, dict):
        return None
    media_type = source.get("media_type")
    data = source.get("data")
    if not data:
        return None
    try:
        encoded = base64.b64encode(base64.b64decode(data)).decode("ascii")
    except Exception:
        return None
    return f"data:{media_type or 'image/jpeg'};base64,{encoded}"


def _convert_tool(tool: ToolDefinition) -> dict[str, Any] | None:
    if tool.type in SERVER_TOOL_TYPES:
        # Server tools are injected by the handler, not passed as-is.
        return None
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def _convert_tool_choice(
    request: MessagesRequest, tools: list[dict[str, Any]]
) -> Any:
    if not request.tool_choice:
        return None
    choice = request.tool_choice
    if choice.type == "any":
        return "required"
    if choice.type == "tool" and choice.name:
        return {
            "type": "function",
            "function": {"name": choice.name},
        }
    if choice.type == "none":
        return "none"
    return "auto"


def _openai_role(role: str) -> str:
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"
    return role
