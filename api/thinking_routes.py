"""Cosplay — REST API routes for model thinking capabilities."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.model_caps import ModelCapsManager
from config.thinking import ThinkingManager
from providers.runtime_adapter import flush_runtime_cache, get_provider_runtime

from proxy.effort import (
    ADMIN_RANK,
    VALID_ADMIN_LEVELS,
    _ability_for,
    _heuristic_rank,
)

router = APIRouter(prefix="/api/thinking")

# Global thinking manager instance
_thinking_manager: ThinkingManager | None = None


def init_thinking(manager: ThinkingManager) -> None:
    """Set the global thinking manager (called by server startup)."""
    global _thinking_manager
    _thinking_manager = manager


def _get_manager() -> ThinkingManager:
    if _thinking_manager is None:
        raise HTTPException(status_code=500, detail="Thinking manager not initialized")
    return _thinking_manager


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_ALL_LEVELS = list(ADMIN_RANK.keys())


class UpdateThinkingRequest(BaseModel):
    default_thinking: str | None = None
    primary_coding_thinking: str | None = None
    fast_tasks_thinking: str | None = None
    heavy_analysis_thinking: str | None = None
    research_thinking: str | None = None
    fallback_1_thinking: str | None = None
    fallback_2_thinking: str | None = None
    fallback_3_thinking: str | None = None


class UpdateCapabilitiesRequest(BaseModel):
    provider_id: str = ""
    model_id: str = ""
    max_level: str | None = None
    supports_thinking: bool | None = None
    clear: bool = False


def _validate_level(level: str | None, *, allow_auto: bool = True) -> str | None:
    """Validate a thinking level against the 7-level vocabulary."""
    if level is None:
        return None
    value = (level or "").strip().lower()
    if value not in VALID_ADMIN_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid thinking level: {level!r}. "
                f"Allowed: {', '.join(sorted(VALID_ADMIN_LEVELS))}."
            ),
        )
    if not allow_auto and value == "auto":
        raise HTTPException(status_code=400, detail="Level 'auto' is not allowed here.")
    return value


def _levels_up_to(rank: int | None) -> list[str]:
    """Return all admin levels with a rank <= the given cap (7 levels)."""
    levels: list[str] = []
    for level in _ALL_LEVELS:
        lv = ADMIN_RANK[level]
        if lv is None:
            levels.append(level)
            continue
        if rank is None or lv <= rank:
            levels.append(level)
    return levels


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def get_thinking_settings():
    """Fetch current thinking configuration."""
    manager = _get_manager()
    settings = manager.get()

    return {
        "default_thinking": settings.default_thinking,
        "primary_coding_thinking": settings.primary_coding_thinking,
        "fast_tasks_thinking": settings.fast_tasks_thinking,
        "heavy_analysis_thinking": settings.heavy_analysis_thinking,
        "research_thinking": settings.research_thinking,
        "fallback_1_thinking": settings.fallback_1_thinking,
        "fallback_2_thinking": settings.fallback_2_thinking,
        "fallback_3_thinking": settings.fallback_3_thinking,
    }


@router.put("")
async def update_thinking_settings(req: UpdateThinkingRequest):
    """Update thinking configuration (validates the 7-level vocabulary)."""
    manager = _get_manager()

    updated = manager.update(
        default_thinking=_validate_level(req.default_thinking),
        primary_coding_thinking=_validate_level(req.primary_coding_thinking),
        fast_tasks_thinking=_validate_level(req.fast_tasks_thinking),
        heavy_analysis_thinking=_validate_level(req.heavy_analysis_thinking),
        research_thinking=_validate_level(req.research_thinking),
        fallback_1_thinking=_validate_level(req.fallback_1_thinking),
        fallback_2_thinking=_validate_level(req.fallback_2_thinking),
        fallback_3_thinking=_validate_level(req.fallback_3_thinking),
    )

    flush_runtime_cache()

    return {
        "primary_coding_thinking": updated.primary_coding_thinking,
        "fast_tasks_thinking": updated.fast_tasks_thinking,
        "heavy_analysis_thinking": updated.heavy_analysis_thinking,
        "research_thinking": updated.research_thinking,
    }


@router.get("/capabilities")
async def fetch_capabilities(provider_id: str = Query(...), model_id: str = Query(...)):
    """Fetch the thinking capabilities of a specific model.

    Returns whether the model supports thinking, the model cap (`max_level`),
    the saved caps record when one exists, and the full 7-level vocabulary
    with per-level `supported` / `is_cap` flags so the UI can show above-cap
    levels as disabled (capped) entries.
    """
    try:
        max_rank, explicit_cap, supports = _ability_for(
            _TargetShim(provider_id, model_id)
        )
        if not supports:
            return {
                "supports_thinking": False,
                "max_level": "off",
                "max_rank": 0,
                "supported_levels": ["auto", "off"],
                "levels": _build_level_flags(0, explicit_cap=True),
                "saved": ModelCapsManager().get(provider_id, model_id),
            }
        return {
            "supports_thinking": True,
            "max_level": _rank_to_level(max_rank) if explicit_cap else None,
            "max_rank": max_rank if explicit_cap else None,
            "supported_levels": _levels_up_to(max_rank if explicit_cap else None),
            "levels": _build_level_flags(max_rank, explicit_cap=explicit_cap),
            "saved": ModelCapsManager().get(provider_id, model_id),
        }
    except Exception:
        # Fallback: permissive so thinking configuration stays available.
        return {
            "supports_thinking": True,
            "max_level": None,
            "max_rank": None,
            "supported_levels": _ALL_LEVELS,
            "levels": _build_level_flags(None, explicit_cap=False),
            "saved": ModelCapsManager().get(provider_id, model_id),
        }


def _build_level_flags(max_rank: int | None, *, explicit_cap: bool) -> list[dict]:
    """All 7 levels with supported/is_cap flags. Empty levels have rank None
    (auto) and are always supported. Levels above the cap are supported=False
    when the cap is explicit."""
    flags: list[dict] = []
    for level in _ALL_LEVELS:
        rank = ADMIN_RANK[level]
        if rank is None:
            flags.append({"level": level, "supported": True, "is_cap": False})
            continue
        if not explicit_cap or max_rank is None:
            flags.append({"level": level, "supported": True, "is_cap": False})
            continue
        supported = rank <= max_rank
        flags.append({
            "level": level,
            "supported": supported,
            "is_cap": supported and rank == max_rank,
        })
    return flags


@router.put("/capabilities")
async def update_capabilities(req: UpdateCapabilitiesRequest):
    """Admin override (or clear) a model's persisted reasoning capability."""
    if req.clear:
        cleared = ModelCapsManager().clear(req.provider_id, req.model_id)
        return {"cleared": cleared}

    if not req.provider_id or not req.model_id:
        raise HTTPException(status_code=400, detail="provider_id and model_id are required")

    max_level = _validate_level(req.max_level, allow_auto=False)
    supports = req.supports_thinking
    if supports is False:
        max_rank = 0
    elif max_level is not None:
        max_rank = ADMIN_RANK[max_level]
    else:
        max_rank = _heuristic_rank(req.model_id)

    record = ModelCapsManager().put(
        req.provider_id,
        req.model_id,
        supports_thinking=True if supports is not False else False,
        max_rank=max_rank,
        source="admin",
    )
    return {"saved": record}


def _rank_to_level(rank: int | None) -> str | None:
    """Map a reasoning rank to its admin level name."""
    if rank is None:
        return None
    for level, r in ADMIN_RANK.items():
        if r == rank:
            return level
    return None


class _TargetShim:
    """Minimal object so `_ability_for` can read provider/model from either a
    RouteTarget or a plain (provider_id, model_id) pair."""

    def __init__(self, provider_id: str, model_id: str) -> None:
        self.provider_id = provider_id
        self.model = model_id
