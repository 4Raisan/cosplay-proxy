"""Cosplay — Provider data models and types."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ApiType(StrEnum):
    """Supported API protocol families."""

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    LOCAL = "local"


class AuthKind(StrEnum):
    """How a provider authenticates."""

    API_KEY = "api_key"
    CONNECTED_ACCOUNT = "connected_account"


class ConnectionStatus(StrEnum):
    """Provider connection status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    UNKNOWN = "unknown"


class ModelStatus(StrEnum):
    """Individual model working status."""

    WORKING = "working"
    FAILED = "failed"
    UNCHECKED = "unchecked"
    CHECKING = "checking"


# ---------------------------------------------------------------------------
# Provider record — persisted to JSON
# ---------------------------------------------------------------------------

class ProviderRecord(BaseModel):
    """A single saved provider configuration."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    api_type: ApiType
    base_url: str = ""
    api_key: str = ""
    custom_headers: dict[str, str] = Field(default_factory=dict)
    auth_kind: AuthKind = AuthKind.API_KEY
    connection_status: ConnectionStatus = ConnectionStatus.UNKNOWN
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    enabled: bool = True

    def touch(self) -> None:
        """Update the `updated_at` timestamp to now."""
        self.updated_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Model record — cached per provider
# ---------------------------------------------------------------------------

class ModelRecord(BaseModel):
    """Cached metadata for one model within a provider."""

    model_id: str
    display_name: str = ""
    provider_id: str = ""
    status: ModelStatus = ModelStatus.UNCHECKED
    last_checked: str | None = None
    error_message: str | None = None
    supports_thinking: bool | None = None


# ---------------------------------------------------------------------------
# API request / response shapes
# ---------------------------------------------------------------------------

class AddProviderRequest(BaseModel):
    """Payload for creating a new provider."""

    name: str
    api_type: ApiType
    base_url: str = ""
    api_key: str = ""
    custom_headers: dict[str, str] = Field(default_factory=dict)


class UpdateProviderRequest(BaseModel):
    """Payload for updating an existing provider."""

    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    custom_headers: dict[str, str] | None = None
    enabled: bool | None = None


class ValidateRequest(BaseModel):
    """Payload for connection validation (without saving)."""

    api_type: ApiType
    base_url: str = ""
    api_key: str = ""
    custom_headers: dict[str, str] = Field(default_factory=dict)


class ProviderSummary(BaseModel):
    """Public-facing provider summary returned by the API."""

    id: str
    name: str
    api_type: ApiType
    base_url: str
    auth_kind: AuthKind
    connection_status: ConnectionStatus
    model_count: int = 0
    working_model_count: int = 0
    unchecked_model_count: int = 0
    failed_model_count: int = 0
    created_at: str
    updated_at: str
    enabled: bool = True


class AccountProvider(BaseModel):
    """An account-based provider available for connection."""

    id: str
    name: str
    description: str = ""
    connected: bool = False
    account_email: str | None = None
    coming_soon: bool = False
