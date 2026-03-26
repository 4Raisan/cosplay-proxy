"""Cosplay — REST API routes for model routing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.routing import RoutingManager
from providers.registry import ProviderRegistry
from providers.runtime_adapter import flush_runtime_cache

router = APIRouter(prefix="/api/routing")

# Global instances
_routing_manager: RoutingManager | None = None
_provider_registry: ProviderRegistry | None = None

def init_routing(manager: RoutingManager, registry: ProviderRegistry) -> None:
    """Set the global routing manager (called by server startup)."""
    global _routing_manager, _provider_registry
    _routing_manager = manager
    _provider_registry = registry

def _get_manager() -> RoutingManager:
    if _routing_manager is None:
        raise HTTPException(status_code=500, detail="Routing manager not initialized")
    return _routing_manager

def _get_registry() -> ProviderRegistry:
    if _provider_registry is None:
        raise HTTPException(status_code=500, detail="Provider registry not initialized")
    return _provider_registry


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class UpdateRoutingRequest(BaseModel):
    default_model: str | None = None
    primary_coding_model: str | None = None
    fast_tasks_model: str | None = None
    heavy_analysis_model: str | None = None
    research_model: str | None = None
    fallback_1: str | None = None
    fallback_2: str | None = None
    fallback_3: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def get_routing_settings():
    """Fetch current routing configuration and effective fallbacks."""
    manager = _get_manager()
    settings = manager.get()
    
    # Return both raw and effective values so the frontend can display fallbacks
    return {
        "default_model": settings.default_model,
        "primary_coding_model": settings.primary_coding_model,
        "fast_tasks_model": settings.fast_tasks_model,
        "heavy_analysis_model": settings.heavy_analysis_model,
        "research_model": settings.research_model,
        "fallback_1": settings.fallback_1,
        "fallback_2": settings.fallback_2,
        "fallback_3": settings.fallback_3,
        # Effective fallbacks
        "effective_default_model": settings.effective_default_model,
        "effective_fast_tasks_model": settings.effective_fast_tasks_model,
        "effective_heavy_analysis_model": settings.effective_heavy_analysis_model,
        "effective_research_model": settings.effective_research_model,
    }


@router.put("")
async def update_routing_settings(req: UpdateRoutingRequest):
    """Update routing configuration."""
    manager = _get_manager()
    registry = _get_registry()
    
    def _validate_provider(model_str: str | None) -> None:
        if not model_str:
            return
        if ":" in model_str:
            provider_id = model_str.split(":", 1)[0]
        elif "/" in model_str:
            provider_id = model_str.split("/", 1)[0]
        else:
            raise HTTPException(status_code=400, detail=f"Invalid model format: {model_str}.")

        if not registry.get_provider(provider_id):
            raise HTTPException(status_code=400, detail=f"Provider {provider_id} does not exist.")

    # Validate all incoming models
    _validate_provider(req.default_model)
    _validate_provider(req.primary_coding_model)
    _validate_provider(req.fast_tasks_model)
    _validate_provider(req.heavy_analysis_model)
    _validate_provider(req.research_model)
    _validate_provider(req.fallback_1)
    _validate_provider(req.fallback_2)
    _validate_provider(req.fallback_3)

    # Empty strings from UI should be treated as None
    updated = manager.update(
        default_model=req.default_model if req.default_model else None,
        primary_coding_model=req.primary_coding_model if req.primary_coding_model else None,
        fast_tasks_model=req.fast_tasks_model if req.fast_tasks_model else None,
        heavy_analysis_model=req.heavy_analysis_model if req.heavy_analysis_model else None,
        research_model=req.research_model if req.research_model else None,
        fallback_1=req.fallback_1 if req.fallback_1 else None,
        fallback_2=req.fallback_2 if req.fallback_2 else None,
        fallback_3=req.fallback_3 if req.fallback_3 else None,
    )
    
    # Flush the FCC ProviderRuntime cache so new routes instantly take effect
    flush_runtime_cache()

    # Re-sync Claude Code's gateway discovery cache so the /model picker shows
    # the change immediately (no claude restart needed).
    try:
        from proxy.gateway_cache import sync_gateway_cache

        sync_gateway_cache()
    except Exception:
        pass

    return {
        "default_model": updated.default_model,
        "primary_coding_model": updated.primary_coding_model,
        "fast_tasks_model": updated.fast_tasks_model,
        "heavy_analysis_model": updated.heavy_analysis_model,
        "research_model": updated.research_model,
        "fallback_1": updated.fallback_1,
        "fallback_2": updated.fallback_2,
        "fallback_3": updated.fallback_3,
        "effective_default_model": updated.effective_default_model,
        "effective_fast_tasks_model": updated.effective_fast_tasks_model,
        "effective_heavy_analysis_model": updated.effective_heavy_analysis_model,
        "effective_research_model": updated.effective_research_model,
    }
