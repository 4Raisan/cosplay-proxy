# Cosplay — Overview

Cosplay is an AI Provider Management Proxy + web admin UI (v1.0.1). It sits in front of one or more LLM providers (Anthropic, OpenAI-compatible, Gemini, Local/Ollama) and exposes an Anthropic-compatible API for coding agents.

- Built on FastAPI ([[Cosplay-Architecture]]).
- Persists all state as atomic JSON in `~/.cosplay` ([[Cosplay-Config-Storage]]).
- Primary client is Claude Code via `cclaude.py` ([[Cosplay-FCC-Launcher]]); also usable by [[Cosplay-OpenCode-Integration]].
- Originally described as an "orchestration layer for Free Claude Code (FCC)".
- Server listens by default on `http://127.0.0.1:8082` ([[Cosplay-Runtime-Settings]]).

#cosplay #overview
