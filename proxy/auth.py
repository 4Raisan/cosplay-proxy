"""Cosplay proxy — bearer token authentication for /v1/* routes."""

from __future__ import annotations

import hmac

from fastapi import Request

from config.settings import RuntimeSettingsManager

from .errors import AuthError


async def require_proxy_auth(request: Request) -> None:
    """Require the configured proxy token as a Bearer or x-api-key credential."""
    settings = RuntimeSettingsManager().get()
    expected = settings.api_auth_token.strip()
    if not expected:
        return

    token = _extract_token(request)
    if token is None or not hmac.compare_digest(token, expected):
        raise AuthError("Invalid or missing proxy authentication token.")


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization:
        parts = authorization.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].casefold() == "bearer":
            return parts[1].strip()
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key.strip()
    return None
