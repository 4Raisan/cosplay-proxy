"""Cosplay — Native runtime adapter.

Provides the `get_provider_runtime()` / `flush_runtime_cache()` surface that the
admin API consumed from the old free-claude-code (FCC) engine. The native proxy
engine reads configuration live on every request, so the cache is a no-op and
runtime queries are served from the configured routing table.
"""

from __future__ import annotations

from typing import Any


class _NativeModelCache:
    """Minimal model metadata store backed by the configured routing table."""

    def __init__(self) -> None:
        self._models: list[tuple[str, str]] = []

    def refresh(self, models: list[tuple[str, str]]) -> None:
        self._models = models

    def cached_model_ids(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for provider_id, model_id in self._models:
            grouped.setdefault(provider_id, []).append(model_id)
        return grouped

    def cached_model_supports_thinking(self, provider_id: str, model_id: str) -> bool | None:
        """Return None (unknown) so thinking settings stay configurable."""
        return None


class _NativeRuntime:
    def __init__(self) -> None:
        self.model_cache = _NativeModelCache()

    def refresh_model_cache(self) -> None:
        models: list[tuple[str, str]] = []
        try:
            from providers.registry import ProviderRegistry
            from config.routing import RoutingManager

            routing = RoutingManager().get()
            refs = [
                routing.effective_default_model,
                routing.primary_coding_model,
                routing.effective_fast_tasks_model,
                routing.effective_heavy_analysis_model,
                routing.effective_research_model,
                routing.fallback_1,
                routing.fallback_2,
                routing.fallback_3,
            ]
            for ref in refs:
                if not ref:
                    continue
                if ":" in ref:
                    pid, mid = ref.split(":", 1)
                else:
                    pid, mid = "", ref
                models.append((pid, mid))
        except Exception:
            pass
        self.model_cache.refresh(models)


_global_runtime: _NativeRuntime | None = None


def get_provider_runtime() -> _NativeRuntime:
    """Return the native runtime object used by admin capability queries."""
    global _global_runtime
    if _global_runtime is None:
        _global_runtime = _NativeRuntime()
        _global_runtime.refresh_model_cache()
    return _global_runtime


def flush_runtime_cache() -> None:
    """No-op: the native engine reads configuration live on every request."""
    global _global_runtime
    _global_runtime = None


def get_fcc_settings() -> None:
    """Removed: the native engine does not use FCC Settings."""
    return None
