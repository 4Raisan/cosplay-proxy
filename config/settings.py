"""Cosplay — Runtime Settings configuration and persistence.

Manages runtime settings with atomic JSON file persistence.
Storage location: ~/.cosplay/runtime.json
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
from pathlib import Path

from config.recovery import backup_corrupted_file, log_corruption

logger = logging.getLogger("cosplay.config")

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

COSPLAY_DIR = Path.home() / ".cosplay"
RUNTIME_FILE = COSPLAY_DIR / "runtime.json"


def _ensure_dir() -> None:
    """Create ~/.cosplay/ if it doesn't exist."""
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RuntimeSettings(BaseModel):
    """Runtime configuration for Cosplay."""

    # UI Configurable Settings
    api_auth_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    server_port: int = 8082
    connection_timeout: int = 30
    rate_limit_requests: int = 1
    rate_limit_seconds: int = 3
    skip_title_generation: bool = False

    # Internal / Read-only Constants (Removed from UI but active in backend)
    @property
    def max_concurrency(self) -> int:
        return 10

    @property
    def http_read_timeout(self) -> float:
        return 300.0

    @property
    def http_write_timeout(self) -> float:
        return 10.0

    @property
    def server_host(self) -> str:
        return "127.0.0.1"




# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class RuntimeSettingsManager:
    """Singleton manager for runtime configuration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = RuntimeSettings()
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    def load(self) -> None:
        """Load settings from disk. Missing file generates a new default config."""
        _ensure_dir()
        if not RUNTIME_FILE.exists():
            self.save()  # Auto-generates the API token on first run
            return

        try:
            raw = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
            self._settings = RuntimeSettings.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            backup_corrupted_file(RUNTIME_FILE)
            log_corruption(RUNTIME_FILE, exc)
            self._settings = RuntimeSettings()

    def save(self) -> None:
        """Atomically persist settings to disk."""
        _ensure_dir()
        data = self._settings.model_dump()

        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="runtime_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if RUNTIME_FILE.exists():
                RUNTIME_FILE.unlink()
            os.rename(tmp_path, str(RUNTIME_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self) -> RuntimeSettings:
        """Get the current settings object."""
        return self._settings

    def update(
        self,
        *,
        server_port: int | None = None,
        connection_timeout: int | None = None,
        rate_limit_requests: int | None = None,
        rate_limit_seconds: int | None = None,
        skip_title_generation: bool | None = None,
    ) -> RuntimeSettings:
        """Update configurable settings and persist."""
        if server_port is not None:
            self._settings.server_port = server_port
        if connection_timeout is not None:
            self._settings.connection_timeout = connection_timeout
        if rate_limit_requests is not None:
            self._settings.rate_limit_requests = rate_limit_requests
        if rate_limit_seconds is not None:
            self._settings.rate_limit_seconds = rate_limit_seconds
        if skip_title_generation is not None:
            self._settings.skip_title_generation = skip_title_generation

        self.save()
        return self._settings

    def regenerate_token(self) -> str:
        """Generate a new API auth token and persist."""
        new_token = secrets.token_urlsafe(32)
        self._settings.api_auth_token = new_token
        self.save()
        return new_token
