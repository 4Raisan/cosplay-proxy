"""Cosplay — Native connected-account management.

Persists account connection state in ~/.cosplay/accounts.json. The OpenAI
(ChatGPT) OAuth browser flow is a future phase; today this surfaces a clean
"disconnected" state and preserves the old FCC API surface.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ACCOUNTS_FILE = Path.home() / ".cosplay" / "accounts.json"


def _default_status() -> dict:
    return {
        "connected": False,
        "status": "disconnected",
        "email": None,
        "login_mode": None,
        "error": None,
    }


def _load() -> dict:
    if not ACCOUNTS_FILE.exists():
        return {}
    try:
        return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(ACCOUNTS_FILE.parent), suffix=".tmp", prefix="accounts_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if ACCOUNTS_FILE.exists():
            ACCOUNTS_FILE.unlink()
        os.rename(tmp_path, str(ACCOUNTS_FILE))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_openai_status() -> dict:
    """Get the current OpenAI account status."""
    data = _load()
    status = _default_status()
    status.update(data.get("openai", {}))
    return status


async def start_openai_login() -> dict:
    """Start the OpenAI (ChatGPT) login flow.

    Not yet implemented — returns an error status so the admin UI shows a
    graceful message instead of crashing.
    """
    status = _default_status()
    status.update(
        {
            "connected": False,
            "status": "error",
            "error": "OpenAI account login is not implemented yet.",
        }
    )
    return status


async def cancel_openai_login() -> dict:
    """Cancel an in-progress OpenAI login flow."""
    return _default_status()


async def disconnect_openai() -> dict:
    """Disconnect and revoke OpenAI credentials."""
    data = _load()
    data.pop("openai", None)
    _save(data)
    return _default_status()
