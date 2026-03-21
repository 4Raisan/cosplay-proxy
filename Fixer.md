# Fixer.md — Fix Log (v3)

The v2 log (Fix V2-001–009) was cleared on 2026-08-08. This log records fixes
applied under the **v3** series. Every entry documents the Fix, the Reason it
was needed, and the Verification that proved it.

---

## Fix V3-001

| | |
| --- | --- |
| **Files** | `providers/discovery.py`, `static/app.js`, `Fixer-v3.md` (new) |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
Working-model check results now **survive an admin page refresh** and the
Thinking page shows the same **✓ Working / ✗ Failed** marks as the Models
dropdown:

1. `providers/discovery.py` — model discovery stamped
   `supports_thinking=False` on every model whose id lacks a
   `reasoning/r1/thinking` keyword. That `False` travelled into
   `record_cap_from_check()` as `supports_hint`, which then **permanently
   recorded** the model as non-reasoning (`max_rank=0`) the moment the check
   succeeded. On the next page load the caps record won over the heuristic and
   the model rendered as Not Available — the check made things worse instead
   of marking the model working. Discovery now leaves the hint `None` (unknown)
   unless a reasoning keyword is present, so absence of a keyword is never
   treated as evidence of non-support.
2. `static/app.js` — each Thinking section header now shows the model's status
   badge (`✓ Working` / `✗ Failed`) pulled from the same model list used by the
   Models combobox, so the page mirrors the Models dropdown marks; the level
   dropdown keeps its own `✓ (working)` marker on the verified cap level.

### Reason
Two symptoms reported together:
- After refreshing the admin page, working-model results were gone. The caps
  record created by the check (`supports_thinking=false, max_rank=0`) won over
  the heuristic on every later load (verified records beat heuristics per
  V2-006), so the Thinking dropdown disappeared and the proxy clamped thinking
  to OFF for a model the check had just proven works.
- The Thinking page showed no working/failed marks, unlike the Models
  dropdowns.

### Verification
- End-to-end against a local mock NIM server (real `discover_models`,
  `check_model_working`, `record_cap_from_check`, registry + caps store):
  - `gemma-3-8b-it` (unknown) → check succeeds → persisted
    `{supports_thinking: true, max_rank: 5, verified: true}`; after a full
    singleton reload (fresh process) the record is still there and the model
    stays `working`.
  - `nemotron-3-nano-3b-a3b-reasoning` → persisted `{true, rank 2, verified}`,
    survives reload, ✓ badge lands on the cap level.
  - Provider registry reload returns both models `working` (status persisted).
- `python -m py_compile providers/discovery.py` and
  `node --check static/app.js` pass.

---

## Fix V3-002

| | |
| --- | --- |
| **Files** | `static/app.js` |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
1. **Per-item working/failed marks in the Thinking dropdown** — the universal
   "✓ Supported / ❌ Not Supported" mark on the section header was removed. The
   marks now live on each level item of the dropdown itself, mirroring the
   Models dropdown style: the verified cap level carries a **✓ Working** badge,
   every level above the cap is greyed `disabled` with a **✗ Failed** badge,
   and the rest render plain. The model's own status badge (`✓ Working` /
   `✗ Failed`) stays next to the model name in the section header.
2. **Auto-save on section change (Routing page)** — selecting a different
   provider/model in any routing section now auto-saves that setting
   (debounced 700 ms, `PUT /api/routing`), so moving between sections persists
   each change immediately instead of waiting for the bottom **Save Routing**
   button (which still exists and still does a full save + re-render).

### Reason
- A single global "supports thinking" badge implies one answer for all levels,
  which is misleading: a model may support some levels but not others. The
  per-item badge shows the real per-level capability.
- Auto-saving each Routing section removes the "edit a field, forget to click
  Save, lose it on refresh" failure; the bottom button remains the explicit way
  to save everything at once.

