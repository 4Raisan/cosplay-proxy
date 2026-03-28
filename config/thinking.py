"""Cosplay — Thinking configuration and persistence.

Manages thinking/reasoning settings with atomic JSON file persistence.
Storage location: ~/.cosplay/thinking.json
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
THINKING_FILE = COSPLAY_DIR / "thinking.json"


def _ensure_dir() -> None:
    """Create ~/.cosplay/ if it doesn't exist."""
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ThinkingSettings(BaseModel):
    """Thinking configuration for Cosplay's routing paths."""

    default_thinking: str = "auto"
    primary_coding_thinking: str = "auto"
    fast_tasks_thinking: str = "auto"
    heavy_analysis_thinking: str = "auto"
    research_thinking: str = "auto"
    fallback_1_thinking: str = "auto"
    fallback_2_thinking: str = "auto"
    fallback_3_thinking: str = "auto"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class ThinkingManager:
    """Singleton manager for thinking configuration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = ThinkingSettings()
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    def load(self) -> None:
        """Load settings from disk."""
        _ensure_dir()
        if not THINKING_FILE.exists():
            self.save()
            return

        try:
            raw = json.loads(THINKING_FILE.read_text(encoding="utf-8"))
            self._settings = ThinkingSettings.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            backup_corrupted_file(THINKING_FILE)
            log_corruption(THINKING_FILE, exc)
            self._settings = ThinkingSettings()

    def save(self) -> None:
        """Atomically persist settings to disk."""
        _ensure_dir()
        data = self._settings.model_dump()

        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="thinking_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if THINKING_FILE.exists():
                THINKING_FILE.unlink()
            os.rename(tmp_path, str(THINKING_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self) -> ThinkingSettings:
        """Get the current thinking settings object."""
        return self._settings

    def update(
        self,
        *,
        default_thinking: str | None = None,
        primary_coding_thinking: str | None = None,
        fast_tasks_thinking: str | None = None,
        heavy_analysis_thinking: str | None = None,
        research_thinking: str | None = None,
        fallback_1_thinking: str | None = None,
        fallback_2_thinking: str | None = None,
        fallback_3_thinking: str | None = None,
    ) -> ThinkingSettings:
        """Update configurable settings and persist."""
        if default_thinking is not None:
            self._settings.default_thinking = default_thinking
        if primary_coding_thinking is not None:
            self._settings.primary_coding_thinking = primary_coding_thinking
        if fast_tasks_thinking is not None:
            self._settings.fast_tasks_thinking = fast_tasks_thinking
        if heavy_analysis_thinking is not None:
            self._settings.heavy_analysis_thinking = heavy_analysis_thinking
        if research_thinking is not None:
            self._settings.research_thinking = research_thinking
        if fallback_1_thinking is not None:
            self._settings.fallback_1_thinking = fallback_1_thinking
        if fallback_2_thinking is not None:
            self._settings.fallback_2_thinking = fallback_2_thinking
        if fallback_3_thinking is not None:
            self._settings.fallback_3_thinking = fallback_3_thinking
        
        self.save()
        return self._settings
