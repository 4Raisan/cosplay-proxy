# Cosplay — Proxy Layer

Implements the Anthropic Messages API natively so coding agents treat Cosplay as an Anthropic endpoint ([[Cosplay-Anthropic-Endpoints]]).

- Translates Anthropic messages -> OpenAI chat completions via [[Cosplay-Upstream-Client]].
- Per-provider fallback chain on failure ([[Cosplay-Model-Routing]]).
- Writes each request to `Temp/opencode/last_request.json` (used by [[Cosplay-OpenCode-Integration]]).
- All routes guarded by [[Cosplay-Auth-Token]].
- `POST /v1/messages` supports forced web-server tool responses.

#cosplay #proxy
