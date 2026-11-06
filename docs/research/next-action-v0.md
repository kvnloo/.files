# Next action v0: from a push chip to a pull panel

This note points the workspace-copilot "predict next action" concept at its successor design. The full design, sources and pre-registered experiment are in the z0evals study `next-action-v0` (`studies/next-action-v0/README.md` in kvnloo/z0evals).

## The old concept (still running)

- `scripts/workspace-copilot` and `scripts/workspace_flow.py` hold the Flow engine, `os.next_context.v0`, and its PREDICT / PREPARE / SURFACE / COMMIT gates.
- The UI is the Noctalia bar chip `next-action`. `Super+Return` commits and `Super+BackSpace` dismisses.
- `scripts/workspace_rerank.py` (`rerank-v1`, local commit) adds a learned re-ranker, retrained daily.
- `config/agent-skills/workspace-copilot/SKILL.md` documents all of it.

## What 30 days of its own log say (2026-09-21 → 2026-10-21)

- 7,859 predictions, 19 ready-tier surfaces, **0 commits** and **0 accept/reject decisions** (225 suggestions all pending).
- 69% of predictions are "focus app X". Plain recency (what `Super+Tab` shows) is top-1 77% and top-3 97% on those, against the engine's 45% and 69%. Switching apps by hand is already sub-second, so a correct guess saves nothing.
- When engine confidence is at least 0.82 (the ready gate), the guess is right only 23% of the time (n=76). The gate is miscalibrated.

## What changes

1. **Pull, not push.** `Super+period` (currently unbound) shows up to 3 actions or says "nothing confident". On the phone this is a Lawnchair tile. The chip stays only for `inspect_result` (an agent finished, blocked or failed).
2. **Only actions worth predicting**, meaning ≥ 3 s or ≥ 3 inputs by hand:
   - inspect the finished session;
   - re-run the last failing command;
   - Atuin next command for this cwd;
   - open the PR or CI for the branch just pushed;
   - resume the active task;
   - mined routines.
3. **Log accept/reject/ignore/manual-equivalent/reversed-within-8s** for every invocation (`next_action.v1`). The re-ranker becomes an accept-probability model trained on those logs, calibrated, with a Cursor-style threshold of τ = 0.25.
4. **Models only after the plain-code version proves it gets used.** T0 is code and frequency. T1 is a calibrated logistic scorer. T2 is the groot Qwen3-4B or Jev in shadow, promoted only by ABAB.

## Ring gestures

| Pattern | Action |
|---|---|
| double / triple | z0live (locked) |
| quad | keyboard STT: Google voice typing via `AccessibilityService.SoftKeyboardController.switchToInputMethod`, only when a text field has focus and no call is active |
| quint | reserved for a display-only next-action peek |

Each new pattern is adopted only if the guided recordings show recall ≥ 90%, ≤ 2% decoded as a lower count, and ≤ 0.5 false fires per hour. A long hold isn't detectable on an accelerometer-only ring.

## First experiment

One week of the desktop pull panel with T0 generators, where 1 in 5 invocations shows recency only (control). Android logs launches in shadow during that week.

Pass criteria:
- ≥ 3 invocations a day on ≥ 5 days;
- accept rate ≥ 40% and better than the recency arm;
- median time saved per accept ≥ 5 s;
- reversals ≤ 10%;
- p95 trigger-to-panel ≤ 150 ms.
