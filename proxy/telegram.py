"""Cosplay proxy — Native Telegram bot.

Runs a config-driven Telegram bot (disabled by default) that answers the paired
user's messages using the native routing engine. Voice notes are transcribed
via NVIDIA NIM Whisper when enabled.
"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from config.remote import RemoteManager
from proxy.voice import transcribe


def _is_paired(update: Update) -> bool:
    remote = RemoteManager().get()
    if remote.telegram_paired_user_id is None:
        return False
    user = update.effective_user
    return user is not None and user.id == remote.telegram_paired_user_id


async def _complete_text(user_text: str) -> str:
    """Send a one-shot completion through the native routing engine."""
    from config.routing import RoutingManager
    from providers.registry import ProviderRegistry

    from .chat_convert import build_chat_payload
    from .routing import resolve_route
    from .schemas import AnthropicMessage, MessagesRequest
    from .upstream import UpstreamClient

    routing = RoutingManager().get()
    registry = ProviderRegistry()
    target = resolve_route("cosplay-default", routing, registry)

    request = MessagesRequest(
        model="cosplay-default",
        max_tokens=1024,
        messages=[AnthropicMessage(role="user", content=user_text)],
    )
    client = UpstreamClient(target)
    body = build_chat_payload(request, target)
    body["model"] = target.model
    body["stream"] = False
    data = await client.chat(body)
    choice = (data.get("choices") or [{}])[0]
    return str((choice.get("message") or {}).get("content") or "")


async def _on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_paired(update):
        return
    user_text = (update.message.text or "").strip()
    if not user_text:
        return
    try:
        reply = await _complete_text(user_text)
    except Exception as exc:
        reply = f"Error: {type(exc).__name__}"
    await update.message.reply_text(reply)


async def _on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_paired(update):
        return
    remote = RemoteManager().get()
    if not remote.allow_voice:
        await update.message.reply_text("Voice notes are disabled.")
        return

    voice = update.message.voice
    if voice is None:
        return
    audio = await voice.get_file()
    raw = await audio.download_as_bytearray()
    text = transcribe(bytes(raw), filename=f"voice_{update.message.message_id}.ogg")
    if not text:
        await update.message.reply_text("Sorry, I could not transcribe that voice note.")
        return
    try:
        reply = await _complete_text(str(text))
    except Exception as exc:
        reply = f"Error: {type(exc).__name__}"
    await update.message.reply_text(reply)


async def run_telegram_bot() -> None:
    """Initialize and start polling. Keeps running while the daemon loop is alive."""
    remote = RemoteManager().get()
    if not remote.enable_telegram or not remote.telegram_token:
        return

    application = Application.builder().token(remote.telegram_token).build()
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text)
    )
    application.add_handler(MessageHandler(filters.VOICE, _on_voice))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Park forever; the daemon loop cancels this task on shutdown.
    while True:
        await asyncio.sleep(3600.0)
