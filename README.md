# Cosplay + Claude Code

A **self-contained, fully-local AI proxy + admin UI + Claude Code launcher** for Windows.

You install it on any (even clean) Windows PC, add one provider API key (any
OpenAI-compatible endpoint — NVIDIA NIM, Groq, local vLLM, …), and `cclaude`
gives you a working Claude Code CLI that routes through a local FastAPI proxy to
your provider's models — no Anthropic account, no cloud round-trip other than
the model calls.

---

## 1. What it is

Three cooperating parts, all running on `127.0.0.1`:

1. **Setup** (`Cosplay-Full-Setup.exe` / `Cosplay-Setup.cmd` → `setup.ps1` + `cclaude_setup.py`)
   Installs whatever a clean PC is missing (portable Python 3.11 / Node 22 / global
   Claude Code npm package / Python deps), writes `~/.cosplay` config, starts the server,
   and launches Claude Code.
2. **Server** (`cosplay.py` → uvicorn → `server.py` FastAPI app)
   Serves the Admin Web UI at `http://127.0.0.1:8082` and exposes two kinds of endpoints:
   - Admin/management routes (`/api/...`) — providers, routing, thinking, voice, remote, diagnostics.
   - **OpenAI-compatible proxy routes** (`/v1/chat/completions`, `/v1/models`, etc.) that
     Claude Code talks to.
3. **Launcher** (`cclaude` → `cclaude.cmd` → `cclaude.py`)
   Ensures the server is running, opens the dashboard, sets the proxy env vars, then runs
   the Claude Code CLI pointed at the local server.

### Runtime flow (one command)

```
cclaude
  └─ cclaude.cmd  (adds portable python/node to PATH for this process)
       └─ cclaude.py
            ├─ server already on 127.0.0.1:8082 ? skip : start `python cosplay.py --no-open`
            ├─ open browser → http://127.0.0.1:8082  (Admin UI)
            └─ launch `npx -y @anthropic-ai/claude-code` with:
                 ANTHROPIC_BASE_URL=http://127.0.0.1:8082
                 ANTHROPIC_AUTH_TOKEN=<token from ~/.cosplay/runtime.json>
                 ANTHROPIC_MODEL=cosplay-default
                 (NO_PROXY=127.0.0.1,localhost,::1)
                 ├─ Claude Code → POST /v1/chat/completions (OpenAI format)
                 └─ proxy/ → routes request to the configured provider per ~/.cosplay/routing.json
```

The proxy endpoint is **OpenAI-compatible**: `proxy/messages.py` converts Claude Code's
Messages request into the upstream body, `proxy/routing.py` picks the model slot, and
`proxy/upstream.py` talks to the provider's base URL (e.g. `https://integrate.api.nvidia.com/v1`)
with the stored key.

---

## 2. File structure

### Root (runtime + tooling)

| File | Role |
| --- | --- |
| `Cosplay-Full-Setup.exe` | **Shippable SFX (EXE)** with the Cosplay logo as its icon. Double-click to install. |
| `Cosplay-Setup.cmd` | **Shippable SFX** (1 file, self-contained batch). Same package as the EXE. |
| `build_sfx.ps1` | Repack both SFX files from this folder. **Run after any fix.** |
| `cclaude-setup.bat` | Thin CRLF wrapper → `setup.ps1`. |
| `setup.ps1` | **Installer** (PowerShell, the UI). Detects/installs Python, Node, Claude Code, deps; configures; starts server. |
| `uninstall.cmd` / `uninstall.ps1` | Uninstaller with 4 keep/remove prompts (Cosplay, Claude Code, Python, Node). |
| `cclaude_setup.py` | Writes `~/.cosplay` config + `cclaude.cmd` launcher + PATH entry (idempotent). |
| `cclaude.cmd` | Launcher wrapper (adds portable python/node to PATH). |
| `cclaude.py` | Launcher: start server, open UI, run Claude Code with proxy env. |
| `cosplay.py` | Server entry: bootstraps `sys.path`, parses args, runs uvicorn on `server:app`. |
| `server.py` | FastAPI app: mounts admin + proxy routers, serves `static/`. |
| `daemon.py` | Telegram daemon manager (disabled by default). |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`. These are the only boot-time deps. |
| `README.md` | This file. |
| `Fixer.md` | Fix log (V3-001…V3-008). Every fix applied to the project. |
| `LICENSE` | Project license. |
| `knowledge-graph/` | Obsidian vault: project architecture notes (the knowledge base). |

### Packages (imported as `config`, `api`, `providers`, `proxy`)

```
config/     Settings managers → JSON files in ~/.cosplay
  settings.py    runtime.json    (server_port, api_auth_token, rate limits, …)
  routing.py     routing.json    (model slot → "nim:<provider-id>:<model>")
  thinking.py    thinking.json   (reasoning/thinking flags)
  web_voice.py   web_voice.json  (voice settings)
  remote.py      remote.json     (Telegram pairing, disabled by default)
  recovery.py    config self-healing

