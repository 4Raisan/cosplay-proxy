"""Cosplay — Model Routing configuration and persistence.

Manages routing settings with atomic JSON file persistence.
Storage location: ~/.cosplay/routing.json
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
ROUTING_FILE = COSPLAY_DIR / "routing.json"


def _ensure_dir() -> None:
    """Create ~/.cosplay/ if it doesn't exist."""
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RoutingSettings(BaseModel):
    """Routing configuration for Cosplay."""

    # Models are stored as provider_id:model_id
    default_model: str | None = None
    primary_coding_model: str | None = None
    fast_tasks_model: str | None = None
    heavy_analysis_model: str | None = None
    research_model: str | None = None
    
    fallback_1: str | None = None
    fallback_2: str | None = None
    fallback_3: str | None = None

    @property
    def effective_default_model(self) -> str | None:
        # For backwards compatibility and logic, if default_model isn't explicitly set, fallback to primary coding model
        return self.default_model or self.primary_coding_model

    @property
    def effective_fast_tasks_model(self) -> str | None:
        return self.fast_tasks_model or self.primary_coding_model or self.default_model

    @property
    def effective_heavy_analysis_model(self) -> str | None:
        return self.heavy_analysis_model or self.primary_coding_model or self.default_model

    @property
    def effective_research_model(self) -> str | None:
        return self.research_model or self.heavy_analysis_model or self.primary_coding_model or self.default_model


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class RoutingManager:
    """Singleton manager for routing configuration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = RoutingSettings()
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    def load(self) -> None:
        """Load settings from disk."""
        _ensure_dir()
        if not ROUTING_FILE.exists():
            self.save()
            return

        try:
            raw = json.loads(ROUTING_FILE.read_text(encoding="utf-8"))
            self._settings = RoutingSettings.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            backup_corrupted_file(ROUTING_FILE)
            log_corruption(ROUTING_FILE, exc)
            self._settings = RoutingSettings()

    def save(self) -> None:
        """Atomically persist settings to disk."""
        _ensure_dir()
        data = self._settings.model_dump()

        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="routing_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if ROUTING_FILE.exists():
                ROUTING_FILE.unlink()
            os.rename(tmp_path, str(ROUTING_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self) -> RoutingSettings:
        """Get the current routing settings object."""
        return self._settings

    def update(
        self,
        *,
        default_model: str | None = None,
        primary_coding_model: str | None = None,
        fast_tasks_model: str | None = None,
        heavy_analysis_model: str | None = None,
        research_model: str | None = None,
        fallback_1: str | None = None,
        fallback_2: str | None = None,
        fallback_3: str | None = None,
    ) -> RoutingSettings:
        """Update configurable settings and persist."""
        self._settings.default_model = default_model
        self._settings.primary_coding_model = primary_coding_model
        self._settings.fast_tasks_model = fast_tasks_model
        self._settings.heavy_analysis_model = heavy_analysis_model
        self._settings.research_model = research_model
        self._settings.fallback_1 = fallback_1
        self._settings.fallback_2 = fallback_2
        self._settings.fallback_3 = fallback_3
        
        self.save()
        return self._settings
