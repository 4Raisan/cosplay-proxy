# Cosplay — Provider API Types

Cosplay supports four provider API types (`api_type` field in [[Cosplay-Provider-Registry]]):

1. **OpenAI Compatible** — `/v1/chat/completions`-style (NIM, Groq, OpenRouter, …).
2. **Anthropic** — Messages API (hardcoded allowlist in discovery).
3. **Gemini** — Google Gemini endpoint.
4. **Local** — vLLM / Ollama / LM Studio on your own machine.

A fresh install starts with **no provider**; you add one via the Admin UI (Providers > Add Provider). Keys live only in `~/.cosplay/providers.json`.

#cosplay #providers #types
