# Cosplay — OpenAI-Compatible Proxy

Cosplay exposes an **OpenAI-compatible** gateway that Claude Code and other agents call ([[Cosplay-FCC-Launcher]], [[Cosplay-OpenCode-Integration]]).

- `POST /v1/chat/completions` ([[Cosplay-Model-Routing]] selects the provider), `GET /v1/models` ([[Cosplay-Gateway-Model-IDs]]), `POST /v1/responses`.
- `proxy/messages.py` once translated Anthropic Messages format; the v3 line is OpenAI chat-completions with a shared effort-conversion point in `chat_convert.py` ([[Cosplay-Effort-Arbitration]]).
- All routes require [[Cosplay-Auth-Token]].
- A single `app.exception_handler(ProxyError)` returns the correct wire-protocol body (anthropic for `/v1/messages`, openai otherwise) instead of a bare 500.

#cosplay #proxy
