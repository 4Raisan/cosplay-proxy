"""Cosplay — Provider connection and model validation.

Two validation levels:

1. Connection validation — lightweight check that API key + base URL
   can reach the provider.
2. Model validation — sends the smallest valid request to test whether
   a specific model actually responds.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from providers.models import ApiType

# Timeout for validation requests (seconds)
VALIDATE_TIMEOUT = 15.0
MODEL_CHECK_TIMEOUT = 15.0


@dataclass
class ValidationResult:
    """Result of a connection or model validation."""

    success: bool
    message: str
    details: str = ""


# ---------------------------------------------------------------------------
# Connection validation
# ---------------------------------------------------------------------------

async def validate_connection(
    api_type: ApiType,
    base_url: str,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> ValidationResult:
    """Test that the provider is reachable and credentials are valid.

    Uses the lightest possible request per API type.
    """
    try:
        if api_type == ApiType.ANTHROPIC:
            return await _validate_anthropic(base_url, api_key, custom_headers)
        elif api_type == ApiType.LOCAL:
            return await _validate_local(base_url, custom_headers)
        else:
            # OpenAI Compatible and Gemini both use GET /models
            return await _validate_openai_compat(
                base_url, api_key, custom_headers
            )
    except httpx.ConnectError as e:
        return ValidationResult(
            success=False,
            message="Connection failed",
            details=f"Cannot reach {base_url}: {e}",
        )
    except httpx.TimeoutException:
        return ValidationResult(
            success=False,
            message="Connection timed out",
            details=f"No response from {base_url} within {VALIDATE_TIMEOUT}s",
        )
    except Exception as e:
        return ValidationResult(
            success=False,
            message="Validation failed",
            details=str(e),
        )


async def _validate_openai_compat(
    base_url: str,
    api_key: str,
    custom_headers: dict[str, str] | None,
) -> ValidationResult:
    """Validate by calling GET /models on an OpenAI-compatible endpoint."""
    url = _normalize_url(base_url).rstrip("/")
    if not url.endswith("/models"):
        url += "/models"

    headers = _build_headers(api_key, custom_headers)

    async with httpx.AsyncClient(timeout=VALIDATE_TIMEOUT) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code == 401:
        return ValidationResult(
            success=False,
            message="Authentication failed",
            details="Invalid API key — the provider returned 401 Unauthorized.",
        )
    if resp.status_code == 403:
        return ValidationResult(
            success=False,
            message="Access denied",
            details="The API key does not have permission — 403 Forbidden.",
        )
    if resp.status_code >= 400:
        body = "Error response truncated for security."
        return ValidationResult(
            success=False,
            message=f"Provider returned HTTP {resp.status_code}",
            details=body,
        )

    data = resp.json()
    model_count = len(data.get("data", []))
    return ValidationResult(
        success=True,
        message=f"Connected — {model_count} models available",
    )


async def _validate_anthropic(
    base_url: str,
    api_key: str,
    custom_headers: dict[str, str] | None,
) -> ValidationResult:
    """Validate an Anthropic provider by sending a minimal messages request."""
    url = _normalize_url(base_url).rstrip("/")
    if not url.endswith("/v1/messages"):
        url = url.rstrip("/") + "/v1/messages"

    headers = _build_headers("", custom_headers)
    headers["x-api-key"] = api_key
    headers["anthropic-version"] = "2023-06-01"
    headers["content-type"] = "application/json"

    body = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }

    async with httpx.AsyncClient(timeout=VALIDATE_TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code == 401:
        return ValidationResult(
            success=False,
            message="Authentication failed",
            details="Invalid API key — Anthropic returned 401.",
        )
    if resp.status_code == 403:
        return ValidationResult(
            success=False,
            message="Access denied",
            details="API key lacks permission — Anthropic returned 403.",
        )
    # 200 or 400 (bad model) both indicate the API is reachable
    if resp.status_code in (200, 400):
        return ValidationResult(
            success=True,
            message="Connected to Anthropic API",
        )
    body = "Error response truncated for security."
    return ValidationResult(
        success=False,
        message=f"Anthropic returned HTTP {resp.status_code}",
        details=body,
    )


async def _validate_local(
    base_url: str,
    custom_headers: dict[str, str] | None,
) -> ValidationResult:
    """Validate a local provider by checking /models or /api/tags."""
    url = _normalize_url(base_url).rstrip("/")
    headers = _build_headers("", custom_headers)

    async with httpx.AsyncClient(timeout=VALIDATE_TIMEOUT) as client:
        # Try /models first (LM Studio, llama.cpp)
        try:
            resp = await client.get(f"{url}/models", headers=headers)
            if resp.status_code == 200:
                return ValidationResult(
                    success=True,
                    message="Connected to local provider",
                )
        except (httpx.HTTPError, Exception):
            pass

        # Try /api/tags (Ollama)
        try:
            resp = await client.get(f"{url}/api/tags", headers=headers)
            if resp.status_code == 200:
                return ValidationResult(
                    success=True,
                    message="Connected to Ollama",
                )
        except (httpx.HTTPError, Exception):
            pass

    return ValidationResult(
        success=False,
        message="Local provider not reachable",
        details=f"Tried {url}/models and {url}/api/tags — neither responded.",
    )


# ---------------------------------------------------------------------------
# Model validation — test individual models
# ---------------------------------------------------------------------------

async def check_model_working(
    api_type: ApiType,
    base_url: str,
    model_id: str,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> ValidationResult:
    """Send the smallest valid request to test if a model responds.

    Returns success=True if the model can generate at least 1 token.
    """
    try:
        if api_type == ApiType.ANTHROPIC:
            return await _check_anthropic_model(
                base_url, model_id, api_key, custom_headers
            )
        else:
            # OpenAI, Gemini, and Local all use /chat/completions
            return await _check_openai_model(
                base_url, model_id, api_key, custom_headers
            )
    except httpx.ConnectError as e:
        return ValidationResult(
            success=False,
            message="Connection failed",
            details=str(e),
        )
    except httpx.TimeoutException:
        return ValidationResult(
            success=False,
            message="Model check timed out",
            details=f"{model_id} did not respond within {MODEL_CHECK_TIMEOUT}s",
        )
    except Exception as e:
        return ValidationResult(
            success=False,
            message="Model check failed",
            details=str(e),
        )


async def _check_openai_model(
    base_url: str,
    model_id: str,
    api_key: str,
    custom_headers: dict[str, str] | None,
) -> ValidationResult:
    """Test a model via POST /chat/completions with max_tokens=5."""
    url = _normalize_url(base_url).rstrip("/")
    if url.endswith("/models"):
        url = url[: -len("/models")]
    url = url.rstrip("/") + "/chat/completions"

    headers = _build_headers(api_key, custom_headers)
    headers["content-type"] = "application/json"

    # Strip provider_id prefix if model_id is stored as provider_id:model_name
    clean_model_id = model_id.split(":", 1)[-1] if ":" in model_id else model_id

    body = {
        "model": clean_model_id,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "hi"}],
    }

    async with httpx.AsyncClient(timeout=MODEL_CHECK_TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code in (200, 201):
        return ValidationResult(success=True, message="Working")
    if resp.status_code in (401, 403):
        return ValidationResult(
            success=False,
            message="Auth error",
            details=f"HTTP {resp.status_code} for model {clean_model_id}",
        )
    return ValidationResult(
        success=False,
        message=f"HTTP {resp.status_code}",
        details=f"Model check returned HTTP {resp.status_code}",
    )


async def _check_anthropic_model(
    base_url: str,
    model_id: str,
    api_key: str,
    custom_headers: dict[str, str] | None,
) -> ValidationResult:
    """Test an Anthropic model via POST /v1/messages with max_tokens=5."""
    url = _normalize_url(base_url).rstrip("/")
    if not url.endswith("/v1/messages"):
        url = url.rstrip("/") + "/v1/messages"

    headers = _build_headers("", custom_headers)
    headers["x-api-key"] = api_key
    headers["anthropic-version"] = "2023-06-01"
    headers["content-type"] = "application/json"

    clean_model_id = model_id.split(":", 1)[-1] if ":" in model_id else model_id

    body = {
        "model": clean_model_id,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "hi"}],
    }

    async with httpx.AsyncClient(timeout=MODEL_CHECK_TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code in (200, 201):
        return ValidationResult(success=True, message="Working")
    return ValidationResult(
        success=False,
        message=f"HTTP {resp.status_code}",
        details=f"Model check returned HTTP {resp.status_code}",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Ensure URL has a scheme."""
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _build_headers(
    api_key: str, custom_headers: dict[str, str] | None
) -> dict[str, str]:
    """Build request headers with auth and custom overrides."""
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if custom_headers:
        headers.update(custom_headers)
    return headers
