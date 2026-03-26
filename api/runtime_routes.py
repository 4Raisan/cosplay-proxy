"""Cosplay — REST API routes for runtime settings."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import socket

from config.settings import RuntimeSettingsManager
from providers.runtime_adapter import flush_runtime_cache

router = APIRouter(prefix="/api/runtime")

# Global runtime settings manager instance
_runtime_manager: RuntimeSettingsManager | None = None


def init_runtime(manager: RuntimeSettingsManager) -> None:
    """Set the global runtime settings manager (called by server startup)."""
    global _runtime_manager
    _runtime_manager = manager


def _get_manager() -> RuntimeSettingsManager:
    if _runtime_manager is None:
        raise HTTPException(status_code=500, detail="Runtime manager not initialized")
    return _runtime_manager


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class UpdateRuntimeRequest(BaseModel):
    server_port: int | None = None
    connection_timeout: int | None = None
    rate_limit_requests: int | None = None
    rate_limit_seconds: int | None = None
    skip_title_generation: bool | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def get_runtime_settings():
    """Fetch current runtime settings."""
    manager = _get_manager()
    # Pydantic model_dump will expose the ui fields but not the internal properties
    return manager.get().model_dump()


@router.put("")
async def update_runtime_settings(req: UpdateRuntimeRequest):
    """Update configurable runtime settings."""
    manager = _get_manager()
    current = manager.get()

    # Validation
    if req.server_port is not None:
        if not (1024 <= req.server_port <= 65535):
            raise HTTPException(status_code=400, detail="Port must be between 1024 and 65535.")
        if req.server_port != current.server_port:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', req.server_port)) == 0:
                    raise HTTPException(status_code=400, detail=f"Port {req.server_port} is already in use.")

    if req.connection_timeout is not None and req.connection_timeout <= 0:
        raise HTTPException(status_code=400, detail="Connection timeout must be greater than 0.")
    if req.rate_limit_requests is not None and req.rate_limit_requests <= 0:
        raise HTTPException(status_code=400, detail="Rate limit requests must be greater than 0.")
    if req.rate_limit_seconds is not None and req.rate_limit_seconds <= 0:
        raise HTTPException(status_code=400, detail="Rate limit seconds must be greater than 0.")

    updated = manager.update(
        server_port=req.server_port,
        connection_timeout=req.connection_timeout,
        rate_limit_requests=req.rate_limit_requests,
        rate_limit_seconds=req.rate_limit_seconds,
        skip_title_generation=req.skip_title_generation,
    )
    
    # Flush the FCC cache so the new settings take effect immediately
    flush_runtime_cache()
    
    return updated.model_dump()


@router.post("/regenerate-token")
async def regenerate_api_token():
    """Regenerate the API auth token."""
    manager = _get_manager()
    new_token = manager.regenerate_token()
    return {"api_auth_token": new_token}
