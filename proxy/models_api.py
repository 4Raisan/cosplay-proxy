"""Cosplay proxy — OpenAI-compatible model listing endpoint.

Advertises the Cosplay routing slots under ``claude-cosplay-*`` ids so Claude
Code's gateway model discovery (which drops every entry whose id does not
contain ``claude``/``anthropic``) keeps them in the ``/model`` picker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from config.routing import RoutingManager

from .auth import require_proxy_auth

router = APIRouter()

# (gateway id, routing slot, label)
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


def build_models_list() -> dict:
    routing = RoutingManager().get()
    data = []
    seen: set[str] = set()

    for gateway_id, slot, label in _GATEWAY_MODELS:
        attr = _SLOT_ATTRS[slot]
        ref = getattr(routing, attr)
        short = _short_model(ref)
        # Display name is dynamic: it re-reads the routing slot on every call,
        # so an Admin UI model change is reflected in the picker on next launch.
        display = f"{label} ({short})" if short else label
        data.append(
            {
                "object": "model",
                "created": 0,
                "owned_by": "cosplay",
                "created_at": "1970-01-01T00:00:00Z",
                "display_name": display,
                "id": gateway_id,
                "type": "model",
            }
        )
        if ref:
            seen.add(ref)

    # Also expose the raw configured model refs so they can be picked directly
    # by OpenAI-compatible clients (Claude Code filters these out).
    for ref in sorted(seen):
        model_id = ref.split(":", 1)[-1]
        data.append(
            {
                "object": "model",
                "created": 0,
                "owned_by": "cosplay",
                "created_at": "1970-01-01T00:00:00Z",
                "display_name": _short_model(ref),
                "id": model_id,
                "type": "model",
            }
        )

    ids = [m["id"] for m in data]
    return {
        "object": "list",
        "data": data,
        "first_id": ids[0] if ids else None,
        "has_more": False,
        "last_id": ids[-1] if ids else None,
    }


@router.get("/v1/models")
async def list_models(_auth: None = Depends(require_proxy_auth)) -> dict:
    return build_models_list()
