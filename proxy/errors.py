"""Cosplay proxy — error types and wire-protocol error payloads."""

from __future__ import annotations

import json
from typing import Any

import httpx


class ProxyError(Exception):
    """Base error for the Cosplay proxy engine."""


class InvalidRequest(ProxyError):
    """Malformed or missing request fields (maps to HTTP 400)."""


class AuthError(ProxyError):
    """Missing/invalid proxy token (maps to HTTP 401)."""


class NotFoundError(ProxyError):
    """Unknown model or endpoint (maps to HTTP 404)."""


class RateLimitError(ProxyError):
    """Too many requests (maps to HTTP 429)."""


class UpstreamError(ProxyError):
    """Upstream provider returned an error status."""

    def __init__(
        self,
        message: str,
        *,
        status: int = 500,
        provider_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.provider_message = provider_message


def anthropic_error_payload(
    error_type: str, message: str, *, request_id: str | None = None
) -> dict[str, Any]:
    """Serialize an error in the Anthropic error envelope."""
    error: dict[str, Any] = {"type": error_type, "message": message}
    if request_id:
        error["request_id"] = request_id
    return {"type": "error", "error": error}


def openai_error_payload(message: str, *, error_type: str = "api_error") -> dict[str, Any]:
    """Serialize an error in the OpenAI Responses error envelope."""
    return {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message,
        },
    }


def http_status(exc: ProxyError) -> int:
    """Map a proxy error to an HTTP status code."""
    if isinstance(exc, InvalidRequest):
        return 400
    if isinstance(exc, AuthError):
        return 401
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, RateLimitError):
        return 429
    if isinstance(exc, UpstreamError):
        return exc.status
    return 500


def upstream_error_message(exc: Exception) -> str:
    """Build a safe, short message for an upstream failure."""
    if isinstance(exc, UpstreamError):
        return exc.provider_message or str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return "Upstream provider timed out."
    if isinstance(exc, httpx.HTTPError):
        return f"Upstream connection error: {type(exc).__name__}."
    if isinstance(exc, json.JSONDecodeError):
        return "Upstream returned malformed JSON."
    return str(exc) or type(exc).__name__
