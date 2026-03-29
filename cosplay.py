"""Cosplay — CLI launcher.

Usage:
    python cosplay.py
    python cosplay.py --port 8088
    python cosplay.py --no-open
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Cosplay — AI Provider Proxy")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: from settings or 8082)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open browser automatically",
    )
    args = parser.parse_args()

    from config.settings import RuntimeSettingsManager
    runtime_settings = RuntimeSettingsManager().get()

    host = args.host if args.host != "127.0.0.1" else runtime_settings.server_host
    port = args.port if args.port is not None else runtime_settings.server_port

    url = f"http://{host}:{port}"

    print()
    print("  ╭─────────────────────────────────╮")
    print("  │          C O S P L A Y          │")
    print("  │    AI Provider Management       │")
    print("  ╰─────────────────────────────────╯")
    print()
    print(f"  Admin UI: {url}")
    print()

    # Open browser after a short delay
    if not args.no_open:
        def _open_browser():
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
