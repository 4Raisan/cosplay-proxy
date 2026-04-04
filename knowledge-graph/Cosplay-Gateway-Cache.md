# Cosplay — Claude Code Gateway Cache

`proxy/gateway_cache.py` keeps Claude Code's `/model` picker in sync with routing.

- Claude Code reads `GET /v1/models` once at startup and caches it in `<claude>/cache/gateway-models.json`; the picker reads that cache.
- `sync_gateway_cache()` writes the exact schema (baseUrl `http://127.0.0.1:8082`, the 5 `claude-cosplay-*` ids from [[Cosplay-Gateway-Model-IDs]]) so an Admin UI routing change shows up without a `claude` restart.
- Best-effort: never blanks an existing cache when the model list is empty; failures swallowed.
- Seed runs in `server.py` lifespan.

#cosplay #cache
