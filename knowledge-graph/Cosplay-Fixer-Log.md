# Cosplay — Fixer Log

`Fixer.md` records every fix in the **v3 series** (V3-001…V3-008), each with Fix / Reason / Verification.

Key corrections that changed behavior (and this graph):
- **V3-001** — working-check verdict survives refresh; discovery no longer demotes models ([[Cosplay-Model-Discovery]], [[Cosplay-Model-Caps]]).
- **V3-005** — `set_models()` merges prior status so refresh doesn't wipe ✓/✗ ([[Cosplay-Provider-Registry]]).
- **V3-006/V3-008** — stale daemon restarts so the registry/caps serve fresh data; routing-page crash fixed (misnamed `comboboxStatusHtml`).
- **V3-002..004 / V3-007** — Thinking page per-level marks, status badges, auto-save, unchecked-state visibility ([[Cosplay-Web-UI]], [[Cosplay-Effort-Arbitration]]).

License: MIT **No-Sell** clause (free use/modify/distribute, but cannot sell Cosplay or products whose main value is Cosplay).

#cosplay #fixer #license