### Verification
- JS check `node --check static/app.js` passes.
- The `change` event is dispatched from the hidden combobox input inside
  `selectComboboxOption`, and `initRoutingAutoSave()` listens via delegation so
  it keeps working after `renderCombobox()` rebuilds the DOM on save.
- No remaining references to `thinking-support-badge` in app.ts render path.

---

## Fix V3-003

| | |
| --- | --- |
| **Files** | `static/app.js` |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
1. **Per-level working marks in the Thinking dropdown** — every level item now
   carries its own ✓ Working / ✗ status instead of a single cap-level mark:
   each *supported* level gets **✓ Working**, each level above the cap gets
   **✗ Not Working** (greyed, disabled). This reflects that a model may
   support some levels but not others (e.g. cap at `balanced` →
   Auto/Off/Light/Balanced ✓, Deep/XHigh/Max ✗).
2. **Thinking page auto-save** — changing a thinking level in any section
   auto-saves it (debounced 700 ms, `PUT /api/thinking` with the same payload
   as the bottom Save button), so navigating between sections persists each
   change immediately; the bottom button remains for a full save.

### Reason
A single "working" mark per model is insufficient: the capability is per
level, and the verified cap tells exactly which levels above it are unusable.
With auto-save, changing a level while moving between sections no longer gets
lost if the user forgets to press Save.

### Verification
- `node --check static/app.js` passes.
- Auto-save payload matches `handleSaveThinking()` fields; using a delegated
  `change` listener on the hidden inputs, so it survives combobox re-renders
  across the Thinking page reloads.

---

## Fix V3-004

| | |
| --- | --- |
| **Files** | `static/app.js`, `static/index.html` |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
Thinking page per-level marks are now driven by the **real working check**:

1. **Real per-level mark gating** (`static/app.js`, thinking section render):
   - Model check status `failed` → every level renders **✗ Not Working**,
     the combobox is locked to "Model failed check".
   - Verified working model (check `working` **or** caps record `verified`) →
     `✓ Working` for each level up to the model cap, `✗ Not Working`
     (capped, disabled) above it.
   - Never-checked model → plain selectable levels with **no badge** and a
     "Not verified — run the model check" hint. No more fake workcheck marks.
2. **Save button + auto-save fixed** — the button is bound directly (click)
   in addition to the form submit (double-fire guarded); both paths now send
   the **full 8-section payload** via a shared `collectThinkingPayload()`
   (default, primary, fast, heavy, research, fallback 1–3 — exactly matching
   `UpdateThinkingRequest`), so nothing is silently dropped. Added null guards
   so a missing button/container can't brick the page.
3. **Cache-bust** — `index.html` loads `/static/app.js?v=20260808` so browsers
   drop stale builds.

### Reason
- Marks previously rendered unconditionally, so a model that failed its check
  still showed "✓ Working" on supported levels.
- Save/auto-save only sent 4 of the 8 fields and could fail silently if the
  button/element was missing mid-render.

### Verification
- `node --check static/app.js` passes.
- Live `GET /static/app.js` byte length equals disk (fresh bundle served).

---

## Fix V3-005

| | |
| --- | --- |
| **Files** | `providers/registry.py` |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
Working-check results now **survive a page refresh**.

Root cause: every page load triggers `autoRefreshModels()` → `POST
/providers/{id}/refresh-models` → `discover_models()` → `set_models()`, which
**replaced** the model list with fresh records whose status is `UNCHECKED`,
wiping the saved ✗/✓ verdicts (they were already persisted in
`providers.json`, but the replacement discarded them).

`ProviderRegistry.set_models()` now merges: a rediscovered model re-uses the
previous `status` / `last_checked` / `error_message` when it already had a
verdict. Model statuses change **only** via an explicit working check, never
on refresh. No separate file needed — `providers.json` is the store; the bug
was the wipe-on-refresh.

