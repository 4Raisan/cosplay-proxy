# Cosplay — Effort / Thinking Arbitration

`proxy/effort.py` reconciles three sources into one per-request decision:

- **Admin per-slot level** ([[Cosplay-Config-Storage]] `thinking.json`): `auto | off | light | balanced | deep | xhigh | max`.
- **Client effort** — Claude Code `/effort` (`output_config.effort`) or classic thinking block.
- **Model capability** — persisted cap from [[Cosplay-Model-Caps]] when available, else id-based heuristic (NIM `reasoning`/`deepseek`/`r1` → rank 2; unknown stays permissive rank 5; anthropic → rank 5).
- `resolve_effort()` → `EffortDirective`; `apply_effort()` sets the OpenAI `reasoning_effort` knob. Precedence: admin `off` > explicit admin level > `auto` → (client effort, else provider default); rank clamped to the model cap when explicit.
- Single shared conversion point in `chat_convert.py`, used by `/v1/messages` (legacy), `/v1/responses`, and the Telegram path.

#cosplay #effort #thinking
