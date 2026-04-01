"""Cosplay proxy — model routing.

Resolves the gateway model id sent by the client (e.g. ``cosplay-default``,
``claude-sonnet-4-20250514``) into a concrete (provider_id, model) pair using
the user's routing configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.routing import RoutingSettings
from providers.registry import ProviderRegistry

from .errors import InvalidRequest, NotFoundError

# Gateway model ids exposed via GET /v1/models. The claude-cosplay-* ids are
# what Claude Code's discovery keeps (ids must contain claude/anthropic); the
# legacy cosplay-* ids are kept for backward compatibility.
GATEWAY_IDS = {
    "claude-cosplay-default": "default",
    "claude-cosplay-coding": "primary_coding",
    "claude-cosplay-fast": "fast_tasks",
    "claude-cosplay-reasoning": "heavy_analysis",
    "claude-cosplay-research": "research",
    "cosplay-default": "default",
    "cosplay-sonnet-coding": "primary_coding",
    "cosplay-haiku-tasks": "fast_tasks",
    "cosplay-opus-analysis": "heavy_analysis",
    "cosplay-fable-research": "research",
}

# Anthropic-style names sent by clients that do not trust /v1/models.
_ANTHROPIC_ALIASES = {
    "sonnet": ("claude-sonnet", "primary_coding"),
    "opus": ("claude-opus", "heavy_analysis"),
    "haiku": ("claude-haiku", "fast_tasks"),
    "fable": ("claude-fable", "research"),
}


@dataclass
class RouteTarget:
    """A resolved provider + model for one request attempt."""

    provider_id: str
    model: str
    base_url: str
    api_key: str
    custom_headers: dict[str, str]

    @property
    def provider_ref(self) -> str:
        return f"{self.provider_id}:{self.model}"


def _slot_ref(slot: str, routing: RoutingSettings) -> str | None:
    """Return the configured provider:model reference for a routing slot."""
    if slot == "default":
        return routing.effective_default_model
    if slot == "primary_coding":
        return routing.primary_coding_model or routing.effective_default_model
    if slot == "fast_tasks":
        return routing.effective_fast_tasks_model
    if slot == "heavy_analysis":
        return routing.effective_heavy_analysis_model
    if slot == "research":
        return routing.effective_research_model
    return None


def resolve_slot(gateway_model: str | None) -> str | None:
    """Map a client model id to its routing slot, or None when unknown.

    Accepts the gateway ids (claude-cosplay-* / legacy cosplay-*), Anthropic
    aliases (claude-sonnet-*, ...), and falls back to the default slot for
    anything else so effort settings still apply.
    """
    g = (gateway_model or "").strip()
    if not g:
        return "default"
    slot = GATEWAY_IDS.get(g)
    if slot is not None:
        return slot
    low = g.lower()
    for _prefix, slot in _ANTHROPIC_ALIASES.values():
        if low.startswith(_prefix):
            return slot
    return "default"


def _known_provider_ids(registry: ProviderRegistry) -> set[str]:
    return {p.id for p in registry.list_providers() if p.enabled}


def _known_provider_names(registry: ProviderRegistry) -> dict[str, str]:
    return {
        p.name.lower(): p.id
        for p in registry.list_providers()
        if p.enabled and p.name
    }


def resolve_route(
    gateway_model: str | None,
    routing: RoutingSettings,
    registry: ProviderRegistry,
) -> RouteTarget:
    """Resolve a client model id to a concrete RouteTarget."""
    ref = _pick_ref(gateway_model, routing, registry)
    if not ref:
        raise NotFoundError(f"Unknown model: {gateway_model or ''}")
    return _ref_to_target(ref, registry, gateway_model)


def _pick_ref(
    gateway_model: str | None,
    routing: RoutingSettings,
    registry: ProviderRegistry,
) -> str | None:
    g = (gateway_model or "").strip()
    if not g:
        return routing.effective_default_model

    # 1. Cosplay gateway ids.
    slot = GATEWAY_IDS.get(g)
    if slot is not None:
        return _slot_ref(slot, routing)

    # 2. Anthropic-style aliases.
    low = g.lower()
    for _prefix, slot in _ANTHROPIC_ALIASES.values():
        if low.startswith(_prefix):
            return _slot_ref(slot, routing)

    # 3. Direct 'provider:model' or 'provider/model' references.
    direct = _parse_direct(g, registry)
    if direct:
        return direct

    # 4. Match a bare model name against configured refs, e.g.
    # 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning' (as exposed
    # verbatim by GET /v1/models) or a plain short name.
    for ref in _configured_refs(routing):
        model_part = ref.partition(":")[2]
        if g == model_part or g == model_part.rsplit("/", 1)[-1]:
            return ref

    # 5. Exact match against a configured routing value.
    if g in _configured_refs(routing):
        return g

    # 6. Fall back to the default model.
    return routing.effective_default_model


def _configured_refs(routing: RoutingSettings) -> list[str]:
    """Deduplicated configured model references, in priority order."""
    seen: set[str] = set()
    refs = []
    for ref in (
        routing.effective_default_model,
        routing.primary_coding_model,
        routing.effective_fast_tasks_model,
        routing.effective_heavy_analysis_model,
        routing.effective_research_model,
        routing.fallback_1,
        routing.fallback_2,
        routing.fallback_3,
    ):
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _parse_direct(
    g: str, registry: ProviderRegistry
) -> str | None:
    """Parse 'provider:model' or 'provider/model' when provider is known."""
    provider_ids = _known_provider_ids(registry)
    provider_names = _known_provider_names(registry)

    if ":" in g:
        pid, model = g.split(":", 1)
        if model and (pid in provider_ids or pid.lower() in provider_names):
            resolved = provider_names.get(pid.lower(), pid)
            return f"{resolved}:{model}"

    if "/" in g:
        pid, model = g.split("/", 1)
        if model and pid in provider_ids:
            return f"{pid}:{model}"
    return None


def _ref_to_target(
    ref: str, registry: ProviderRegistry, gateway_model: str | None
) -> RouteTarget:
    provider_id, sep, model = ref.partition(":")
    if not sep or not model:
        raise InvalidRequest(
            f"Configured model reference is invalid: {ref!r} (expected provider:model)"
        )
    provider = registry.get_provider(provider_id)
    if provider is None:
        raise NotFoundError(f"Unknown provider: {provider_id}")
    if not provider.enabled:
        raise NotFoundError(f"Provider is disabled: {provider.name}")
    if not model:
        raise NotFoundError(f"Model is empty for provider: {provider.name}")
    return RouteTarget(
        provider_id=provider.id,
        model=model,
        base_url=provider.base_url,
        api_key=provider.api_key,
        custom_headers=provider.custom_headers,
    )


def fallback_targets(
    routing: RoutingSettings, registry: ProviderRegistry
) -> list[str]:
    """Return the configured fallback model references (non-empty)."""
    return [
        ref
        for ref in (routing.fallback_1, routing.fallback_2, routing.fallback_3)
        if ref
    ]
