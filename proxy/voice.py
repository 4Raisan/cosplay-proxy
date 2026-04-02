"""Cosplay proxy — Voice note transcription via NVIDIA NIM Whisper.

Used by the Telegram daemon when voice notes are enabled. Uses the first
enabled NVIDIA/NIM provider's OpenAI-compatible /audio/transcriptions endpoint.
"""

from __future__ import annotations

import httpx

from config.web_voice import WebVoiceManager
from providers.registry import ProviderRegistry


def _nim_target() -> tuple[str, str] | None:
    """Return (base_url, api_key) of the first enabled NVIDIA/NIM provider."""
    registry = ProviderRegistry()
    for p in registry.list_providers():
        if not p.enabled:
            continue
        name = (p.name or "").lower()
        if "nvidia" in name or "nim" in name:
            return p.base_url or "", p.api_key or ""
    return None


def transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    """Transcribe audio bytes to text using the configured NIM whisper model."""
    settings = WebVoiceManager().get()
    model = settings.voice_model or "openai/whisper-large-v3"

    target = _nim_target()
    if target is None:
        return None

    base_url, api_key = target
    url = base_url.rstrip("/").replace("/v1", "") + "/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                url,
                headers=headers,
                data={"model": model},
                files={"file": (filename, audio_bytes)},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            text = data.get("text")
            return str(text) if text else None
    except httpx.HTTPError:
        return None
