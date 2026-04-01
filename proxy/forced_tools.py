"""Cosplay proxy — forced Anthropic web server tool turns.

When Claude Code forces a ``web_search`` / ``web_fetch`` server tool via
``tool_choice``, the proxy executes the tool locally and streams back a
single turn containing the tool_use, its result, and a text summary — without
calling the model.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from .chat_sse import sse
from .errors import InvalidRequest
from .schemas import ContentBlock, MessagesRequest
from .tokens import estimate_messages_tokens
from .web_tools import execute_server_tool

SERVER_TOOL_NAMES = {"web_search", "web_fetch"}


def forced_server_tool_name(request: MessagesRequest) -> str | None:
    """Return web_search/web_fetch when tool_choice forces that server tool."""
    choice = request.tool_choice
    if choice is None or choice.type != "tool" or not choice.name:
        return None
    name = choice.name
    if name in SERVER_TOOL_NAMES:
        return name
    return None


def has_tool_named(request: MessagesRequest, name: str) -> bool:
    return any(tool.name == name for tool in (request.tools or []))


def is_web_server_tool_request(request: MessagesRequest) -> bool:
    """True when the client forces a web server tool (and lists it)."""
    forced = forced_server_tool_name(request)
    if forced is None:
        return False
    return has_tool_named(request, forced)


def _forced_tool_turn_text(request: MessagesRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            if isinstance(message.content, str):
                return message.content
            return "\n".join(_block_text(b) for b in message.content if _block_text(b))
    return ""


def _block_text(block: ContentBlock) -> str:
    if block.type == "text" and block.text:
        return block.text
    if block.type == "tool_result":
        content = block.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(b.text or "" for b in content if b.type == "text")
    return ""


def extract_query(text: str) -> str:
    match = re.search(r"query:\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip().strip("\"'")
    return text.strip()


def extract_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip(").,]") if match else text.strip()


async def stream_forced_web_tool_response(
    request: MessagesRequest,
    *,
    gateway_model: str,
) -> AsyncIterator[str]:
    """Stream the forced server-tool turn (tool_use + result + summary)."""
    tool_name = forced_server_tool_name(request)
    if tool_name is None or not has_tool_named(request, tool_name):
        raise InvalidRequest(f"Unknown forced server tool: {tool_name}")

    text = _forced_tool_turn_text(request)
    tool_id = f"srvtoolu_{uuid.uuid4().hex}"
    if tool_name == "web_search":
        tool_input = {"query": extract_query(text)}
    else:
        tool_input = {"url": extract_url(text)}

    input_tokens = estimate_messages_tokens(
        [m.model_dump() for m in request.messages], request.system_text()
    )

    yield sse(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": f"msg_{uuid.uuid4()}",
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": gateway_model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": input_tokens, "output_tokens": 1},
            },
        },
    )

    yield sse(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "server_tool_use",
                "id": tool_id,
                "name": tool_name,
                "input": tool_input,
            },
        },
    )
    yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})

    try:
        result_text = await execute_server_tool(tool_name, tool_input)
        result_block: dict = {"type": "text", "text": result_text}
        result_block_type = (
            "web_search_tool_result"
            if tool_name == "web_search"
            else "web_fetch_tool_result"
        )
        summary = result_text
    except Exception as error:
        result_block = {
            "type": "web_search_tool_result_error"
            if tool_name == "web_search"
            else "web_fetch_tool_error",
            "error_code": "unavailable",
        }
        result_block_type = (
            "web_search_tool_result"
            if tool_name == "web_search"
            else "web_fetch_tool_result"
        )
        summary = f"{tool_name} failed: {type(error).__name__}"
    finally:
        # Ensure result_block / summary are always defined.
        pass

    yield sse(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": result_block_type,
                "tool_use_id": tool_id,
                "content": result_block,
            },
        },
    )
    yield sse("content_block_stop", {"type": "content_block_stop", "index": 1})

    yield sse(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 2,
            "content_block": {"type": "text", "text": ""},
        },
    )
    yield sse(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 2,
            "delta": {"type": "text_delta", "text": summary},
        },
    )
    yield sse("content_block_stop", {"type": "content_block_stop", "index": 2})

    output_tokens = max(1, len(summary) // 4)
    yield sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "server_tool_use": {
                    "web_search_requests" if tool_name == "web_search" else "web_fetch_requests": 1
                },
            },
        },
    )
    yield sse("message_stop", {"type": "message_stop"})
