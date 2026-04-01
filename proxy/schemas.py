"""Cosplay proxy — Anthropic Messages API request/response models.

Deliberately permissive: unknown fields are ignored so newer Claude Code
clients keep working. Only the fields we translate are modeled.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContentBlock(BaseModel):
    """A single content block inside a message."""

    model_config = ConfigDict(extra="ignore")

    type: str
    text: str | None = None
    thinking: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    content: Any = None
    tool_use_id: str | None = None


class AnthropicMessage(BaseModel):
    """One message in the Anthropic conversation."""

    model_config = ConfigDict(extra="ignore")

    role: str
    content: str | list[ContentBlock] = ""


class ToolDefinition(BaseModel):
    """A tool the model may call."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    type: str = "custom"
    server_tool: bool = False


class ThinkingConfig(BaseModel):
    """Extended thinking configuration."""

    model_config = ConfigDict(extra="ignore")

    type: str = "disabled"
    budget_tokens: int | None = None


class ToolChoice(BaseModel):
    """Tool selection policy."""

    model_config = ConfigDict(extra="ignore")

    type: str = "auto"
    name: str | None = None


class OutputConfig(BaseModel):
    """Claude Code output configuration (delivers /effort)."""

    model_config = ConfigDict(extra="ignore")

    effort: str | None = None
    reasoning_effort: str | None = None


class MessagesRequest(BaseModel):
    """Inbound POST /v1/messages payload."""

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    max_tokens: int | None = None
    messages: list[AnthropicMessage] = Field(default_factory=list)
    system: str | list[ContentBlock] | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: ToolChoice | None = None
    thinking: ThinkingConfig | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    metadata: dict[str, Any] | None = None
    store: bool | None = None
    context: Any = None
    output_config: OutputConfig | None = None

    def client_effort(self) -> str | None:
        """Extract the client's requested reasoning effort.

        Prefers ``output_config.effort`` (Claude Code /effort); the classic
        ``thinking`` block with type ``enabled`` maps to ``high``.
        """
        if self.output_config and self.output_config.effort:
            return self.output_config.effort
        if self.thinking and self.thinking.type == "enabled":
            return "high"
        return None

    def system_text(self) -> str | None:
        """Flatten the system field to plain text."""
        if self.system is None:
            return None
        if isinstance(self.system, str):
            return self.system
        parts = []
        for block in self.system:
            if isinstance(block, ContentBlock) and block.type == "text" and block.text:
                parts.append(block.text)
        return "\n".join(parts) or None


def block_text(block: ContentBlock) -> str:
    """Extract plain text from a content block."""
    if block.type == "text" and block.text:
        return block.text
    if block.type == "tool_result":
        content = block.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                b.text or ""
                for b in content
                if isinstance(b, ContentBlock) and b.type == "text"
            )
    return ""