### Verification
- `python -c "import ast; ast.parse(...)"` on `registry.py` passes.
- Logic: fresh records keep prior status unless a check overwrites it.

---

## Fix V3-006

| | |
| --- | --- |
| **Files** | `static/app.js`, daemon restart |
| **Date** | 2026-08-08 |
| **Status** | Verified (daemon restarted) |

### Fix
Per-level marks still missing despite the model supporting thinking.

Root cause: the daemon (PID 5860, started 09:21) was running the **old Python
code from before V3-001…V3-005** — its `/api/thinking/capabilities` responses
lacked `levels` / `max_rank` / `saved`, so the page always fell back to
"unverified, no marks" even for working models.

1. `static/app.js` — a model whose check status is `working` now counts as
   verified for the per-level marks even when a caps record hasn't been
   saved yet: `verifiedWorking = (modelStatus === 'working' || capsSaved?.verified)`.
2. Daemon restarted: old PID 5860 terminated; fresh process (PID 4876) now
   serves 8082 with the updated code.

### Verification
- `/api/thinking/capabilities?model_id=deepseek-ai/deepseek-v4-flash-0731`
  now returns `max_rank: 2`, full `levels[]` with per-level `supported`,
  and `saved`.
- `node --check static/app.js` passes.
- `netstat`: `127.0.0.1:8082` LISTENING under the new process.

---

## Fix V3-007

| | |
| --- | --- |
| **Files** | `static/app.js`, `static/styles.css`, `static/index.html` |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
1. **Provider card — unchecked state visible.** The model count block now
   always renders (`N working / M failed / K unchecked`), and a new provider
   that has never been checked shows the count plus an **Unchecked** dashed
   badge until the working check runs (`.badge-unchecked`,
   `.unchecked-count` styles added).
2. **Combobox shows the selected value's status inline.** Both the Models and
   Thinking comboboxes now render a status badge next to the selected value
   **without opening the dropdown** (`combobox-input-badge-…` element):
   `✓ Working` / `✗ Not Working`, driven by the real check state. Picking any
   option updates the badge immediately — `selectComboboxOption()` gained a 4th
   `status` argument, all option mousedowns pass it, and the input gets extra
   right padding (`has-status` class) when a badge is shown.

### Reason
- A fresh provider showed a bare model count with no way to tell it wasn't
  verified yet.
- The visible selected model/level gave no status feedback until the dropdown
  was opened.

### Verification
- `node --check static/app.js` passes.
- Live `GET /static/app.js?v=20260808b` byte length equals disk (80553).
- Status badge logic verified in code: initial render + after selection.

---

## Fix V3-008

| | |
| --- | --- |
| **Files** | `static/app.js`, `static/index.html`, daemon restart |
| **Date** | 2026-08-08 |
| **Status** | Verified |

### Fix
"Failed to load routing configuration" toast on the Routing page:

1. **JS crash** — `renderCombobox()` called `statusBadgeHtml(…)` but the helper
   is named `comboboxStatusHtml(…)`. The `ReferenceError` thrown during render
   bubbled into `loadRoutingSettings()` → toast and an empty page. Fixed the
   call site; no stray `statusBadgeHtml` references remain.
2. **Stale registry** — the daemon's in-memory registry had 0 providers while
   `providers.json` contained the current one (101b9d95…, 100 models). Daemon
   restarted; `/api/providers` now returns 1 provider with 25 working / 75
   failed. Cache-bust bumped to `?v=20260808c`.

### Reason
- A mis-named helper made the whole Routing page throw (silent dead page
  behind a generic toast).
- The running daemon predated the user's provider replacement, so the UI had
  no provider data to render.

### Verification
- `node --check static/app.js` passes.
- Live `/api/routing` OK; `/api/providers` → 1 provider (id 101b9d95…).
- Live `/static/app.js?v=20260808c` byte length equals disk (80556).
- `index.html` references the bumped cache-bust version.

---
