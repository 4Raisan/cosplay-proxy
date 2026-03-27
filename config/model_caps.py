"""Cosplay — persisted model reasoning capability records.

Storage: ~/.cosplay/model_caps.json, keyed ``provider:model`` →
``{supports_thinking, max_rank, verified, source, updated_at}``.

Records are written by successful proxy requests (``mark_model_used``), by the
working-model check (``record_cap_from_check``), and by an explicit admin
override (``put``). Admin overrides are never clobbered by later usage records.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

COSPLAY_DIR = Path.home() / ".cosplay"
MODEL_CAPS_FILE = COSPLAY_DIR / "model_caps.json"


def _ensure_dir() -> None:
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class ModelCapsManager:
    """Singleton manager for persisted model reasoning capabilities."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._records: dict[str, dict[str, Any]] = {}
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    # -- persistence --------------------------------------------------------

    def load(self) -> None:
        if not MODEL_CAPS_FILE.exists():
            return
        try:
            raw = json.loads(MODEL_CAPS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._records = raw
        except Exception:
            self._records = {}

    def save(self) -> None:
        _ensure_dir()
        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="model_caps_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._records, f, indent=2)
            if MODEL_CAPS_FILE.exists():
                MODEL_CAPS_FILE.unlink()
            os.rename(tmp_path, str(MODEL_CAPS_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # -- accessors ----------------------------------------------------------

    @staticmethod
    def _key(provider_id: str, model_id: str) -> str:
        return f"{provider_id}:{model_id}"

    def get(self, provider_id: str, model_id: str) -> dict[str, Any] | None:
        rec = self._records.get(self._key(provider_id, model_id))
        return dict(rec) if rec else None

    def put(
        self,
        provider_id: str,
        model_id: str,
        *,
        supports_thinking: bool,
        max_rank: int,
        verified: bool = True,
        source: str = "verified",
    ) -> dict[str, Any]:
        """Store (or override) a capability record. Admin overrides are
        protected from later usage writes by `mark_model_used`."""
        rec = {
            "supports_thinking": bool(supports_thinking),
            "max_rank": int(max_rank),
            "verified": bool(verified),
            "source": source,
            "updated_at": _now(),
        }
        self._records[self._key(provider_id, model_id)] = rec
        self.save()
        return dict(rec)

    def mark_model_used(
        self,
        provider_id: str,
        model_id: str,
        *,
        supports_thinking: bool = True,
        max_rank: int = 5,
        source: str = "used",
    ) -> dict[str, Any] | None:
        """Record that a model served a successful request. Never overwrites
        an admin override. A permissive baseline (rank 5, supports thinking)
        is persisted for unknown models so verified records beat the
        id-heuristic while never being more restrictive than the default."""
        key = self._key(provider_id, model_id)
        existing = self._records.get(key)
        if existing and existing.get("source") == "admin":
            return None
        rec = {
            "supports_thinking": bool(supports_thinking),
            "max_rank": int(max_rank),
            "verified": True,
            "source": source,
            "updated_at": _now(),
        }
        self._records[key] = rec
        self.save()
        return dict(rec)

    def clear(self, provider_id: str, model_id: str) -> bool:
        key = self._key(provider_id, model_id)
        if key not in self._records:
            return False
        del self._records[key]
        self.save()
        return True
