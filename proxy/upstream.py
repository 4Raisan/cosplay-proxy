"""Cosplay proxy — upstream OpenAI-compatible client.

Thin async client over httpx that talks to any ``/chat/completions``
endpoint, including streaming SSE.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from config.settings import RuntimeSettingsManager

from .errors import UpstreamError
from .routing import RouteTarget


class UpstreamClient:
    """Async client bound to one resolved provider target."""

    def __init__(self, target: RouteTarget) -> None:
        self.target = target
        settings = RuntimeSettingsManager().get()
        self._connect_timeout = float(settings.connection_timeout)
        self._read_timeout = float(settings.http_read_timeout)
        self._write_timeout = float(settings.http_write_timeout)

    @property
    def _base_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.target.api_key:
            headers["Authorization"] = f"Bearer {self.target.api_key}"
        if self.target.custom_headers:
            headers.update(self.target.custom_headers)
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                self._read_timeout,
                connect=self._connect_timeout,
                write=self._write_timeout,
            ),
            follow_redirects=True,
        )

    def _chat_url(self) -> str:
        base = (self.target.base_url or "").strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if not base:
            raise UpstreamError("Provider has no base URL configured.")
        return f"{base}/chat/completions"

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a non-streaming chat completions request."""
        body = dict(payload)
        body["stream"] = False
        async with self._client() as client:
            resp = await client.post(
                self._chat_url(), json=body, headers=self._base_headers
            )
        return await self._raise_for_status(resp)

    async def stream_chat(
        self, payload: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat completions; yields parsed SSE JSON chunks."""
        body = dict(payload)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        async with self._client() as client:
            async with client.stream(
                "POST", self._chat_url(), json=body, headers=self._base_headers
            ) as resp:
                if resp.status_code >= 400:
                    await self._raise_for_status_streaming(resp)
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if not data or data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue

    async def list_models(self) -> list[str]:
        """Fetch the provider's model catalog (best effort)."""
        base = (self.target.base_url or "").strip().rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        url = f"{base}/models"
        async with self._client() as client:
            try:
                resp = await client.get(url, headers=self._base_headers)
            except httpx.HTTPError:
                return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return []
        items = data.get("data", []) if isinstance(data, dict) else data
        return [
            str(i.get("id"))
            for i in items
            if isinstance(i, dict) and i.get("id")
        ]

    async def _raise_for_status(self, resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code < 400:
            try:
                return resp.json()
            except json.JSONDecodeError:
                raise UpstreamError(
                    "Upstream returned a non-JSON response.",
                    status=502,
                    provider_message="Non-JSON response body.",
                )
        body = _safe_body(resp)
        raise UpstreamError(
            f"Upstream provider returned HTTP {resp.status_code}.",
            status=502,
            provider_message=body,
        )

    async def _raise_for_status_streaming(self, resp: httpx.Response) -> None:
        body = await resp.aread()
        message = _safe_bytes(body)
        raise UpstreamError(
            f"Upstream provider returned HTTP {resp.status_code}.",
            status=502,
            provider_message=message,
        )


def _safe_body(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "")[:500]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message", ""))[:500]
        if isinstance(error, str):
            return error[:500]
        return (data.get("message") or "")[:500]
    return (resp.text or "")[:500]


def _safe_bytes(body: bytes) -> str:
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return ""
    return text[:500]
