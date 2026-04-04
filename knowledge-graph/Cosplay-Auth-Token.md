# Cosplay — Auth Token

Bearer / x-api-key authentication for all `/v1/*` proxy routes ([[Cosplay-Proxy-Layer]]).

- Token sourced from `RuntimeSettingsManager().api_auth_token` ([[Cosplay-Runtime-Settings]]).
- Compared with `hmac.compare_digest` (constant-time).
- Clients such as [[Cosplay-FCC-Launcher]] send it as `ANTHROPIC_AUTH_TOKEN`.
- If the expected token is empty, auth is disabled (dev only).

#cosplay #auth
