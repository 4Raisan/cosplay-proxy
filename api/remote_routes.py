"""Cosplay — REST API routes for Remote Access (Telegram & FS)."""

from __future__ import annotations

import os
from pathlib import Path
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.remote import RemoteManager
from config.web_voice import WebVoiceManager
from daemon import restart_daemon, get_daemon_status
from providers.runtime_adapter import flush_runtime_cache


router = APIRouter(prefix="/api/remote")

# Global manager instance
_remote_manager: RemoteManager | None = None


def init_remote(manager: RemoteManager) -> None:
    """Set the global remote manager (called by server startup)."""
    global _remote_manager
    _remote_manager = manager


def _get_manager() -> RemoteManager:
    if _remote_manager is None:
        raise HTTPException(status_code=500, detail="Remote manager not initialized")
    return _remote_manager


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class UpdateRemoteRequest(BaseModel):
    enable_telegram: bool | None = None
    telegram_token: str | None = None
    telegram_paired_user_id: int | None = None
    telegram_paired_username: str | None = None
    workspace_folder: str | None = None
    allow_voice: bool | None = None



class PairRequest(BaseModel):
    telegram_token: str


# ---------------------------------------------------------------------------
# Config Routes
# ---------------------------------------------------------------------------

@router.get("")
async def get_remote_settings():
    """Fetch current remote configuration."""
    manager = _get_manager()
    settings = manager.get()
    
    token_len = len(settings.telegram_token) if settings.telegram_token else 0
    masked_token = "*" * 16 if token_len > 0 else ""
    
    return {
        "enable_telegram": settings.enable_telegram,
        "telegram_token_masked": masked_token,
        "has_token": bool(settings.telegram_token),
        "telegram_paired_user_id": settings.telegram_paired_user_id,
        "telegram_paired_username": settings.telegram_paired_username,
        "workspace_folder": settings.workspace_folder,
        "allow_voice": settings.allow_voice,
    }


@router.put("")
async def update_remote_settings(req: UpdateRemoteRequest):
    """Update remote configuration."""
    manager = _get_manager()
    
    # Workspace Validation
    if req.workspace_folder is not None:
        path = req.workspace_folder
        if path:
            if not os.path.exists(path):
                raise HTTPException(status_code=400, detail="Workspace folder does not exist.")
            if not os.path.isdir(path):
                raise HTTPException(status_code=400, detail="Workspace path is not a directory.")
            if not os.access(path, os.R_OK):
                raise HTTPException(status_code=400, detail="Workspace folder is not readable.")
            if not os.access(path, os.W_OK):
                raise HTTPException(status_code=400, detail="Workspace folder is not writable.")
    
    requires_restart = any([
        req.enable_telegram is not None,
        req.telegram_token is not None,
        req.telegram_paired_user_id is not None,
        req.telegram_paired_username is not None,
        req.workspace_folder is not None,
    ])

    updated = manager.update(
        enable_telegram=req.enable_telegram,
        telegram_token=req.telegram_token,
        telegram_paired_user_id=req.telegram_paired_user_id,
        telegram_paired_username=req.telegram_paired_username,
        workspace_folder=req.workspace_folder,
        allow_voice=req.allow_voice,
    )
    
    # Apply changes to FCC
    flush_runtime_cache()
    if requires_restart:
        restart_daemon()
    
    return {"success": True}


@router.get("/status")
async def fetch_daemon_status():
    """Get the live status of the daemon."""
    return {"status": get_daemon_status()}


# ---------------------------------------------------------------------------
# Telegram Logic
# ---------------------------------------------------------------------------

