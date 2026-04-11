# Cosplay — Telegram Daemon

Optional background bridge, disabled by default. A native reimplementation that replaces the old FCC-based daemon.

- Started in `server.py` lifespan only if `remote.enable_telegram` and a token are set ([[Cosplay-Config-Storage]]).
- Runs `proxy.telegram.run_telegram_bot` in a daemon thread with exponential backoff.
- Lets a paired Telegram user issue commands to the workspace remotely.
- Distinct from the Hermes Telegram bot.

#cosplay #telegram
