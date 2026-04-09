# Cosplay — Setup Flow

One-time setup chain: `cclaude-setup.bat` -> `cclaude_setup.py` -> `setup.ps1`.

- Idempotent: never overwrites existing `~/.cosplay` files ([[Cosplay-Config-Storage]]).
- Seeds `runtime.json` (token + port 8082), `providers.json` ([[Cosplay-NIM-Provider]], key read from env if present), `routing.json` (Nemotron slots).
- Creates `cclaude.cmd` launcher and adds the install dir to the user PATH.
- Hands off to [[Cosplay-FCC-Launcher]].
- `Cosplay-cclaude-Setup.cmd` is a separate self-extracting installer that drops files to `%LocalAppData%\Cosplay`.

#cosplay #setup
