"""Cosplay — FastAPI server entry point.

Mounts API routes and serves static admin UI files.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from api.routes import init_registry, router as api_router
from api.runtime_routes import init_runtime, router as runtime_router
from api.routing_routes import init_routing, router as routing_router
from api.thinking_routes import init_thinking, router as thinking_router
from api.web_voice_routes import init_web_voice, router as web_voice_router
from api.remote_routes import init_remote, router as remote_router
from api.diagnostics_routes import router as diagnostics_router
from providers.registry import ProviderRegistry
from config.settings import RuntimeSettingsManager
from config.routing import RoutingManager
from config.thinking import ThinkingManager
from config.web_voice import WebVoiceManager
from config.remote import RemoteManager
from daemon import start_daemon, stop_daemon

from proxy.auth import require_proxy_auth as _require_proxy_auth
from proxy.errors import (
    AuthError,
    InvalidRequest,
    NotFoundError,
    ProxyError,
    RateLimitError,
    UpstreamError,
    anthropic_error_payload,
    http_status,
    openai_error_payload,
)
from proxy.gateway_cache import sync_gateway_cache
from proxy.messages import router as proxy_messages_router
from proxy.models_api import router as proxy_models_router
from proxy.responses import router as proxy_responses_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _proxy_error_type(exc: ProxyError) -> str:
    """Map a ProxyError subclass to its wire-protocol error type."""
    if isinstance(exc, AuthError):
        return "authentication_error"
    if isinstance(exc, InvalidRequest):
        return "invalid_request_error"
    if isinstance(exc, NotFoundError):
        return "not_found_error"
    if isinstance(exc, RateLimitError):
        return "rate_limit_error"
    return "api_error"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load provider registry, runtime, routing, thinking, web_voice, and remote settings on startup."""
    registry = ProviderRegistry()
    registry.load()
    init_registry(registry)
    
    runtime_manager = RuntimeSettingsManager()
    init_runtime(runtime_manager)

    routing_manager = RoutingManager()
    init_routing(routing_manager, registry)
    
    thinking_manager = ThinkingManager()
    init_thinking(thinking_manager)
    
    web_voice_manager = WebVoiceManager()
    init_web_voice(web_voice_manager, registry)
    
    remote_manager = RemoteManager()
    init_remote(remote_manager)

    # Seed Claude Code's gateway model discovery cache on first launch so the
    # /model picker shows the Cosplay slots immediately (best-effort).
    try:
        sync_gateway_cache()
    except Exception:
        pass

    # Start Telegram daemon if enabled (config-driven, disabled by default)
    start_daemon()
    
    yield
    
    # Stop Telegram daemon on shutdown
    stop_daemon()


app = FastAPI(
    title="Cosplay",
    description="AI Provider Management Proxy",
    version="1.0.1",
    lifespan=lifespan,
)


@app.exception_handler(ProxyError)
async def proxy_error_handler(request: Request, exc: ProxyError) -> JSONResponse:
    """App-level handler: proxy errors that escape the route handlers (e.g.
    raised by the require_proxy_auth dependency) keep their correct HTTP
    status and wire-protocol body instead of surfacing as a bare 500."""
    status = http_status(exc)
    message = str(exc) or type(exc).__name__
    etype = _proxy_error_type(exc)
    if request.url.path.startswith("/v1/messages"):
        return JSONResponse(
            status_code=status,
            content=anthropic_error_payload(etype, message),
        )
    return JSONResponse(
        status_code=status,
        content=openai_error_payload(message, error_type=etype),
    )

# Mount API routes
app.include_router(api_router)
app.include_router(runtime_router)
app.include_router(routing_router)
app.include_router(thinking_router)
app.include_router(web_voice_router)
app.include_router(remote_router)
app.include_router(diagnostics_router)

# Native Claude Code / OpenAI compatible proxy endpoints
app.include_router(proxy_messages_router)
app.include_router(proxy_models_router)
app.include_router(proxy_responses_router)


# Serve the admin UI
@app.get("/", include_in_schema=False)
async def admin_page():
    return FileResponse(STATIC_DIR / "index.html")


# Serve static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
