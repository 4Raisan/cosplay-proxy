from __future__ import annotations

import os
import platform
import sys
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.auth import verify_api_token
from config.settings import RuntimeSettingsManager
from daemon import get_daemon_status
from providers.registry import ProviderRegistry

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

# Record boot time
_BOOT_TIME = time.time()

@router.get("", dependencies=[Depends(verify_api_token)])
async def get_diagnostics() -> Dict[str, Any]:
    """Retrieve system diagnostics, memory usage, and runtime status."""
    runtime_manager = RuntimeSettingsManager()
    runtime = runtime_manager.get()
    
    # Safe dump of runtime (no tokens)
    safe_runtime = runtime.model_dump()
    if "api_auth_token" in safe_runtime:
        safe_runtime["api_auth_token"] = "***"
        
    registry = ProviderRegistry()
    providers = []
    for p in registry.list_providers():
        safe_p = p.model_dump()
        if "api_key" in safe_p and safe_p["api_key"]:
            safe_p["api_key"] = "***"
        providers.append(safe_p)

    uptime_seconds = time.time() - _BOOT_TIME

    # Basic memory stats (cross-platform compatible without psutil)
    # Using sys.getsizeof for a rough estimate of objects, but real mem is better.
    # We will just report standard python sys info since psutil isn't in requirements.txt.

    return {
        "status": "ok",
        "version": "1.0.1",
        "uptime_seconds": round(uptime_seconds, 2),
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "python_version": sys.version,
        },
        "daemon": {
            "status": get_daemon_status(),
        },
        "runtime_config": safe_runtime,
        "providers_loaded": len(providers),
        "providers": providers,
    }
