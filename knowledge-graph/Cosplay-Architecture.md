# Cosplay — Architecture

Layered design (entry point `server.py` mounts routers + static, lifespan loads all managers):

- **Proxy layer** ([[Cosplay-Proxy-Layer]]) — native `/v1/messages`, `/v1/models`, `/v1/responses`.
- **Routing** ([[Cosplay-Model-Routing]]) — resolves a gateway model id to a concrete `provider:model`.
- **Provider registry** ([[Cosplay-Provider-Registry]]) — enabled providers + cached model lists.
- **Discovery** ([[Cosplay-Model-Discovery]]) — queries upstream `/models` to populate the registry.
- **Upstream client** ([[Cosplay-Upstream-Client]]) — httpx POST to `<base_url>/chat/completions`.
- **Auth** ([[Cosplay-Auth-Token]]) — bearer / x-api-key gate on all `/v1/*` routes.
- **Config managers** — runtime, routing, thinking, remote, web_voice ([[Cosplay-Config-Storage]], [[Cosplay-Runtime-Settings]]).
- **Daemon** ([[Cosplay-Telegram-Daemon]]) — optional Telegram bridge.
- **Web UI** ([[Cosplay-Web-UI]]) — static admin SPA driven by [[Cosplay-API-Routes]].

#cosplay #architecture
