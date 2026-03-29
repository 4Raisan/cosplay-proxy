"""Cosplay — Model discovery per API type.

Queries upstream provider endpoints to discover available models natively.
"""

from __future__ import annotations

from providers.models import ApiType, ModelRecord


async def discover_models(
    api_type: ApiType,
    base_url: str,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
    provider_id: str = "",
) -> list[ModelRecord]:
    """Discover available models from a provider.

    Returns a list of ModelRecord with status=UNCHECKED.
    Raises Exception on failure.
    """
    if api_type == "anthropic":
        return _anthropic_models(provider_id)

    http_models = await _discover_http_models(base_url, api_key, custom_headers, provider_id)
    if http_models:
        return http_models

    raise ValueError("No models discovered from provider.")


async def _discover_http_models(
    base_url: str,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
    provider_id: str = "",
) -> list[ModelRecord]:
    """Fallback HTTP discovery for OpenAI-compatible, Gemini, and Local endpoints."""
    import httpx
    from providers.validator import _normalize_url, _build_headers

    url = _normalize_url(base_url).rstrip("/")
    headers = _build_headers(api_key, custom_headers)

    model_ids = []

    # 1. Try GET /models or GET /v1/models
    models_url = url if url.endswith("/models") else f"{url}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in items:
                    if isinstance(item, dict):
                        m_id = item.get("id") or item.get("name")
                        if m_id:
                            model_ids.append(str(m_id))
    except Exception:
        pass

    # 2. Try Ollama GET /api/tags if /models returned nothing
    if not model_ids:
        tags_url = f"{url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(tags_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("models", []):
                        if isinstance(item, dict) and (m_name := item.get("name") or item.get("model")):
                            model_ids.append(str(m_name))
        except Exception:
            pass

    records = [
        ModelRecord(
            model_id=m_id,
            display_name=m_id,
            provider_id=provider_id,
            supports_thinking=(
                True
                if (
                    "thinking" in m_id.lower()
                    or "reason" in m_id.lower()
                    or "r1" in m_id.lower()
                )
                else None
            ),
        )
        for m_id in set(model_ids)
    ]
    records.sort(key=lambda m: m.model_id.lower())
    return records


# ---------------------------------------------------------------------------
# Anthropic hardcoded model list (no public /models endpoint)
# ---------------------------------------------------------------------------

_ANTHROPIC_MODELS = [
    ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
    ("claude-opus-4-20250514", "Claude Opus 4"),
    ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet"),
    ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet v2"),
    ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
    ("claude-3-opus-20240229", "Claude 3 Opus"),
    ("claude-3-haiku-20240307", "Claude 3 Haiku"),
]

def _anthropic_models(provider_id: str) -> list[ModelRecord]:
    """Return the hardcoded Anthropic model list."""
    return [
        ModelRecord(
            model_id=mid,
            display_name=name,
            provider_id=provider_id,
            supports_thinking=True if "claude-3-7" in mid else None,
        )
        for mid, name in _ANTHROPIC_MODELS
    ]
