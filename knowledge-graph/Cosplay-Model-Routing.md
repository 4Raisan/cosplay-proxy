# Cosplay — Model Routing

Resolves a client model id to a concrete `(provider, model)` pair via [[Cosplay-Provider-Registry]].

- Gateway IDs map to slots (see [[Cosplay-Gateway-Model-IDs]]): `cosplay-default`->default, `cosplay-sonnet-coding`->primary_coding, `cosplay-haiku-tasks`->fast_tasks, `cosplay-opus-analysis`->heavy_analysis, `cosplay-fable-research`->research.
- Also accepts Anthropic aliases (`sonnet`, `opus`, `haiku`, `fable`) and direct `provider:model` refs.
- Slots stored in `~/.cosplay/routing.json` ([[Cosplay-Config-Storage]]); `effective_default_model` falls back to primary_coding.
- If every slot is null -> `NotFoundError: Unknown model` (the current broken state with no configured provider).
- Fallback chain (`fallback_1..3`) tried in order after the primary target.

#cosplay #routing
