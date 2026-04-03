# Cosplay — Anthropic Endpoints

Native Anthropic-compatible surface, all under [[Cosplay-Proxy-Layer]] and requiring [[Cosplay-Auth-Token]]:

- `POST /v1/messages` — streams Anthropic SSE (and JSON); supports forced web-server tool responses.
- `POST /v1/messages/count_tokens` — token estimate.
- `GET /v1/models` — exposes the logical gateway model IDs ([[Cosplay-Gateway-Model-IDs]]).
- `POST /v1/responses` — Responses API surface.

#cosplay #endpoints
