"""Cosplay — one-time setup for a fresh Windows PC.

Driven by ``cclaude-setup.bat``.  Writes ``~/.cosplay`` configuration
(runtime token + empty provider registry), creates the ``cclaude.cmd``
launcher, adds the install folder to the user PATH, then hands off to
``cclaude.py`` which starts the proxy server and launches Claude Code.

A fresh setup starts clean: no provider and no routing data are seeded.
The user adds their own provider via the Cosplay Admin UI.

Idempotent: existing config files are never overwritten.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
COSPLAY_DIR = Path.home() / ".cosplay"


def write_json(path: Path, data: dict) -> None:
    """Atomically write a JSON file (no BOM)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def ensure_config() -> None:
    COSPLAY_DIR.mkdir(parents=True, exist_ok=True)

    runtime = COSPLAY_DIR / "runtime.json"
    if not runtime.exists():
        write_json(
            runtime,
            {
                "api_auth_token": secrets.token_urlsafe(32),
                "server_port": 8082,
                "connection_timeout": 30,
                "rate_limit_requests": 1,
                "rate_limit_seconds": 3,
                "skip_title_generation": False,
            },
        )
        print("[Setup] Created runtime.json (new auth token)")
    else:
        print("[Setup] runtime.json already exists — keeping it")

    providers = COSPLAY_DIR / "providers.json"
    if not providers.exists():
        write_json(
            providers,
            {
                "providers": [],
                "models": {},
            },
        )
        print("[Setup] Created providers.json (empty — add your provider in the Admin UI)")
    else:
        print("[Setup] providers.json already exists — keeping it")



def ensure_launcher() -> None:
    """Write cclaude.cmd and add APP_DIR to the user PATH."""
    launcher = APP_DIR / "cclaude.cmd"
    with open(launcher, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(
            "@echo off\n"
            "set \"PATH=%LocalAppData%\\CosplayPython;%LocalAppData%\\CosplayPython\\Scripts;"
            "%LocalAppData%\\CosplayNode;%PATH%\"\n"
            "python \"%~dp0cclaude.py\" %*\n"
        )
    print(f"[Setup] Launcher ready: {launcher}")

    import winreg

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
    )
    try:
        current, _ = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        current = ""
    parts = [p for p in current.split(";") if p]
    if str(APP_DIR) not in parts:
        parts.insert(0, str(APP_DIR))
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$c='[DllImport(\"user32.dll\")] public static extern bool "
                    "SendMessageTimeout(IntPtr hWnd, int Msg, IntPtr wParam, "
                    "string lParam, int fuFlags, int uTimeout, out IntPtr "
                    "lpdwResult);'; $t=Add-Type -MemberDefinition $c -Name 'W32' "
                    "-PassThru; $r=[IntPtr]::Zero; "
                    "$t::SendMessageTimeout([IntPtr]0xffff, 0x1A, [IntPtr]::Zero, "
                    "'Environment', 2, 5000, [ref]$r) | Out-Null",
                ],
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
        print(f"[Setup] Added {APP_DIR} to user PATH")
    else:
        print("[Setup] Install folder already on PATH")
    key.Close()


def has_any_provider_key() -> bool:
    """True if any configured provider already has an API key."""
    providers = COSPLAY_DIR / "providers.json"
    if not providers.exists():
        return False
    try:
        data = json.loads(providers.read_text(encoding="utf-8"))
    except Exception:
        return False
    return any(p.get("api_key") for p in data.get("providers", []))


def main() -> None:
    args = sys.argv[1:]
    ensure_config()
    ensure_launcher()
    print("[Setup] Configuration complete.")
    if os.environ.get("CCLDUDE_SETUP_NO_LAUNCH") == "1":
        print("[Setup] Skipping launch (CCLDUDE_SETUP_NO_LAUNCH set).")
        print("[Setup] Run `cclaude` to start the proxy and Claude Code.")
        return

    env = os.environ.copy()
    if not has_any_provider_key():
        env["CCLDUDE_NO_CLAUDE"] = "1"
        print()
        print("[Setup] No provider configured yet.")
        print("[Setup] A browser will open the Cosplay Admin UI — add your")
        print("[Setup] provider there (Providers > Add Provider), then run:")
        print()
        print("[Setup]     cclaude")
        print()
    else:
        print()
        print("[Setup] Starting Cosplay proxy and launching Claude Code...")
        print()
    sys.exit(
        subprocess.call([sys.executable, str(APP_DIR / "cclaude.py")] + args, env=env)
    )


if __name__ == "__main__":
    main()
