"""Cosplay proxy — in-memory sliding-window rate limiter per provider."""

from __future__ import annotations

import asyncio
import time

from config.settings import RuntimeSettingsManager

from .errors import RateLimitError

_locks: dict[str, asyncio.Lock] = {}
_counts: dict[str, list[float]] = {}


def _lock(provider_id: str) -> asyncio.Lock:
    if provider_id not in _locks:
        _locks[provider_id] = asyncio.Lock()
    return _locks[provider_id]


def reset() -> None:
    """Clear rate-limit state (used when settings change / tests)."""
    _counts.clear()
    _locks.clear()


async def check_rate_limit(provider_id: str) -> None:
    """Enforce the configured request rate for one provider."""
    settings = RuntimeSettingsManager().get()
    limit = settings.rate_limit_requests
    window = float(settings.rate_limit_seconds)
    if limit <= 0 or window <= 0:
        return

    lock = _lock(provider_id)
    async with lock:
        now = time.monotonic()
        window_start = now - window
        history = [t for t in _counts.get(provider_id, []) if t >= window_start]
        if len(history) >= limit:
            raise RateLimitError(
                f"Rate limit exceeded for provider {provider_id} "
                f"({limit} requests per {int(window)}s)."
            )
        history.append(now)
        _counts[provider_id] = history
