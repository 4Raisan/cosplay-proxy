# Cosplay — OpenCode Integration

OpenCode can use Cosplay as its Anthropic base URL (proxy on `127.0.0.1:8082`).

- `proxy/messages.py` logs each request to `Temp/opencode/last_request.json` for inspection.
- Requires `opencode.jsonc` pointed at the Cosplay base URL + auth token ([[Cosplay-Auth-Token]]).
- Currently unwired: OpenCode config is empty and routing slots are null, so requests fail with "Unknown model" ([[Cosplay-Model-Routing]]).

#cosplay #opencode
