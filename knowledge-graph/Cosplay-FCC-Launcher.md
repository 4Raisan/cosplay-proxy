# Cosplay — FCC / Claude Code Launcher

`cclaude.py` is the all-in-one launcher that runs Claude Code on top of Cosplay.

- Ensures the server is up (`http://127.0.0.1:port`), opens [[Cosplay-Web-UI]], then launches `npx @anthropic-ai/claude-code`.
- Injects proxy environment: `ANTHROPIC_BASE_URL`=server, `ANTHROPIC_AUTH_TOKEN`=token ([[Cosplay-Auth-Token]]), `ANTHROPIC_MODEL`=cosplay-default ([[Cosplay-Gateway-Model-IDs]]).
- `cclaude_setup.py` seeds [[Cosplay-Config-Storage]] and the user PATH ([[Cosplay-Setup-Flow]]).

#cosplay #launcher
