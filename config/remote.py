"""Cosplay — Remote Access configuration persistence.

Manages Telegram and workspace settings with atomic JSON file persistence.
Storage location: ~/.cosplay/remote.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from config.recovery import backup_corrupted_file, log_corruption

logger = logging.getLogger("cosplay.config")

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

COSPLAY_DIR = Path.home() / ".cosplay"
REMOTE_FILE = COSPLAY_DIR / "remote.json"


def _ensure_dir() -> None:
    """Create ~/.cosplay/ if it doesn't exist."""
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RemoteSettings(BaseModel):
    """Remote access configuration for Cosplay."""

    enable_telegram: bool = False
    telegram_token: str = ""
    telegram_paired_user_id: int | None = None
    telegram_paired_username: str | None = None
    workspace_folder: str = ""
    allow_voice: bool = False


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class RemoteManager:
    """Singleton manager for remote access configuration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = RemoteSettings()
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    def load(self) -> None:
        """Load settings from disk."""
        _ensure_dir()
        if not REMOTE_FILE.exists():
            self.save()
            return

        try:
            raw = json.loads(REMOTE_FILE.read_text(encoding="utf-8"))
            self._settings = RemoteSettings.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            backup_corrupted_file(REMOTE_FILE)
            log_corruption(REMOTE_FILE, exc)
            self._settings = RemoteSettings()

    def save(self) -> None:
        """Atomically persist settings to disk."""
        _ensure_dir()
        data = self._settings.model_dump()

        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="remote_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if REMOTE_FILE.exists():
                REMOTE_FILE.unlink()
            os.rename(tmp_path, str(REMOTE_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self) -> RemoteSettings:
        """Get the current remote settings object."""
        return self._settings

    def update(
        self,
        *,
        enable_telegram: bool | None = None,
        telegram_token: str | None = None,
        telegram_paired_user_id: int | None = None,
        telegram_paired_username: str | None = None,
        workspace_folder: str | None = None,
        allow_voice: bool | None = None,

    ) -> RemoteSettings:
        """Update configurable settings and persist."""
        if enable_telegram is not None:
            self._settings.enable_telegram = enable_telegram
        if telegram_token is not None:
            self._settings.telegram_token = telegram_token
            
        # These can be explicitly unset (None) to unpair
        if telegram_paired_user_id is not None or telegram_paired_username is not None:
            # If they pass empty string or 0, treat as unpairing
            if not telegram_paired_user_id:
                self._settings.telegram_paired_user_id = None
                self._settings.telegram_paired_username = None
            else:
                self._settings.telegram_paired_user_id = telegram_paired_user_id
                self._settings.telegram_paired_username = telegram_paired_username

        if workspace_folder is not None:
            self._settings.workspace_folder = workspace_folder
        if allow_voice is not None:
            self._settings.allow_voice = allow_voice

            
        self.save()
        return self._settings
