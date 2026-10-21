# Bend statecharts as Hapsland layers

The three z0 agent-work statecharts, drawn as CSS-3D planes in the real Hapsland
dashboard next to the `.files` architecture view (`../`):

| Plane | Machine | Upstream |
|---|---|---|
| Loop 1 · Work item | `WorkItem.astep` (12 states) | kvnloo/z0intelligence#183, `bend/work_item_fsm` |
| Loop 2 · Worker | `WorkerSupervision.step` (9 states) | kvnloo/z0intelligence#184, `bend/worker_supervision_fsm` |
| Loop 2 · Shared resources | `lstep` (lease / install lock), `pstep` + `peff` (S25) | same |

States are nodes; every arrow is a move the compiled Bend made on a sample
state. Of the 48 edges, the 38 loop edges plus one self-loop (Push) are exactly
the 39 arrows in the upstream Mermaid drawings, none missing and none extra;
the other 10 belong to the lease and S25 machines, which the drawings only
mention in a note. Badges name the law guarding the move. Play/Step sends one tape
event at a time to the compiled Bend; nothing in the browser decides a
transition.

## What it says, in plain words

**Loop 1** follows one piece of work: Proposed → Claimed (Opus or Sol only) →
Implementing → Verifying (CI, never the author, checks a receipt for that exact
commit) → Draft PR → Integrated → Deployed (the service must run exactly that
commit; now it waits in Kevin's queue) → OwnerAccepted (only Kevin) → Merged.
Blocked, Interrupted and Abandoned are the side exits.

**Loop 2** follows one delegated agent: Dispatched → Running (heartbeats) →
Completed → Integrated. Quiet too long and it Stalls, then counts as
Interrupted; a successor must resume from its log, or someone abandons it once
its background processes are reaped. Two hours with no decision makes it
Overdue, which puts it in Kevin's queue instead of letting it vanish. Next to
it: one owner per worktree (the lease) and the S25 rules (install lock, look
before you tap).

| Law | Prevents | 21 Oct reports |
|---|---|---|
| L1 merge only after owner acceptance | agents merging before Kevin saw it running | 6 PRs |
| L2 no self-approval | an agent grading or landing its own work | 5 (indeterminate: shared GitHub identity) |
| L3 receipt bound to the head | old green tests landing new code | 39 |
| L4 deployed == integrated | stale or diverged services | 6 services |
| L5 interrupted never dropped | half-done work vanishing | 13 |
| L6 free models never implement | code from a lane ruled out for code | 0 (unreachable) |
| L7 owner is a batched queue | pinging Kevin off-hours; one decision blocking others | 3 queued |
| W1 one owner per worktree | two sessions editing one checkout | 419 writes, 19 worktrees |
| W2 resume from log or decide in 2 h | blind restarts, rotting interruptions | 26 overdue + 10 blind resumes |
| W3 reap or adopt background processes | orphan servers eating groot's memory | 1 orphan alive |
| W4 heavy work off groot | builds starving the desktop | 1,695 (97 since the fleet) |
| W5 S25 installs serialized | installs over each other | 7 of 17 |
| W6 look before you tap | taps landing in the wrong app | 11 of 23 |

This is poteto's "draw a statechart, then verify it" loop with Bend in the TLA+
seat: the laws are theorems proven about the same `fsm.bend` that runs here,
and the reports replay real history through it. The guards are ROLES-v0 in
code: Opus/Sol write code, CI and Opus land work but never their own, Kevin
alone accepts and is a batched queue, and free models/Jev/SLMs never implement.

## Files and checks

- `WorkItem.bend`, `WorkerSupervision.bend`, `work-item.mmd`,
  `worker-supervision.mmd`: byte-identical copies of the upstream blobs at
  z0intelligence `b4c06ee` (checked by git blob id).
- `Runtime.bend`: imports both; `bend Runtime.bend -o Runtime.mjs` with the
  pinned **Bend 2.0.34** (sha256 `66e5faf9…`, the identity that produced the
  PROOF.bend pass receipts) emits `Runtime.generated.mjs`.
- `adapter.mjs`: JSON ⇄ Bend constructor boundary; fails closed on unknown
  tags, fields or ranges. It labels an unchanged state with its guarding law.
- `extract-tapes.py`: makes `scenarios.json` (12 tapes) from the private
  replay/supervise reports, copying only ids, times, event kinds, short SHAs
  and finding codes. Steps are tagged `report` or `what-if`.
- `replay.json`, `projection.json`, `receipt.json`: generated outcomes, edges
  and hashes.

```sh
node docs/spec-diagram/fsm/build.mjs --check   # hashes, upstream blobs, re-run every tape and edge
BEND=~/.bend/bin/bend node docs/spec-diagram/fsm/build.mjs   # recompile (refuses any other compiler identity)
```

The browser re-runs each step and shows whether it matches the receipt-bound
`replay.json`. Vite (`vite.fsm.config.ts`) refuses to bundle stale artifacts.

## Hapsland

`hapsland/fsm-layers.patch` is the full Hapsland working-tree change against
`dearlordylord/hapsland@a0773f79` (the earlier `.files` integration plus
`fsm.html`, `src/fsm/` and `vite.fsm.config.ts`). Lay out `hapsland/` and this
`.files` checkout as siblings, apply the patch, install `effect@4.0.0`,
`foldkit@0.165.0`, `@effect/platform-browser@4.0.0` and `vite@8.3.1`, then:

```sh
node node_modules/vite/bin/vite.js build --config packages/agent-flow-viz/vite.fsm.config.ts
```

On phones (≤700px) `src/fsm/mobile-view.ts` renders a separate shell: the
3D stack as the hero, one bottom thumb bar (layer chips from `model.json`
planes, event cards, scrub, tape, Play/Step, tabs) and the inspector as a
sheet. It reads the same projection, so new planes appear without code changes.

## Loop 3 · integration owner

Adds a fourth plane (the shared-resources plane is still part of Loop 2),
backed by unchanged `IntegrationOwner.bend` from z0intelligence#188 at
`1ef432f91223e74dcfb756c590aae82a950999ed`. The kernel receipt passes for
I1–I5 monitor/safety laws, including all-event merge entry safety. Parking
needs an explicit reason and expiry; an expired park requeues. The per-repo
lease cannot be stolen before expiry. Integration requires independent review.

`extract-integration-tapes.py /private/integration-20261021.json` produces five
allowlisted snapshot tapes in `integration-tapes.json`. Initial states come
from the checker; every action/probe is labelled WHAT-IF, including all owner
acceptance and merge events. These are not fabricated historical deployments.
NOOP checkout drift is not a claim about the installed phone's source revision.
Missing runtime SHA evidence remains unverified, not a green deploy.

The producer and browser concatenate these tapes after the original 12. Current
receipt: 17 tapes, 96 steps, 73 edges; Mermaid comparison has zero missing and
zero extra edges. Earlier counts in this README describe the original two-loop
snapshot. Both the original and Loop 3 inputs remain hash-bound by the producer.

The isolated headless browser was exercised at 412×915: all five new tapes
completed and every prefix matched the receipt-bound compiled Bend replay.
No owner desktop/phone was used. The full upstream check:fast was attempted
through fleet-build on the MBP and is blocked by missing vitest in that clean
remote source shipment; the bounded Vite bundle and browser proof passed.
This is not a full Hapsland source-qualification claim.

## Scope

A replay is not an authorization, an admission or verified success, and it
observes no live host. PROOF.bend passes cover Bend's emitted book
(`source_semantics_attested=false`). Worker hosts are not in the supervise
events, so report tapes assume groot with light load.
