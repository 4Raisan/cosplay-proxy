"""Cosplay — All-in-One CLI Launcher (cclaude).

When invoked:
1. Checks if Cosplay server (FastAPI on http://127.0.0.1:8082) is running.
2. If not running, launches 'python cosplay.py --no-open' as a background server process.
3. Opens http://127.0.0.1:8082 in the default web browser.
4. Launches Claude Code CLI connected to Cosplay.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


def is_server_running(url: str) -> bool:
    try:
        req = urllib.request.Request(f"{url}/api/runtime")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_claude_settings(env: dict) -> None:
    """Merge Cosplay proxy env into ~/.claude/settings.json so any `claude`
    launch (not only via cclaude.cmd) connects to the gateway with model
    discovery enabled. User settings are preserved."""
    try:
        settings_file = Path.home() / ".claude" / "settings.json"
        data = {}
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
        data.setdefault("env", {})
        for key in (
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_MODEL",
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
            "NO_PROXY",
        ):
            if key in env:
                data["env"][key] = env[key]
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print(f"[Cosplay] Warning: could not update ~/.claude/settings.json ({exc})")


def main() -> None:
    cosplay_dir = Path(__file__).parent.resolve()
    runtime_file = Path.home() / ".cosplay" / "runtime.json"
    port = 8082
    token = "cosplay-secret-token"

    if runtime_file.exists():
        try:
            with open(runtime_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                port = data.get("server_port", 8082)
                token = data.get("api_auth_token", "cosplay-secret-token")
        except Exception:
            pass

    server_url = f"http://127.0.0.1:{port}"

    # Step 1: Ensure Cosplay server is running
    if not is_server_running(server_url):
        print(f"[Cosplay] Server not running. Starting server on {server_url}...")
        cosplay_script = cosplay_dir / "cosplay.py"
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        server_log = Path.home() / ".cosplay" / "server.log"
        log_handle = None
        try:
            server_log.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(server_log, "ab")
        except Exception:
            pass
        subprocess.Popen(
            [sys.executable, str(cosplay_script), "--no-open"],
            cwd=str(cosplay_dir),
            creationflags=creationflags,
            stdout=log_handle or subprocess.DEVNULL,
            stderr=log_handle or subprocess.DEVNULL,
        )
        print(f"[Cosplay] Server log: {server_log}")

        # Wait up to 5 seconds for server to start
        sys.stdout.write(f"[Cosplay] Waiting for server to initialize...  ")
        sys.stdout.flush()
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        running = False
        for i in range(50):
            sys.stdout.write(f"\b{spinner[i % len(spinner)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            if is_server_running(server_url):
                running = True
                break
        if running:
            sys.stdout.write("\b✓\n")
        else:
            sys.stdout.write("\b✗\n")
            print(f"[Cosplay] ERROR: server did not start on {server_url}.")
            print(f"[Cosplay] Check {Path.home() / '.cosplay' / 'server.log'} for details, then run `cclaude` again.")

    # Step 2: Open Admin Web UI in default browser
    print(f"[Cosplay] Admin Web UI: {server_url}")
    try:
        webbrowser.open(server_url)
    except Exception:
        pass

    # Step 3: Configure proxy environment and launch Claude Code CLI
    env = os.environ.copy()
    
    # Force inject portable Node/Python paths into this session just in case
    # the Windows Sandbox / Explorer hasn't reloaded the registry PATH yet.
    local_app_data = Path(env.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    node_dir = str(local_app_data / "CosplayNode")
    py_dir = str(local_app_data / "CosplayPython")
    py_scripts = str(local_app_data / "CosplayPython" / "Scripts")
    
    current_path = env.get("PATH", "")
    paths_to_add = [d for d in [node_dir, py_dir, py_scripts] if os.path.exists(d) and d not in current_path]
    if paths_to_add:
        env["PATH"] = os.pathsep.join(paths_to_add) + os.pathsep + current_path

    env.pop("ANTHROPIC_API_KEY", None)
    env["ANTHROPIC_BASE_URL"] = server_url
    env["ANTHROPIC_AUTH_TOKEN"] = token
    env.setdefault("ANTHROPIC_MODEL", "claude-cosplay-default")
    env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = "190000"
    env["DISABLE_AUTOUPDATER"] = "1"
    env["DISABLE_FEEDBACK_COMMAND"] = "1"
    env["DISABLE_ERROR_REPORTING"] = "1"
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"

    ensure_claude_settings(env)

    print(f"[Cosplay] Launching Claude Code CLI...")
    print()

    if os.environ.get("CCLDUDE_NO_CLAUDE") == "1":
        print(f"[Cosplay] Proxy ready at {server_url} (no API key yet).")
        print(f"[Cosplay] Open {server_url}, add a provider API key,")
        print("[Cosplay] then run `cclaude` to start Claude Code.")
        return

    cmd = ["npx", "-y", "@anthropic-ai/claude-code"] + sys.argv[1:]
    try:
        proc = subprocess.run(cmd, env=env, shell=True)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
