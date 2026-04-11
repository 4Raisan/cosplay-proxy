# Cosplay — Upstream Client

Thin async httpx client bound to one resolved [[Cosplay-Model-Routing]] target.

- POSTs to `<base_url>/chat/completions` (both stream and non-stream).
- Adds `Authorization: Bearer <api_key>` plus any custom headers from the provider.
- Timeouts taken from [[Cosplay-Runtime-Settings]].
- Translates upstream chunks into Anthropic SSE for [[Cosplay-Proxy-Layer]].
- Returns HTTP 502 on upstream error.

#cosplay #upstream
