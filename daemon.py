"""Cosplay — Background daemon manager.

Runs the Telegram bot loop (config-driven, disabled by default). Replaces the
old FCC-based daemon with a fully native implementation.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from config.remote import RemoteManager


_daemon_thread: Optional[threading.Thread] = None
_daemon_loop: Optional[asyncio.AbstractEventLoop] = None
_daemon_task: Optional[asyncio.Task] = None
_daemon_status: str = "Stopped"  # Stopped, Starting, Running, Stopping, Error
_daemon_should_run: bool = False


def get_daemon_status() -> str:
    """Return the current lifecycle state of the daemon."""
    return _daemon_status


def start_daemon() -> None:
    """Start the Telegram daemon if enabled by configuration."""
    global _daemon_thread, _daemon_loop, _daemon_status, _daemon_should_run

    remote = RemoteManager().get()
    if not remote.enable_telegram or not remote.telegram_token:
        _daemon_status = "Stopped"
        return

    _daemon_should_run = True

    if _daemon_thread is not None and _daemon_thread.is_alive():
        return

    _daemon_status = "Starting"

    def run_loop() -> None:
        global _daemon_loop, _daemon_task, _daemon_status
        _daemon_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_daemon_loop)

        async def _main() -> None:
            global _daemon_status, _daemon_should_run
            backoff = 2
            while _daemon_should_run:
                _daemon_status = "Starting"
                try:
                    from proxy.telegram import run_telegram_bot

                    _daemon_status = "Running"
                    await run_telegram_bot()
                    backoff = 2
                    while _daemon_should_run:
                        await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    if not _daemon_should_run:
                        break
                    _daemon_status = "Error"
                    print(
                        f"[Daemon] Unexpected error ({type(exc).__name__}). "
                        f"Retrying in {backoff} seconds..."
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(60, backoff * 2)

            _daemon_status = "Stopped"

        _daemon_task = _daemon_loop.create_task(_main())
        try:
            _daemon_loop.run_until_complete(_daemon_task)
        finally:
            _daemon_loop.close()

    _daemon_thread = threading.Thread(target=run_loop, daemon=True)
    _daemon_thread.start()


def stop_daemon() -> None:
    """Gracefully stop the background daemon."""
    global _daemon_thread, _daemon_loop, _daemon_task, _daemon_status, _daemon_should_run

    _daemon_should_run = False
    _daemon_status = "Stopping"

    if _daemon_loop and _daemon_task:
        _daemon_loop.call_soon_threadsafe(_daemon_task.cancel)

    if _daemon_thread and _daemon_thread.is_alive():
        _daemon_thread.join(timeout=15.0)

    _daemon_thread = None
    _daemon_loop = None
    _daemon_task = None
    _daemon_status = "Stopped"


def restart_daemon() -> None:
    """Restart the background daemon to apply new settings."""
    stop_daemon()
    start_daemon()
