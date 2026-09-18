---
name: workspace-copilot
description: Analyze the user's sanitized Hyprland, tmux, Agent Deck, and ActivityWatch workspace context; explain what agents and windows are doing; identify context-switching or organization inefficiencies; and propose permissioned workspace changes. Use when the user asks about workspaces, windows, tmux sessions, agent fleet state, workflow habits, focus, navigation, keybind ergonomics, or workspace organization.
metadata:
  author: kvn
  version: "1.0"
---

# Workspace Copilot

Use the local `workspace-copilot` CLI as the only workspace-observation interface. It exposes sanitized aggregates from Hyprland, the personal tmux server, Agent Deck, and privacy-filtered ActivityWatch.

## Non-negotiable privacy boundary

Never inspect or request raw ActivityWatch events, window titles, pane contents, shell history rows, clipboard data, screenshots, audio, command arguments, browser URLs, or harness transcripts for this workflow. Never install input hooks or read `/dev/input`.

The approved context contains only application identity, workspace/monitor placement, project basenames, hashed paths, tmux topology, command basenames, explicit fleet session metadata, aggregate durations, semantic harness states, and prior accept/reject decisions.

Run this before relying on the data:

```sh
workspace-copilot --json doctor
```

Stop and report the failing boundary if `ok` is not `true` or `activitywatch_privacy_ok` is not `true`.

## Analyze the workspace

Retrieve current sanitized context:

```sh
workspace-copilot --json context
```

Explain conclusions as:

1. **Observation** — only fields present in the output.
2. **Inference** — a clearly labeled interpretation.
3. **Recommendation** — a concrete, reversible improvement.
4. **Evidence** — counts, durations, session states, or repeated transitions.

Do not infer an agent's task from its pane output. Prefer the Agent Deck title, group, tool, state, and project basename. If those are insufficient, say so and ask the user to name or group the session rather than inspecting private content.

## Generate recommendations

Refresh deterministic suggestions:

```sh
workspace-copilot --json suggest
workspace-copilot --json suggestions
```

Present every proposed mutation with its suggestion ID, evidence, exact allowlisted action, and undo availability. Advisory suggestions have no executable action.

## Decision and execution protocol

A recommendation, acceptance, application, and undo are distinct transitions.

- Never treat discussion, interest, or a request for explanation as acceptance.
- Record acceptance only after the user explicitly accepts a suggestion ID.
- Record rejection and the user's reason when explicitly rejected.
- Never apply an accepted suggestion until the user separately requests application, unless the same message unmistakably says both accept and apply.
- Never construct an arbitrary shell command as a substitute for the allowlisted apply operation.

Record a decision:

```sh
workspace-copilot --json decide <id> accept --note '<brief reason>'
workspace-copilot --json decide <id> reject --note '<brief reason>'
```

Apply only an accepted suggestion:

```sh
workspace-copilot --json apply <id>
```

Undo only when requested:

```sh
workspace-copilot --json undo <id>
```

After apply or undo, rerun `workspace-copilot --json context` and verify the observable state transition.

## Preference learning

Treat stored preference confidence as ranking evidence, not authority. Repeated acceptance may increase recommendation priority, but must never grant automatic execution permission. Rejections constrain future recommendations; explain any later proposal that appears to conflict with a recorded rejection.

## Flow predictor (os.next_context.v0)

Shadow next-context prediction runs on every semantic context change (not the
5-minute suggestion loop). Schema **v5**.

Four separate gates (never one confidence knob):

| Gate | Policy |
|---|---|
| **PREDICT** | Always. <1ms. Training data. |
| **PREPARE** | Often (`p≥0.28`). Discardable, no side effects. |
| **SURFACE** | Rarely (`p≥0.82` + margin/entropy). 10% withhold arm. |
| **COMMIT** | Explicit only (`commit-next` / Super+Space). |

Multi-horizon labels (500ms / 2s / 10s / 60s): if nothing relevant happens,
`actual_family=noop`. Canonical receipt `flow_prediction.v1` dual-writes to
`~/.z0int/receipts/flow_predictions.jsonl`.

Invariant: **never steal focus**. Never auto-run consequential actions.
Correct prediction ≠ useful intervention (keyboard-fast → silence).

```sh
workspace-copilot --json predict          # force shadow prediction now
workspace-copilot --json next-action      # single global surface (or idle)
workspace-copilot --json commit-next      # reversible navigation only
workspace-copilot --json dismiss-next     # suppress until evidence changes
workspace-copilot --json shadow-stats     # top1/topk/noop/horizons/gates
workspace-copilot --json export-flow      # JSONL → ~/.z0int/episodes
```

z0int vault + skeptic (no promote):

```sh
z0int os-context stats
z0int os-context import
z0int os-context skeptic --horizon-ms 2000
```

Operator families (second head, coarse): `inspect_result`, `run_test`,
`open_context`, `delegate`, `retrieve`, `resume_previous`, `noop`.

## Routine Suggestion Miner (P3)

Mine 1–4 step semantic sequences from the episode stream. Reuses the existing
suggestions / decide / apply / undo substrate — no second automation framework.

```sh
workspace-copilot --json record-action --family switch_app --target kitty --source keyboard
workspace-copilot --json mine-routines --suggest
workspace-copilot --json routine-stats
workspace-copilot --json suggestions --status pending   # kind=routine-shortcut
# after explicit accept:
workspace-copilot --json decide <id> accept
workspace-copilot --json apply <id>     # installs Super+Alt bind → run-routine
workspace-copilot --json undo <id>      # removes exactly that bind
```

Evidence is observed facts only (count, sessions, median duration, same-sequence
ratio, existing shortcut, reversibility, source mix). No fake seconds-saved.

Modality sources: `keyboard|mouse|voice|flow|agent|unknown` — never raw keys.
Keyboard-optimal single actions with an existing chord are suppressed.

## Automation utility receipts (P3d)

Acceptance is not proof of value. Track lifecycle:

```text
suggested → accepted → installed → invoked → completed
                 ↘ rejected
installed → opportunity + manual_equivalent (sequence still done by hand)
installed → unused_after_N_opportunities (default N=12, zero invokes)
invoked → immediate_reversal (user leaves target within ~8s)
```

```sh
workspace-copilot --json utility-stats
workspace-copilot --json export-flow   # + os_automation_receipts.jsonl
```

Generated Hypr binds call `run-routine`, which records `source=keyboard` semantic
actions and `invoked`/`completed` receipts — no raw keylogging.
Do not accept one-step focus shortcuts merely because the miner found them.
