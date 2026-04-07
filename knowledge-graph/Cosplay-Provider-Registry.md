# Cosplay — Provider Registry

Singleton store of providers + cached model lists, backed by `~/.cosplay/providers.json` ([[Cosplay-Config-Storage]]).

- Atomic write (temp file -> rename) to avoid corruption.
- Each provider record: `id`, `name`, `api_type` (anthropic / openai_compatible / gemini / local), `base_url`, `api_key`, `auth_kind`, `enabled`, `connection_status`.
- `list_providers()` returns only enabled providers; consumed by [[Cosplay-Model-Routing]] and [[Cosplay-Upstream-Client]].
- Default seeded provider is NVIDIA NIM ([[Cosplay-NIM-Provider]]).
- Model cache populated by [[Cosplay-Model-Discovery]].

#cosplay #providers
