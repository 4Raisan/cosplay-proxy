"""Cosplay proxy — thinking / effort arbitration.

Reconciles three sources into a single per-request decision:

- **Admin per-slot level** (`~/.cosplay/thinking.json`): ``auto | off | light |
  balanced | deep | xhigh | max``.
- **Client effort** (Claude Code `/effort`, delivered as
  ``output_config.effort``, or the classic ``thinking`` block).
- **Model capability** — the target model's reasoning cap: a persisted caps
  record (see ``config/model_caps.py``) when available, else a conservative
  id-based heuristic (NIM ``reasoning``/``deepseek``/``r1`` ids are pinned to
  rank 2; unknown models stay permissive; anthropic ids get rank 5).

``resolve_effort()`` produces a single ``EffortDirective``; ``apply_effort()``
applies it to an OpenAI chat payload as the ``reasoning_effort`` knob. The one
conversion point in ``proxy/chat_convert.py`` is shared by ``/v1/messages``,
``/v1/responses`` and the Telegram path.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.model_caps import ModelCapsManager
from config.thinking import ThinkingManager

# Admin thinking levels → reasoning rank (None = follow client/provider).
ADMIN_RANK: dict[str, int | None] = {
    "auto": None,
    "off": 0,
    "light": 1,
    "balanced": 2,
    "deep": 3,
    "xhigh": 4,
    "max": 5,
}

VALID_ADMIN_LEVELS = frozenset(ADMIN_RANK)

# Claude Code /effort values → reasoning rank.
CLIENT_RANK: dict[str, int] = {
    "low": 1,
    "mid": 2,
    "high": 3,
    "xhigh": 4,
    "max": 5,
}

# Reasoning rank → OpenAI reasoning_effort knob (0 = off, None = provider default).
RANK_KNOB: dict[int, str] = {
    1: "low",
    2: "medium",
    3: "high",
    4: "high",
    5: "high",
}

# Admin slots in thinking.json, mapped 1:1 to routing slot names.
_THINKING_ATTRS = {
    "default": "default_thinking",
    "primary_coding": "primary_coding_thinking",
    "fast_tasks": "fast_tasks_thinking",
    "heavy_analysis": "heavy_analysis_thinking",
    "research": "research_thinking",
}

# Model ids that embed a reasoning family marker → conservative cap.
_REASONING_MARKERS = ("reasoning", "deepseek", "-r1", "/r1")


@dataclass
class EffortDirective:
    """The resolved reasoning decision for one request."""

    rank: int | None = None
    explicit: bool = False
    clamped_to: int | None = None
    source: str = "auto"
    max_rank: int | None = None


def _heuristic_rank(model_id: str) -> int:
    low = (model_id or "").lower()
    if any(marker in low for marker in _REASONING_MARKERS):
        return 2
    return 5


def _ability_for(target: object) -> tuple[int, bool, bool]:
    """Return (max_rank, explicit_cap, supports_thinking) for a target.

    A saved record wins over the heuristic. A permissive verified record
    (rank 5, source used/verified) is treated as *not* explicit so the
    reasoning_effort knob is only sent to models with a known cap.
    """
    provider_id = getattr(target, "provider_id", "")
    model = getattr(target, "model", "")
    saved = ModelCapsManager().get(provider_id, model)
    if saved:
        supports = bool(saved.get("supports_thinking", True))
        max_rank = int(saved.get("max_rank", 5))
        source = saved.get("source", "used")
        explicit = supports and (source == "admin" or max_rank < 5)
        return max_rank, explicit, supports

    max_rank = _heuristic_rank(model)
    low = model.lower()
    supports = True
    explicit = False
    if any(marker in low for marker in _REASONING_MARKERS):
        explicit = True
    return max_rank, explicit, supports


def resolve_effort(
    admin_level: str | None,
    client_effort: str | None,
    target: object,
) -> EffortDirective:
    """Arbitrate admin level, client effort and model cap into a directive.

    Precedence: admin ``off`` > explicit admin level > ``auto`` → (client
    effort, else provider default). The final rank is clamped to the model's
    cap when the cap is explicit.
    """
    max_rank, explicit_cap, supports = _ability_for(target)
    if not supports:
        return EffortDirective(rank=0, explicit=True, source="off", max_rank=max_rank)

    admin = (admin_level or "auto").strip().lower()
    if admin not in VALID_ADMIN_LEVELS:
        admin = "auto"

    if admin == "off":
        return EffortDirective(rank=0, explicit=True, source="off", max_rank=max_rank)

    if admin != "auto":
        rank = ADMIN_RANK.get(admin)  # int
    else:
        client = (client_effort or "").strip().lower()
        rank = CLIENT_RANK.get(client)  # None → provider default

    directive = EffortDirective(rank=rank, max_rank=max_rank)
    directive.source = "admin" if admin != "auto" else ("client" if rank else "auto")
    if rank is None:
        directive.explicit = False
        return directive

    directive.explicit = True
    if explicit_cap and max_rank is not None and rank > max_rank:
        directive.clamped_to = max_rank
        directive.rank = max_rank
    return directive


def apply_effort(payload: dict, directive: EffortDirective) -> dict:
    """Apply a directive to an OpenAI chat payload (in place, returns it).

    rank None → untouched (provider default); rank 0 → knob removed;
    otherwise `reasoning_effort` is set to the mapped knob value.
    """
    if directive is None:
        return payload
    if directive.rank is None:
        return payload
    if directive.rank == 0:
        payload.pop("reasoning_effort", None)
        return payload
    knob = RANK_KNOB.get(directive.rank, "medium")
    payload["reasoning_effort"] = knob
    return payload


def admin_level_for_slot(slot: str | None) -> str:
    """Fetch the configured admin thinking level for a routing slot."""
    attr = _THINKING_ATTRS.get(slot or "default")
    if not attr:
        return "auto"
    try:
        return str(getattr(ThinkingManager().get(), attr, "auto") or "auto")
    except Exception:
        return "auto"


def record_cap_from_check(
    provider_id: str,
    model_id: str,
    supports_hint: bool | None,
) -> dict | None:
    """Persist the capability learned by the working-model check.

    ``supports_hint=False`` (metadata says the model cannot reason) → recorded
    as rank 0. Anything else (True or unknown) → the permissive baseline with
    the id-heuristic cap, so a model that worked is never demoted to
    "not available" by an unverified heuristic. Admin overrides are kept.
    """
    manager = ModelCapsManager()
    existing = manager.get(provider_id, model_id)
    if existing and existing.get("source") == "admin":
        return None

    if supports_hint is False:
        return manager.mark_model_used(
            provider_id, model_id, supports_thinking=False, max_rank=0,
            source="verified",
        )
    max_rank = _heuristic_rank(model_id)
    return manager.mark_model_used(
        provider_id, model_id, supports_thinking=True, max_rank=max_rank,
        source="verified",
    )
