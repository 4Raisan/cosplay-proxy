"""Cosplay — Provider registry with JSON file persistence.

Manages saved providers and their cached model lists.
Storage location: ~/.cosplay/providers.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.recovery import backup_corrupted_file, log_corruption

logger = logging.getLogger("cosplay.config")


from providers.models import (
    AuthKind,
    ConnectionStatus,
    ModelRecord,
    ModelStatus,
    ProviderRecord,
    ProviderSummary,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

COSPLAY_DIR = Path.home() / ".cosplay"
PROVIDERS_FILE = COSPLAY_DIR / "providers.json"


def _ensure_dir() -> None:
    """Create ~/.cosplay/ if it doesn't exist."""
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """In-memory provider store backed by a JSON file.

    Thread safety is not required — FastAPI runs on a single event loop and
    all mutating API calls are sequential.  The JSON file is written
    atomically (write-to-temp then rename) to prevent corruption.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers = {}
            cls._instance._models = {}
            cls._instance.load()
        return cls._instance

    def __init__(self) -> None:
        pass

    # -- persistence --------------------------------------------------------

    def load(self) -> None:
        """Load providers and models from disk."""
        _ensure_dir()
        if not PROVIDERS_FILE.exists():
            return
        try:
            raw = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            backup_corrupted_file(PROVIDERS_FILE)
            log_corruption(PROVIDERS_FILE, exc)
            return

        for p_data in raw.get("providers", []):
            try:
                rec = ProviderRecord.model_validate(p_data)
                self._providers[rec.id] = rec
            except Exception:
                continue

        for pid, m_list in raw.get("models", {}).items():
            records: list[ModelRecord] = []
            for m_data in m_list:
                try:
                    records.append(ModelRecord.model_validate(m_data))
                except Exception:
                    continue
            self._models[pid] = records

    def save(self) -> None:
        """Atomically persist current state to disk."""
        _ensure_dir()
        data = {
            "providers": [p.model_dump() for p in self._providers.values()],
            "models": {
                pid: [m.model_dump() for m in mlist]
                for pid, mlist in self._models.items()
            },
        }
        # Atomic write: temp file → rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(COSPLAY_DIR), suffix=".tmp", prefix="providers_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # On Windows, target must not exist for os.rename
            if PROVIDERS_FILE.exists():
                PROVIDERS_FILE.unlink()
            os.rename(tmp_path, str(PROVIDERS_FILE))
        except Exception:
            # Cleanup temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # -- provider CRUD ------------------------------------------------------

    def add_provider(self, provider: ProviderRecord) -> ProviderRecord:
        """Add a new provider and persist."""
        self._providers[provider.id] = provider
        self._models.setdefault(provider.id, [])
        self.save()
        return provider

    def update_provider(
        self,
        provider_id: str,
        *,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        custom_headers: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> ProviderRecord | None:
        """Update fields on an existing provider.  Returns None if not found."""
        rec = self._providers.get(provider_id)
        if rec is None:
            return None
        if name is not None:
            rec.name = name
        if base_url is not None:
            rec.base_url = base_url
        if api_key is not None:
            rec.api_key = api_key
        if custom_headers is not None:
            rec.custom_headers = custom_headers
        if enabled is not None:
            rec.enabled = enabled
        rec.touch()
        self.save()
        return rec

    def remove_provider(self, provider_id: str) -> bool:
        """Remove a provider and its cached models.  Returns True if removed."""
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        self._models.pop(provider_id, None)
        self.save()
        return True

    def get_provider(self, provider_id: str) -> ProviderRecord | None:
        """Return a provider by ID or None."""
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ProviderRecord]:
        """Return all providers ordered by creation time."""
        return sorted(self._providers.values(), key=lambda p: p.created_at)

    # -- model cache --------------------------------------------------------

    def set_models(self, provider_id: str, models: list[ModelRecord]) -> None:
        """Replace the cached model list for a provider and persist.

        Rediscovered models keep their previous working-check verdict
        (status / last_checked / error_message) so a page refresh never
        wipes saved results. Verdicts change only via an explicit check.
        """
        previous = {m.model_id: m for m in self._models.get(provider_id, [])}
        merged: list[ModelRecord] = []
        for m in models:
            old = previous.get(m.model_id)
            if old is not None and old.status != ModelStatus.UNCHECKED:
                m.status = old.status
                m.last_checked = old.last_checked
                m.error_message = old.error_message
            merged.append(m)
        self._models[provider_id] = merged
        # Also update the provider timestamp
        rec = self._providers.get(provider_id)
        if rec is not None:
            rec.touch()
        self.save()

    def get_models(self, provider_id: str) -> list[ModelRecord]:
        """Return cached models for a provider."""
        return list(self._models.get(provider_id, []))

    def set_model_status(
        self,
        provider_id: str,
        model_id: str,
        status: ModelStatus,
        error_message: str | None = None,
        save: bool = True,
    ) -> None:
        """Update the working status of one model."""
        for m in self._models.get(provider_id, []):
            if m.model_id == model_id:
                m.status = status
                m.last_checked = datetime.now(timezone.utc).isoformat()
                m.error_message = error_message
                break
        if save:
            self.save()

    # -- summaries for the API ----------------------------------------------

    def provider_summary(self, provider_id: str) -> ProviderSummary | None:
        """Build a public summary for one provider."""
        rec = self._providers.get(provider_id)
        if rec is None:
            return None
        models = self._models.get(provider_id, [])
        return ProviderSummary(
            id=rec.id,
            name=rec.name,
            api_type=rec.api_type,
            base_url=rec.base_url,
            auth_kind=rec.auth_kind,
            connection_status=rec.connection_status,
            model_count=len(models),
            working_model_count=sum(
                1 for m in models if m.status == ModelStatus.WORKING
            ),
            unchecked_model_count=sum(
                1 for m in models if m.status == ModelStatus.UNCHECKED
            ),
            failed_model_count=sum(
                1 for m in models if m.status == ModelStatus.FAILED
            ),
            created_at=rec.created_at,
            updated_at=rec.updated_at,
            enabled=rec.enabled,
        )

    def all_summaries(self) -> list[ProviderSummary]:
        """Build public summaries for all providers."""
        return [
            s
            for pid in self._providers
            if (s := self.provider_summary(pid)) is not None
        ]