@router.post("/telegram/pair")
async def pair_telegram(req: PairRequest):
    """Long-polls Telegram for a /pair message for up to 5 minutes."""
    token = req.telegram_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Bot token is required for pairing.")
        
    manager = _get_manager()
    
    # Delete webhook to prevent conflicts with getUpdates
    delete_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    async with httpx.AsyncClient() as client:
        try:
            await client.get(delete_url)
        except Exception:
            pass
            
    # Poll for up to 5 minutes (300 seconds), in chunks of 15 seconds
    poll_url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    for _ in range(20):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(poll_url, params={"timeout": 15, "limit": 1})
                if res.status_code == 401:
                    raise HTTPException(status_code=401, detail="Invalid Bot Token.")
                if res.status_code != 200:
                    continue
                    
                data = res.json()
                if not data.get("ok"):
                    continue
                    
                for update in data.get("result", []):
                    message = update.get("message")
                    if not message:
                        continue
                    text = message.get("text", "").strip()
                    if text.startswith("/pair"):
                        user = message.get("from", {})
                        user_id = user.get("id")
                        username = user.get("username", user.get("first_name", "Unknown"))
                        
                        if user_id:
                            manager.update(
                                telegram_paired_user_id=user_id,
                                telegram_paired_username=username,
                                telegram_token=token
                            )
                            
                            send_url = f"https://api.telegram.org/bot{token}/sendMessage"
                            try:
                                await client.post(send_url, json={
                                    "chat_id": user_id,
                                    "text": "✓ Successfully paired with Cosplay! You can now send me coding tasks."
                                })
                            except Exception:
                                pass
                                
                            # Notify FCC runtime of the new pairing
                            flush_runtime_cache()
                            restart_daemon()
                            
                            return {
                                "success": True,
                                "user_id": user_id,
                                "username": username
                            }
        except httpx.TimeoutException:
            continue
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal server error during pairing.")
            
    return {"success": False, "timeout": True, "message": "Pairing timed out after 5 minutes."}


@router.post("/telegram/test")
async def test_telegram_connection():
    """Test every component of the connection."""
    manager = _get_manager()
    settings = manager.get()
    
    checks = []
    
    # 1. Bot Token
    has_token = bool(settings.telegram_token)
    checks.append({"name": "Bot Token Configured", "passed": has_token})
    
    # 2. Telegram API Reachable
    api_reachable = False
    if has_token:
        url = f"https://api.telegram.org/bot{settings.telegram_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code == 200 and res.json().get("ok"):
                    api_reachable = True
        except Exception:
            pass
    checks.append({"name": "Telegram API Access", "passed": api_reachable})
    
    # 3. Daemon Running
    status = get_daemon_status()
    checks.append({
        "name": f"Daemon Status: {status}", 
        "passed": status == "Running"
    })
    
    # 4. Workspace Validation
    ws = settings.workspace_folder
    ws_valid = bool(ws and os.path.isdir(ws) and os.access(ws, os.R_OK) and os.access(ws, os.W_OK))
    checks.append({"name": "Workspace Validation", "passed": ws_valid})
    
    # 5. Paired User
    paired = bool(settings.telegram_paired_user_id)
    checks.append({"name": "User Paired", "passed": paired})
    
    # 6. Voice Integration
    if settings.allow_voice:
        web_voice_mgr = WebVoiceManager()
        wv = web_voice_mgr.get()
        voice_passed = bool(wv.enable_voice)
        checks.append({"name": "NVIDIA Voice Ready", "passed": voice_passed})
    else:
        checks.append({"name": "Voice Ignored (Disabled)", "passed": True})

    all_passed = all(c["passed"] for c in checks)
    
    return {
        "status": "Ready" if all_passed else "Incomplete",
        "checks": checks,
        "all_passed": all_passed
    }


# ---------------------------------------------------------------------------
# File System Browser
# ---------------------------------------------------------------------------

@router.get("/fs/browse")
async def browse_fs(path: str = Query("")):
    if not path:
        if os.name == 'nt':
            import string
            drives = []
            for d in string.ascii_uppercase:
                if os.path.exists(f"{d}:\\"):
                    drives.append(f"{d}:\\")
            return {"current": "", "directories": drives}
        else:
            path = "/"
            
    try:
        target_path = Path(path).resolve()
        if not target_path.exists() or not target_path.is_dir():
            raise HTTPException(status_code=400, detail="Invalid path")
            
        directories = []
        for entry in os.scandir(target_path):
            if entry.is_dir() and not entry.name.startswith('.'):
                directories.append(entry.name)
                
        directories.sort(key=str.lower)
        
        return {
            "current": str(target_path),
            "parent": str(target_path.parent) if target_path.parent != target_path else "",
            "directories": directories
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Filesystem error.")
