"""Cosplay proxy — Claude Code gateway model discovery cache sync.

Claude Code fetches ``GET /v1/models`` once per startup and caches the result in
``gateway-models.json`` under its config dir; the ``/model`` picker reads that
cache. ``sync_gateway_cache()`` writes the exact schema the picker reads so a
routing change made in the Admin UI shows up in the terminal picker immediately
— no ``claude`` restart needed.

Best-effort and non-destructive: an existing cache is never blanked when the
model list is empty, and any failure is swallowed by callers.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.routing import RoutingManager

# Gateway ids advertised by GET /v1/models (kept in sync with models_api.py).
_GATEWAY_MODELS: list[tuple[str, str, str]] = [
    ("claude-cosplay-default", "default", "Default"),
    ("claude-cosplay-coding", "primary_coding", "Coding"),
    ("claude-cosplay-fast", "fast_tasks", "Fast"),
    ("claude-cosplay-reasoning", "heavy_analysis", "Reasoning"),
    ("claude-cosplay-research", "research", "Heavy Research"),
]

_SLOT_ATTRS = {
    "default": "effective_default_model",
    "primary_coding": "primary_coding_model",
    "fast_tasks": "effective_fast_tasks_model",
    "heavy_analysis": "effective_heavy_analysis_model",
    "research": "effective_research_model",
}


def _short_model(ref: str | None) -> str:
    if not ref:
        return ""
    return ref.split(":")[-1].split("/")[-1]


def _cache_path() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or str(
        Path.home() / ".claude"
    )
    return Path(config_dir) / "cache" / "gateway-models.json"


def build_cache_entries() -> list[dict[str, str]]:
    """Build the picker entries from the current routing slots.

    Only ids starting with ``claude``/``anthropic`` are included — that is the
    filter Claude Code applies to the discovery result.
    """
    routing = RoutingManager().get()
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for gateway_id, slot, label in _GATEWAY_MODELS:
        ref = getattr(routing, _SLOT_ATTRS[slot])
        short = _short_model(ref)
        display = f"{label} ({short})" if short else label
        if not gateway_id.lower().startswith(("claude", "anthropic")):
            continue
        entries.append({"id": gateway_id, "display_name": display})
        seen.add(gateway_id)
    return entries


def sync_gateway_cache() -> Path | None:
    """Write Claude Code's gateway discovery cache from the current routing.

    Returns the cache path on success, or None when there was nothing to write
    or the write failed. Never overwrites an existing cache with an empty list.
    """
    entries = build_cache_entries()
    if not entries:
        return None

    cache_file = _cache_path()
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "baseUrl": "http://127.0.0.1:8082",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "models": entries,
    }

    fd, tmp_path = tempfile.mkstemp(
        dir=str(cache_file.parent), suffix=".tmp", prefix="gateway-models_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if cache_file.exists():
            cache_file.unlink()
        os.rename(tmp_path, str(cache_file))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return cache_file
