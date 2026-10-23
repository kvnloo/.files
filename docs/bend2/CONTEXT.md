# Bend2 context for `kvnloo/.files` — host intent, fleet, phone and ops gates

> **Documentation-only context handoff** for OMP / owner review. Target: `context/bend2-laws` branched from `master`. This file does **not** implement a new law, enable a hook, install a service, or prove a real device state. Canonical cross-repo history: [z0intelligence issue #199, `BEND1-HISTORY`](https://github.com/kvnloo/z0intelligence/issues/199). Review the existing stacked drafts before doing any code work.

## Why the dotfiles repo is in the proof boundary

This repository configures host and agent workflows, so most of the harm happens *after* a valid pure decision, at the boundaries to `git`, the fleet, systemd, Android/ADB, KDE Connect and external providers. [`AGENTS.md`](../../AGENTS.md) requires explicit user approval for onboarding/setup; never silently install or modify the live system. A mathematically correct Bend decision does **not** prove a shell classifier, a real process, the active app, a checked-out SHA, or permission.

**Architecture**: `owner-approved rule (Bend LAWS) → Bend pure reducer + PROOF → parity-checked Python/TS adapter → opt-in/report-first host gate → actual observed receipt`. The reusable proof models and Python twin already live in the z0intelligence drafts; .files owns the *host adapters and visualization*, **not** a second Bend store/verifier or authority service.

## Existing work: inventory and merge status

The following were **open Draft PRs** when this document was prepared; they are stacked on non-default bases, so their paths may not be present on `.files master`:

| Existing Draft PR | What it owns | Relationship |
| --- | --- | --- |
| [#34](https://github.com/kvnloo/.files/pull/34) `docs/fsm-hapsland-layers-20261021` | `docs/spec-diagram/fsm/`, `WorkItem.bend`, `WorkerSupervision.bend`, compiled Bend statechart edges, read-only replay tapes, Hapsland view patch; L1–L7 and W1–W6 badges | Base `infra/k3s-single-node-phone-20261016`; original models in [z0 #183](https://github.com/kvnloo/z0intelligence/pull/183) and [#184](https://github.com/kvnloo/z0intelligence/pull/184) |
| [#36](https://github.com/kvnloo/.files/pull/36) `docs/fsm-hapsland-mobile-20261021` | Phone-first FSM UI; REPORT / WHAT-IF tapes, not permission or live device attestation | Stacked on #34 |
| [#37](https://github.com/kvnloo/.files/pull/37) `docs/fsm-hapsland-ops-layer-20261021` | `Ops.bend` pinned from z0 source, `OpsLayer.bend`, ops/nodes/gateway layers, 11 dated incident tapes | Stacked on #36; mirrors [z0 #192](https://github.com/kvnloo/z0intelligence/pull/192) |
| [#38](https://github.com/kvnloo/.files/pull/38) `feat/ops-gates-20261021` | `scripts/fleet-build` O1, `scripts/z0-guard`, `scripts/fleet` O8, `config/git-hooks/z0-hooks` + `scripts/z0-hooks-install` O4 | Stacked on #30 (`feat/k3s-cluster`); host action gate distinct from #37 diagram |
| [z0 #192](https://github.com/kvnloo/z0intelligence/pull/192) | `bend/ops_fsm/{ops,LAWS,PROOF}.bend`, `src/z0int/fsm/{ops,ops_parity,ops_replay,guard}.py`, incident tapes, default modes | Canonical *model* and checked contract, not something to copy/reimplement here |

Additional context: [.files issue #23](https://github.com/kvnloo/.files/issues/23) single-node K3s baseline; [z0 issue #182](https://github.com/kvnloo/z0intelligence/issues/182) statechart program; [z0 #188](https://github.com/kvnloo/z0intelligence/pull/188) I1–I5 integration-owner guard; [z0 #189](https://github.com/kvnloo/z0intelligence/pull/189) read-only/opt-in supervised leases; [z0 issue #199](https://github.com/kvnloo/z0intelligence/issues/199) coordinator. A proof receipt in a Draft PR must not be mistaken for a deployed gate.

## Owner decisions suitable for `LAWS.bend`

Formalize **finite, pure** inputs and states. Proposed names below are *conceptual*; exact law names/constructors must reuse existing z0 code and require review of the actual LAWS diff before modifying any proof.

| Law/model | Required invariant on pure input/state | Where runtime effects happen | Oct 21 documented default |
| --- | --- | --- | --- |
| **O1, W4: compute placement** | Heavy classes (test, mutation, typecheck, Gradle, bundle, eval, screenshot) admit only a non-`groot` lane; central host only small, service, GPU, Bend/Lean exceptions; no available lane → wait, never silent fallback | `scripts/fleet-build`, `z0-guard run`, queued jobs | O1 enforce |
| **O2: no edits to served worktrees** | Live-service lease refuses edits, commits, checkout, stash, merge; sole exception a recorded `ff-only` move/rollback inside authorized rollout transaction | reference-transaction/git hooks, `z0-guard rollout` | enforce |
| **O3: rollback-safe deploy** | Candidate must be clean and not already served; required independent orchestrator review; restarts/checks only when owner-call guard permits; failed runtime launch → rollback; otherwise defer/pending | `z0-guard rollout`, actual service manager and launch check | report |
| **O4: private push stop** | A private-labeled path/corpus must never be emitted to public or unknown-privacy remotes. Unknown remote privacy is a refusal, not an allow | `config/git-hooks/z0-hooks`, `scripts/z0-hooks-install`, git pre-push | enforce only after opt-in hook install |
| **O5: owner phone intent** | Phone tap/type/install requires explicit owner intent AND fresh expected foreground; app install/restart refused during live z0live call; unknown call state counts as live | z0live broker and phone/install adapters, `z0-guard phone` | report |
| **W5: install lease** | At most one active device install-lock holder; only current holder can install; stale lease/target refuses | Android install script and device lock | model proven in z0 #184; adapter qualification needed |
| **W6: foreground freshness** | Every S25 UI input requires a fresh observation of intended foreground; never type into a target inferred from an earlier step | phone automation adapter | model proven in z0 #184; runtime qualification needed |
| **O6: accessibility monotonicity** | Post-install enabled accessibility service set contains pre-install set except explicitly owner-removed services | `install-z0live-apk.sh`, `z0-guard a11y` | enforce |
| **O7: role/provider allowlist** | No route to a cancelled provider; visual/UI-design role not mapped to Sol per the **dated** 2026-10-21 rule | `z0-guard routing` reading harness configs | report |
| **O8: unhealthy episode notify-once** | Once a worker remains unhealthy >30 min, exactly one *intent to notify* per episode; duplicate polls/retries must not produce additional emits; a new healthy→unhealthy episode may emit again | `scripts/fleet health`, KDE Connect to paired phone | report |
| **O9: gateway interruption recovery** | Restart of headless-run gateway converts vanished active dependent runs to `Interrupted` with resume pointer, not `Failed`; no loss of head/checkpoint | `z0-guard gateway-watch`, local append-only state | report |
| **H1: onboarding consent** (*candidate; not claimed in existing proofs*) | Any module that configures host, SSH, services or device runs only after current explicit owner approval and scoped target check | `scripts/onboard`, `./install` | existing `AGENTS.md` policy, no Bend proof claimed |
| **H2: secrets boundary** (*candidate*) | No private credentials/Agent Reach state/host-private corpus may flow into repository artifact or unknown-public remote | precommit/prepush, packaging, CI artifact uploader | property/risk model, never assume pure proof catches actual bytes |

Owner review must establish which rules are universal safety invariants versus changing policy/profile: e.g. O7's cancelled-provider set and design-role routing are time/version-scoped facts; hard-coding a historical cancellation without live configuration would be wrong.

## Which changes need `PROOF.bend`?

Existing z0 implementation uses `LAWS.bend` (human-approved claim) + `PROOF.bend` (implementer proof) and `bend PROOF.bend --verdict`. **Require renewed proof whenever the pure transition model changes**:

1. O1 permitted class/node matrix or retry/wait behavior; O2 exception path; O3 rollback and pending states; O4 privacy label/remote-state lattice.
2. O5/W5/W6 phone-intent, foreground and lock-state transitions; O6 accessibility removal exceptions; O7 role/provider eligibility; O8 episode state machine; O9 restart classification and resume-pointer preservation.
3. Model type/constructor updates, law text changes, compiler/kernel/toolchain changes, imported law/implementation hash changes, or reuse in a new adapter must trigger a reviewed, pinned verifier run (not automatic trust inheritance).

**Formal obligations** are safety/exhaustive transition properties of abstract `Data`; model *exactly-one* notification intent and idempotent repeats, but **not** real delivery within 30 min without a scheduler/fairness/transport assumption. External I/O requires separate red/green integration tests, not a fabricated theorem. `--verdict` is about the checked emitted BendTT book; prior receipts explicitly report `source_semantics_attested=false`.

## Host-enforcement tests OMP should run *before enabling*

- **Spec identity:** use existing pinned Bend 2.0.34/2.0.37 pins as declared by the relevant draft, record exact SHA/tool versions, approved `LAWS.bend` hash and `PROOF.bend` manifest. Never run with an ambient untrusted `BENDTT` override; source → emitted-book translation requires independent qualification.
- **Parity and sabotage:** deterministic finite-state exhaustive/properties plus seeded replay on Bend vs existing Python adapter, with deliberate classifier mutation. Source-level proof cannot establish that `fleet-build` actually sent a job to the intended machine.
- **O1:** scratch fleet jobs with heavy/classified/exception/unknown input, explicit `--node groot` denial and no silent fallback when no healthy node.
- **O2/O3:** scratch served-service/worktree; reject git ref changes and mutations outside rollout token; record clean candidate, launch check, rollback and owner-call deferral. Never test by mutating current served checkout.
- **O4:** opt-in `core.hooksPath` on a scratch repo, one known-public remote, one unknown remote, one private remote; preserve an existing pre-push hook. No private test data committed or pushed.
- **O5/W5/W6/O6:** synthetic/sanitized Android fixture plus consented device smoke for lock ownership, foreground freshness, live/unknown call state and accessibility superset. Never trigger live UI action based on a replay alone.
- **O8/O9:** fake time, duplicate polls, health flaps, gateway/head changes, crash/restart replay. Distinguish “notification intended” from “notification delivered.”
- **Regression:** `node docs/spec-diagram/fsm/build.mjs --check` and `node docs/spec-diagram/build.mjs --check` on the appropriate stacked branch; unknown evidence → REPORT/HOLD, never a green proof.

## Open questions and boundaries

1. Which PR stack should OMP integrate first: z0 pure models (#183/#184/#188/#192) or host #38? Prioritize proofs/parity and no default-branch merge without owner authorization.
2. Do host wrappers call one centrally installed `z0-guard` with a pinned checkout, or ship a versioned package? Avoid a second implementation whose semantics drift.
3. Which live policy sources define classes, “owner-call active”, provider cancellation, trusted remote visibility, device identity, accessibility removals, and owner-approved intent? Model unknown explicitly.
4. How to attest *served binary/build head* and *live foreground* independently of a checkout/JSON annotation? A proof over a fabricated input is not an operational guard.
5. How to introduce host enforcement incrementally: O1/O2/O4/O6 already documented enforce in drafts, O3/O5/O7/O8/O9 report-first; no global hook/install/notification side effects without separate consent.
6. How will verified refusals, incident receipts and recoveries flow into the existing z0 evals/decision ledger without copying secrets or personal device traces? Prefer hashed/redacted minimal evidence.

## References and terminology

- [Full dated Bend history and paper index](https://github.com/kvnloo/z0intelligence/issues/199) including [zekramu Oct 22 post](https://x.com/zekramu/status/2113081285707251845) and [Dafny paper](https://arxiv.org/abs/2501.06283).
- [Upstream Bend2 guide](https://github.com/bendlang/bend/blob/main/guide/GUIDE.md), [BendTT paper](https://github.com/bendlang/bend/blob/main/paper/BendTT.pdf), [BendRT paper](https://github.com/bendlang/bend/blob/main/paper/BendRT.pdf). Bend2/BendRT is distinct from Bend1/HVM; concolic test generation supplements but does not replace proof.
- The current change is **context only**. No `LAWS.bend`, `PROOF.bend`, production gate, CI test result, or default-branch change was added by this Draft PR.
