# Cosplay — Config Storage

All persistent state is atomic JSON under `~/.cosplay/`:

- `runtime.json` — auth token, port, timeouts ([[Cosplay-Runtime-Settings]]).
- `providers.json` — providers + model cache ([[Cosplay-Provider-Registry]]).
- `routing.json` — model slots ([[Cosplay-Model-Routing]]).
- `thinking.json`, `web_voice.json`, `remote.json` (Telegram) — other managers.
- `Cosplay-cclaude-Setup.cmd` is a self-extracting installer that unpacks to `%LocalAppData%\Cosplay`.

#cosplay #config
