# Cosplay — Model Discovery

Discovers available models per API type, writing results into [[Cosplay-Provider-Registry]].

- HTTP providers: `GET /models` or `/v1/models`; Ollama fallback `GET /api/tags`.
- Anthropic: a hardcoded allowlist (claude-sonnet-4, opus-4, 3.7/3.5/3.x) — no public `/models` endpoint.
- Detects `supports_thinking` via id keywords (`thinking` / `reason` / `r1`).
- Triggered from the admin UI "Check Working Models" button ([[Cosplay-Web-UI]]).

#cosplay #discovery
