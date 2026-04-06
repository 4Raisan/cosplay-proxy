# Cosplay — Model Capability Records

`config/model_caps.py` persists per-model reasoning capability in `~/.cosplay/model_caps.json`, keyed `provider:model` → `{supports_thinking, max_rank, verified, source, updated_at}`.

- Written by successful proxy requests (`mark_model_used`), by the working-model check (`record_cap_from_check`), and by admin override (`put`).
- **Admin overrides (`source=admin`) are never clobbered** by usage records.
- Fixed in V3-001/V3-004: a model that checks working is never demoted by an unverified heuristic; a `failed` check records rank 0.
- Consumed by [[Cosplay-Effort-Arbitration]] to clamp reasoning level.
- `thinking.json` per-slot level (default Auto) is the admin half; caps are the model half.

#cosplay #caps #thinking