api/        FastAPI admin routes under /api
  routes.py            providers CRUD            runtime_routes.py  runtime settings
  routing_routes.py    routing                   thinking_routes.py
  web_voice_routes.py  voice                     remote_routes.py   Telegram
  diagnostics_routes.py /api/diagnostics/...     auth.py

providers/  Provider model + discovery + validation
  registry.py          ProviderRegistry (loads providers.json)
  models.py, discovery.py, validator.py, connected_accounts.py, accounts.py

proxy/      OpenAI-compatible gateway (what Claude Code actually calls)
  auth.py        validates ANTHROPIC_AUTH_TOKEN
  messages.py    /v1/chat/completions (Messages format)
  models_api.py  /v1/models
  responses.py   /v1/responses
  routing.py     model slot resolution
  upstream.py    HTTP call to upstream provider (NIM)
  chat_convert.py, chat_sse.py, schemas.py, errors.py, rate_limit.py, forced_tools.py
  tokens.py (lazy tiktoken), web_tools.py, voice.py, telegram.py

static/     Admin UI (index.html, styles.css, app.js) — served at /
```

---

## 3. Config: `~/.cosplay/`

Created by `cclaude_setup.py` (never overwritten once present):

- `providers.json` — the provider list. A fresh install starts **empty**; add your
  provider (name, base URL, API key, API type) via the Admin UI
  (Providers > Add Provider). Four API types are supported: **OpenAI Compatible**
  (`/v1/chat/completions`-style), **Anthropic** (Messages API), **Gemini**, and
  **Local** (vLLM / Ollama / LM Studio on your own machine). Keys are stored here and
  used by the proxy only.
- `routing.json` — model slots (default / fast_tasks / heavy_analysis / research /
  fallback_1–3), each mapping to `provider_id:model_id`. Empty until you assign models.
- `thinking.json` — per-slot thinking level (default **Auto**). Priority flow: the Admin UI
  controls the level, and the model Claude Code selects is served through the gateway with
  that Admin-configured level for its slot.
- `runtime.json` — `api_auth_token` (random), `server_port` (8082), rate limits.
- `remote.json`, `thinking.json`, `web_voice.json`, `accounts.json`, `model_caps.json` —
  optional features + per-model capability records.

---

## 4. How setup works (fresh PC)

`setup.ps1` (the part inside the SFX) does, in order:

1. **Python** — detect via `py -3.xx` / `python` (`Get-PythonExe`). If a Python exists but has
   no pip, bootstrap pip (`Ensure-Pip`, get-pip.py). If none exists, install the **embeddable**
   portable Python 3.11 into `%LocalAppData%\CosplayPython` and bootstrap pip.
2. **Node.js** — need >= 22 (Claude Code EBADENGINE). Else install portable Node 22
   (`%LocalAppData%\CosplayNode`).
3. **Claude Code** — `npm i -g @anthropic-ai/claude-code@latest` (verify via `npm ls -g`).
4. **Deps** — `pip install -r requirements.txt` (verify by importing uvicorn/fastapi/…).
5. **Config** — `cclaude_setup.py` with `CCLDUDE_SETUP_NO_LAUNCH=1` → writes `~/.cosplay`,
   `cclaude.cmd`, user PATH entry.
6. **PATH** — add `%LocalAppData%\Cosplay` to user PATH (so `cclaude` works anywhere).
7. **Server** — start `cosplay.py --no-open` hidden, poll `http://127.0.0.1:8082/api/runtime`
   until 200, open the dashboard.
