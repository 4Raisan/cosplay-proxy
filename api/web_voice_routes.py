"""Cosplay — REST API routes for Web and Voice settings."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.web_voice import WebVoiceManager
from providers.registry import ProviderRegistry
from providers.runtime_adapter import flush_runtime_cache

router = APIRouter(prefix="/api/web-voice")

# Global managers
_web_voice_manager: WebVoiceManager | None = None
_provider_registry: ProviderRegistry | None = None


def init_web_voice(manager: WebVoiceManager, registry: ProviderRegistry) -> None:
    """Set the global managers (called by server startup)."""
    global _web_voice_manager
    global _provider_registry
    _web_voice_manager = manager
    _provider_registry = registry


def _get_manager() -> WebVoiceManager:
    if _web_voice_manager is None:
        raise HTTPException(status_code=500, detail="WebVoice manager not initialized")
    return _web_voice_manager


def _get_registry() -> ProviderRegistry:
    if _provider_registry is None:
        raise HTTPException(status_code=500, detail="Provider registry not initialized")
    return _provider_registry


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class UpdateWebVoiceRequest(BaseModel):
    enable_web_search: bool | None = None
    allow_private_network: bool | None = None
    enable_voice: bool | None = None
    voice_model: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def get_web_voice_settings():
    """Fetch current web and voice configuration."""
    manager = _get_manager()
    settings = manager.get()
    
    return {
        "enable_web_search": settings.enable_web_search,
        "allow_private_network": settings.allow_private_network,
        "enable_voice": settings.enable_voice,
        "voice_model": settings.voice_model,
    }


@router.put("")
async def update_web_voice_settings(req: UpdateWebVoiceRequest):
    """Update web and voice configuration."""
    manager = _get_manager()
    
    updated = manager.update(
        enable_web_search=req.enable_web_search,
        allow_private_network=req.allow_private_network,
        enable_voice=req.enable_voice,
        voice_model=req.voice_model,
    )
    
    flush_runtime_cache()
    
    return {
        "enable_web_search": updated.enable_web_search,
        "allow_private_network": updated.allow_private_network,
        "enable_voice": updated.enable_voice,
        "voice_model": updated.voice_model,
    }


@router.get("/nvidia-status")
async def check_nvidia_provider():
    """Check if an NVIDIA NIM provider exists in the registry."""
    reg = _get_registry()
    providers = reg.list_providers()
    
    for p in providers:
        if "nvidia" in p.name.lower() or "nim" in p.name.lower():
            # Return masked API key
            key_len = len(p.api_key)
            masked_key = "*" * 14 if key_len > 0 else ""
            
            return {
                "configured": True,
                "provider_id": p.id,
                "status": p.connection_status,
                "api_key": masked_key
            }
            
    return {"configured": False}
