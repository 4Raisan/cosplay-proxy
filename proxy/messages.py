"""Cosplay proxy — Anthropic Messages API endpoints.

Implements ``POST /v1/messages`` (SSE + JSON) and ``POST /v1/messages/count_tokens``
natively, routing through Cosplay's provider registry with per-provider fallback.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config.routing import RoutingManager
from providers.registry import ProviderRegistry

from .auth import require_proxy_auth
from .chat_convert import build_chat_payload
from .chat_sse import AnthropicStreamTranslator, translate_nonstream_response
from .errors import InvalidRequest, ProxyError, anthropic_error_payload, http_status, upstream_error_message
from .forced_tools import is_web_server_tool_request, stream_forced_web_tool_response
from .rate_limit import check_rate_limit
from .routing import fallback_targets, resolve_route, resolve_slot
from .schemas import MessagesRequest
from .tokens import estimate_messages_tokens
from .upstream import UpstreamClient

router = APIRouter()

ANTHROPIC_SSE_HEADERS = {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "x-accel-buffering": "no",
}


def _request_id(request: Request) -> str:
    rid = request.headers.get("x-request-id") or request.headers.get("request-id")
    return rid or uuid.uuid4().hex


@router.post("/v1/messages")
async def create_message(
    request: Request,
    _auth: None = Depends(require_proxy_auth),
) -> Any:
    rid = _request_id(request)
    try:
        raw = await request.json()
        payload = MessagesRequest.model_validate(raw)
    except Exception as exc:
        return _error_response(
            "invalid_request_error", f"Invalid request body: {exc}", rid
        )

    if not payload.messages and not is_web_server_tool_request(payload):
        return _error_response(
            "invalid_request_error",
            "messages: Field required (must provide at least one message).",
            rid,
        )

    gateway_model = payload.model or "claude-cosplay-default"
    slot = resolve_slot(gateway_model)

    if is_web_server_tool_request(payload):
        return StreamingResponse(
            stream_forced_web_tool_response(payload, gateway_model=gateway_model),
            media_type="text/event-stream",
            headers={**ANTHROPIC_SSE_HEADERS, "request-id": rid, "x-request-id": rid},
        )

    try:
        routing = RoutingManager().get()
        registry = ProviderRegistry()
        target = resolve_route(gateway_model, routing, registry)
        fallbacks = fallback_targets(routing, registry)
        input_tokens = estimate_messages_tokens(
            [m.model_dump() for m in payload.messages], payload.system_text()
        )
    except ProxyError as exc:
        return _error_response(
            _error_type_for(exc), str(exc), rid
        )

    try:
        await check_rate_limit(target.provider_id)
    except ProxyError as exc:
        return _error_response(_error_type_for(exc), str(exc), rid)

    if not payload.stream:
        return await _handle_non_streaming(
            payload, gateway_model, target, fallbacks, rid, slot
        )

    body = _build_upstream_body(payload, target, slot)
    stream = _stream_with_fallback(
        payload, gateway_model, target, fallbacks, body, rid, input_tokens
    )

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={**ANTHROPIC_SSE_HEADERS, "request-id": rid, "x-request-id": rid},
    )


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: Request,
    _auth: None = Depends(require_proxy_auth),
) -> Any:
    rid = _request_id(request)
    try:
        raw = await request.json()
        payload = MessagesRequest.model_validate(raw)
    except Exception as exc:
        return _error_response(
            "invalid_request_error", f"Invalid request body: {exc}", rid
        )
    tokens = estimate_messages_tokens(
        [m.model_dump() for m in payload.messages], payload.system_text()
    )
    return JSONResponse(
        {
            "input_tokens": tokens,
            "output_tokens": 0,
        }
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _build_upstream_body(
    payload: MessagesRequest,
    target: Any,
    slot: str | None,
) -> dict[str, Any]:
    return build_chat_payload(payload, target, slot=slot)


async def _stream_with_fallback(
    payload: MessagesRequest,
    gateway_model: str,
    primary: Any,
    fallback_refs: list[str],
    body: dict[str, Any],
    rid: str,
    input_tokens: int,
) -> AsyncIterator[str]:
    attempts: list[Any] = [primary]
    for ref in fallback_refs:
        try:
            registry = ProviderRegistry()
            from .routing import _ref_to_target

            attempts.append(_ref_to_target(ref, registry, None))
        except ProxyError:
            continue

    last_error: Exception | None = None
    for attempt in attempts:
        if attempt.provider_id != primary.provider_id:
            try:
                await check_rate_limit(attempt.provider_id)
            except ProxyError as exc:
                last_error = exc
                continue
        stream = _stream_one_attempt(
            payload, gateway_model, attempt, body, rid, input_tokens
        )
        sent_any = False
        try:
            async for event in stream:
                sent_any = True
                yield event
            return
        except Exception as exc:
            last_error = exc
            if sent_any:
                raise

    if last_error:
        yield _terminal_error_events(last_error)


async def _stream_one_attempt(
    payload: MessagesRequest,
    gateway_model: str,
    target: Any,
    body: dict[str, Any],
    rid: str,
    input_tokens: int,
) -> AsyncIterator[str]:
    client = UpstreamClient(target)
    translator = AnthropicStreamTranslator(
        gateway_model, request_id=rid, input_tokens=input_tokens
    )
    payload_body = dict(body)
    payload_body["model"] = target.model
    async for chunk in client.stream_chat(payload_body):
        _mark_model_used(target)
        for event in translator.translate(chunk):
            yield event
    for event in translator.finish():
        yield event


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


def _terminal_error_events(error: Exception) -> list[str]:
    from .chat_sse import sse

    payload = anthropic_error_payload(
        "api_error", upstream_error_message(error)
    )
    return [sse("error", payload)]


async def _handle_non_streaming(
    payload: MessagesRequest,
    gateway_model: str,
    target: Any,
    fallback_refs: list[str],
    rid: str,
    slot: str | None,
) -> JSONResponse:
    last_error: Exception | None = None
    attempts: list[Any] = [target]
    for ref in fallback_refs:
        try:
            from .routing import _ref_to_target

            attempts.append(_ref_to_target(ref, ProviderRegistry(), None))
        except ProxyError:
            continue

    for attempt in attempts:
        if attempt.provider_id != target.provider_id:
            try:
                await check_rate_limit(attempt.provider_id)
            except ProxyError as exc:
                last_error = exc
                continue
        try:
            client = UpstreamClient(attempt)
            data = await client.chat(build_chat_payload(payload, attempt, slot=slot))
            _mark_model_used(attempt)
            return JSONResponse(
                content=translate_nonstream_response(
                    data, gateway_model, request_id=rid
                )
            )
        except Exception as exc:
            last_error = exc
            continue

    return _error_response(
        "api_error",
        upstream_error_message(last_error) if last_error else "All providers failed.",
        rid,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_type_for(exc: ProxyError) -> str:
    from .errors import NotFoundError, RateLimitError

    if isinstance(exc, NotFoundError):
        return "not_found_error"
    if isinstance(exc, RateLimitError):
        return "rate_limit_error"
    return "invalid_request_error"


def _error_response(error_type: str, message: str, rid: str) -> JSONResponse:
    status = (
        404
        if error_type == "not_found_error"
        else 429
        if error_type == "rate_limit_error"
        else 400
    )
    return JSONResponse(
        status_code=status,
        content=anthropic_error_payload(error_type, message, request_id=rid),
    )