8. **Launch** — dashboard opens for the API key. Wait for `Press any key to run cclaude, after setup an
   API Key !`, then press a key and `cclaude` launches Claude Code directly (server is already running).

UI conventions: boxed banner `Cosplay v3.9 | Full Setup`, spinner frames
`| / - \` during every long step until `[ OK ]`, status list, and a `Congrats, Setup Complete !!!`
footer with `Admin Dashboard : http://127.0.0.1:8082`.

---

## 5. Critical gotchas (read before changing anything)

- **Portable Python is the embeddable build.** Its `python311._pth` locks `sys.path` to the
  python dir + site-packages and **ignores the script dir and `PYTHONPATH`**. Therefore every
  runnable script that imports local packages **must** add its own folder to `sys.path` first:
  `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` (see `cosplay.py`). Without
  this, `python cosplay.py` dies with `ModuleNotFoundError: No module named 'config'`.
- **`import site` in `python311._pth` must be enabled** (uncommented) or pip installs but is
  invisible (`python -m pip` → "No module named pip"). The uncomment regex must use multiline:
  `-replace '(?m)^#\s*import site', 'import site'`. A plain `'^#import site'` only matches line 1.
- **File encodings matter.**
  - `.bat` / `.cmd` / the SFX header: **CRLF**, UTF-8 **no BOM**.
  - `.py` / `.ps1` / `.json`: **LF**, UTF-8 no BOM.
- **SFX = single self-extracting file.** `Cosplay-Setup.cmd` is a batch header whose
  final line is the base64 of the whole package. Only that one file is shipped to users.
- **Harness quirk (only when automated):** a test harness that kills spawned child processes can
  make `Start-Process`-based steps report nonzero exit codes even on success. `setup.ps1` handles
  this with `-Verify` scriptblocks (e.g. re-check `npm ls -g` / import the modules / check the
  config files exist). On a real double-click run the exit codes are true.
- **Server logs go to `~/.cosplay/server.log`** (started via `cclaude.py` or `setup.ps1`).
  `setup.log` / `setup.log.err` in the install dir capture installer output.
- **`cclaude.py` must not send server output to DEVNULL** — it appends to `~/.cosplay/server.log`
  so startup errors stay diagnosable.

---

## 6. Development / debugging

Run pieces directly:

```powershell
# install deps into the active python
python -m pip install -r requirements.txt

# start the server in the foreground on a spare port (see errors live)
python cosplay.py --no-open --port 8091

# check it answers
curl http://127.0.0.1:8091/api/runtime

# run the launcher (starts server if needed, opens UI, runs claude)
cclaude
```

Logs:
- `%LocalAppData%\Cosplay\setup.log` / `setup.log.err` — installer steps.
- `~/.cosplay/server.log` — server stdout/stderr.
- `~/.cosplay/*.json` — live config (editable while the server runs; settings hot-reload).

---

## 7. Shipping a fix (the update loop)

1. Edit the source files in this folder.
2. Keep encodings right (see §5).
3. Rebuild the package:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build_sfx.ps1
   ```
4. It regenerates `Cosplay-Setup.cmd` and `Cosplay-Full-Setup.exe`.
5. Send the new `.exe` (or `.cmd`) to users / test in a clean Windows Sandbox.

**Recommended clean-room test:** run the SFX in a fresh Windows Sandbox (no Python/Node) and
confirm the steps reach the `Congrats` footer with the server returning 200 on
`http://127.0.0.1:8082/api/runtime`.

---

## 8. Uninstall

`%LocalAppData%\Cosplay\uninstall.cmd` asks 4 separate keep/remove prompts:
Cosplay, Claude Code (npm pkg + `~/.claude`), Python, Node.js. Removing Cosplay deletes
`%LocalAppData%\Cosplay`, `~/.cosplay` (API key), PATH entries, the desktop shortcut,
and self-deletes the folder.

---

## 9. License

MIT License — No-Sell Clause (see [`LICENSE`](LICENSE)): free to use, copy, modify, and
distribute, but you may not sell Cosplay or products whose main value is Cosplay. Software
is provided "as is" without warranty or liability.
