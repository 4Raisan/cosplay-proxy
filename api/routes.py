"""Cosplay — REST API routes for provider management.

All endpoints are local-only (loopback check on admin routes).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from providers.accounts import get_account_providers
from providers.discovery import discover_models
from providers.models import (
    AddProviderRequest,
    ApiType,
    ConnectionStatus,
    ModelStatus,
    ProviderRecord,
    UpdateProviderRequest,
    ValidateRequest,
)
from providers.registry import ProviderRegistry
from providers.validator import ValidationResult, check_model_working, validate_connection
from providers.runtime_adapter import flush_runtime_cache

router = APIRouter(prefix="/api")

# Global registry instance — initialized by the server
_registry: ProviderRegistry | None = None

# Track background "check working" tasks
_check_tasks: dict[str, bool] = {}  # provider_id -> is_running


def init_registry(registry: ProviderRegistry) -> None:
    """Set the global registry instance (called by server startup)."""
    global _registry
    _registry = registry


def _get_registry() -> ProviderRegistry:
    if _registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")
    return _registry


# ---------------------------------------------------------------------------
# Dev / Prototype Reset
# ---------------------------------------------------------------------------

@router.post("/reset-data")
async def reset_user_data():
    """Clear all user configuration files in ~/.cosplay/ and reset runtime state."""
    import shutil
    from pathlib import Path
    from config.settings import RuntimeSettingsManager
    from config.routing import RoutingManager
    from config.thinking import ThinkingManager
    from config.web_voice import WebVoiceManager
    from config.remote import RemoteManager
    from api.runtime_routes import init_runtime
    from api.routing_routes import init_routing
    from api.thinking_routes import init_thinking
    from api.web_voice_routes import init_web_voice
    from api.remote_routes import init_remote

    cosplay_dir = Path.home() / ".cosplay"
    if cosplay_dir.exists():
        for item in cosplay_dir.glob("*"):
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass

    # Reset singletons & FCC runtime cache
    ProviderRegistry._instance = None
    RuntimeSettingsManager._instance = None
    RoutingManager._instance = None
    ThinkingManager._instance = None
    WebVoiceManager._instance = None
    RemoteManager._instance = None
    flush_runtime_cache()

    # Re-initialize singletons and route managers
    reg = ProviderRegistry()
    init_registry(reg)

    rs_mgr = RuntimeSettingsManager()
    init_runtime(rs_mgr)

    rt_mgr = RoutingManager()
    init_routing(rt_mgr, reg)

    th_mgr = ThinkingManager()
    init_thinking(th_mgr)

    wv_mgr = WebVoiceManager()
    init_web_voice(wv_mgr, reg)

    rm_mgr = RemoteManager()
    init_remote(rm_mgr)

    _sync_claude_settings()

    return {"success": True, "message": "All user data cleared."}


def _sync_claude_settings() -> None:
    """Keep ~/.claude/settings.json env in sync with the gateway after the
    auth token is regenerated (e.g. Reset), so Claude Code can still reach
    /v1/models and discover the gateway model list."""
    import json
    from pathlib import Path
    from config.settings import RuntimeSettingsManager

    settings_file = Path.home() / ".claude" / "settings.json"
    try:
        rs = RuntimeSettingsManager().get()
        token = rs.api_auth_token.strip()
        if not token:
            return
        data = {}
        if settings_file.exists():
            try:
                data = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data.setdefault("env", {})
        env = data["env"]
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{rs.server_port}"
        env["ANTHROPIC_AUTH_TOKEN"] = token
        env.setdefault("ANTHROPIC_MODEL", "claude-cosplay-default")
        env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        try:
            from proxy.gateway_cache import sync_gateway_cache

            sync_gateway_cache()
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------

@router.get("/providers")
async def list_providers():
    """List all saved providers with model count summaries."""
    reg = _get_registry()
    return reg.all_summaries()


@router.post("/providers")
async def add_provider(req: AddProviderRequest, background_tasks: BackgroundTasks):
    """Validate, save a new provider, and discover models."""
    reg = _get_registry()

    # Validate connection first
    result = await validate_connection(
        api_type=req.api_type,
        base_url=req.base_url,
        api_key=req.api_key,
        custom_headers=req.custom_headers,
    )

    # Create provider record
    provider = ProviderRecord(
        name=req.name,
        api_type=req.api_type,
        base_url=req.base_url,
        api_key=req.api_key,
        custom_headers=req.custom_headers,
        connection_status=(
            ConnectionStatus.CONNECTED
            if result.success
            else ConnectionStatus.ERROR
        ),
    )
    reg.add_provider(provider)
    flush_runtime_cache()

    # Discover models in the background if connection succeeded
    if result.success:
        background_tasks.add_task(_discover_models_task, provider.id)

    summary = reg.provider_summary(provider.id)
    return {
        "provider": summary,
        "validation": {
            "success": result.success,
            "message": result.message,
            "details": result.details,
        },
    }


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, req: UpdateProviderRequest):
    """Update an existing provider's configuration."""
    reg = _get_registry()
    updated = reg.update_provider(
        provider_id,
        name=req.name,
        base_url=req.base_url,
        api_key=req.api_key,
        custom_headers=req.custom_headers,
        enabled=req.enabled,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    flush_runtime_cache()
    return reg.provider_summary(provider_id)


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """Remove a provider and its cached models."""
    reg = _get_registry()
    if not reg.remove_provider(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    flush_runtime_cache()
    return {"success": True}


# ---------------------------------------------------------------------------
# Validation (without saving)
# ---------------------------------------------------------------------------

@router.post("/providers/validate")
async def validate_provider(req: ValidateRequest):
    """Test connection to a provider without saving it."""
    result = await validate_connection(
        api_type=req.api_type,
        base_url=req.base_url,
        api_key=req.api_key,
        custom_headers=req.custom_headers,
    )
    return {
        "success": result.success,
        "message": result.message,
        "details": result.details,
    }


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

@router.post("/providers/{provider_id}/refresh-models")
async def refresh_models(provider_id: str):
    """Re-run model discovery for a provider."""
    reg = _get_registry()
    provider = reg.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    flush_runtime_cache()
    try:
        models = await discover_models(
            api_type=provider.api_type,
            base_url=provider.base_url,
            api_key=provider.api_key,
            custom_headers=provider.custom_headers,
            provider_id=provider.id,
        )
        reg.set_models(provider.id, models)
        provider.connection_status = ConnectionStatus.CONNECTED
        reg.save()
        return {
            "success": True,
            "model_count": len(models),
            "models": [m.model_dump() for m in models],
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Discovery failed: {e}",
            "model_count": 0
        }


@router.get("/providers/{provider_id}/models")
async def get_models(provider_id: str):
    """Get cached model list with working status."""
    reg = _get_registry()
    provider = reg.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    models = reg.get_models(provider_id)
    is_checking = _check_tasks.get(provider_id, False)
    return {
        "models": [m.model_dump() for m in models],
        "checking": is_checking,
    }


# ---------------------------------------------------------------------------
# Check working models (background task)
# ---------------------------------------------------------------------------

@router.post("/providers/{provider_id}/check-working")
async def check_working_models(
    provider_id: str, background_tasks: BackgroundTasks
):
    """Start background check of all models for a provider."""
    reg = _get_registry()
    provider = reg.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    if _check_tasks.get(provider_id, False):
        return {"message": "Check already in progress", "checking": True}

    background_tasks.add_task(_check_working_task, provider_id)
    return {"message": "Check started", "checking": True}


# ---------------------------------------------------------------------------
# Account providers
# ---------------------------------------------------------------------------

@router.get("/account-providers")
async def list_account_providers():
    """List all available account-based providers."""
    return [p.model_dump() for p in get_account_providers()]


@router.post("/account-providers/{provider_id}/login")
async def account_login(provider_id: str):
    from providers.connected_accounts import start_openai_login
    if provider_id == "openai_chatgpt":
        return await start_openai_login()
    raise HTTPException(400, "Unknown provider")


@router.get("/account-providers/{provider_id}/status")
async def account_status(provider_id: str):
    from providers.connected_accounts import get_openai_status
    if provider_id == "openai_chatgpt":
        return get_openai_status()
    raise HTTPException(400, "Unknown provider")


@router.post("/account-providers/{provider_id}/cancel")
async def account_cancel(provider_id: str):
    from providers.connected_accounts import cancel_openai_login
    if provider_id == "openai_chatgpt":
        return await cancel_openai_login()
    raise HTTPException(400, "Unknown provider")


@router.delete("/account-providers/{provider_id}")
async def account_disconnect(provider_id: str):
    from providers.connected_accounts import disconnect_openai
    if provider_id == "openai_chatgpt":
        return await disconnect_openai()
    raise HTTPException(400, "Unknown provider")


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _discover_models_task(provider_id: str) -> None:
    """Background task: discover models for a newly added provider."""
    reg = _get_registry()
    provider = reg.get_provider(provider_id)
    if provider is None:
        return
    try:
        models = await discover_models(
            api_type=provider.api_type,
            base_url=provider.base_url,
            api_key=provider.api_key,
            custom_headers=provider.custom_headers,
            provider_id=provider.id,
        )
        reg.set_models(provider.id, models)
    except Exception as e:
        print(f"Background discovery failed: {type(e).__name__}")


async def _check_working_task(provider_id: str) -> None:
    """Background task: test models for a provider concurrently in parallel."""
    reg = _get_registry()
    provider = reg.get_provider(provider_id)
    if provider is None:
        return

    _check_tasks[provider_id] = True
    try:
        models = reg.get_models(provider_id)
        semaphore = asyncio.Semaphore(10)  # Check up to 10 models concurrently

        async def _check_single(model):
            async with semaphore:
                reg.set_model_status(provider_id, model.model_id, ModelStatus.CHECKING, save=False)
                result = await check_model_working(
                    api_type=provider.api_type,
                    base_url=provider.base_url,
                    model_id=model.model_id,
                    api_key=provider.api_key,
                    custom_headers=provider.custom_headers,
                )
                status = ModelStatus.WORKING if result.success else ModelStatus.FAILED
                error_msg = None if result.success else result.details or result.message
                reg.set_model_status(
                    provider_id, model.model_id, status, error_message=error_msg, save=False
                )
                if result.success:
                    # Learn the model's reasoning capability from the same check
                    # that proved it works (no extra network call).
                    try:
                        from proxy.effort import record_cap_from_check

                        record_cap_from_check(
                            provider_id, model.model_id, model.supports_thinking
                        )
                    except Exception:
                        pass

        await asyncio.gather(*[_check_single(m) for m in models], return_exceptions=True)
        reg.save()
    finally:
        _check_tasks[provider_id] = False
