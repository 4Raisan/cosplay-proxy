"""Cosplay — Web and Voice configuration persistence.

Manages Web Search and Voice settings with atomic JSON file persistence.
Storage location: ~/.cosplay/web_voice.json
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
WEB_VOICE_FILE = COSPLAY_DIR / "web_voice.json"


def _ensure_dir() -> None:
    """Create ~/.cosplay/ if it doesn't exist."""
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class WebVoiceSettings(BaseModel):
    """Web Search and Voice configuration for Cosplay."""

    enable_web_search: bool = True
    allow_private_network: bool = False
    enable_voice: bool = False
    voice_model: str | None = None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class WebVoiceManager:
    """Singleton manager for web and voice configuration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = WebVoiceSettings()
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    def load(self) -> None:
        """Load settings from disk."""
        _ensure_dir()
        if not WEB_VOICE_FILE.exists():
            self.save()
            return

        try:
            raw = json.loads(WEB_VOICE_FILE.read_text(encoding="utf-8"))
            self._settings = WebVoiceSettings.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            backup_corrupted_file(WEB_VOICE_FILE)
            log_corruption(WEB_VOICE_FILE, exc)
            self._settings = WebVoiceSettings()

    def save(self) -> None:
        """Atomically persist settings to disk."""
        _ensure_dir()
        data = self._settings.model_dump()

        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="web_voice_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if WEB_VOICE_FILE.exists():
                WEB_VOICE_FILE.unlink()
            os.rename(tmp_path, str(WEB_VOICE_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self) -> WebVoiceSettings:
        """Get the current web and voice settings object."""
        return self._settings

    def update(
        self,
        *,
        enable_web_search: bool | None = None,
        allow_private_network: bool | None = None,
        enable_voice: bool | None = None,
        voice_model: str | None = None,
    ) -> WebVoiceSettings:
        """Update configurable settings and persist."""
        if enable_web_search is not None:
            self._settings.enable_web_search = enable_web_search
        if allow_private_network is not None:
            self._settings.allow_private_network = allow_private_network
        if enable_voice is not None:
            self._settings.enable_voice = enable_voice
            
        # Voice model can be explicitly unset (None)
        self._settings.voice_model = voice_model
        
        self.save()
        return self._settings
