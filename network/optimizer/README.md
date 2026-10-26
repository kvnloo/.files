# network meta-optimizer (WP1)

A **thin placement policy + detector** for the z0 fleet. It decides where a job
belongs and routes NEW heavy build invocations off a lagging laptop (mbp) onto
the desktop (groot), through planes that already exist. It owns no scheduler, no
admission math, and no killer (spec `~/workspace/.design/network/META-OPTIMIZER-SPEC.md`,
sections 0-7 + the Revisions R1-R9, which override the body).

## What it is / is not

- **Is:** a 60s systemd `--user` timer on **groot** that samples the fleet
  read-only, runs the pure `place()` policy, and appends a decision per cycle.
  Plus a thin mbp-side `route-build` wrapper that steers NEW build invocations.
- **Is not:** a process migrator. It never kills, moves, or restarts a running
  process (R5), never writes `memory.*` / `oom_score_adj` / cgroup limits (R9a),
  and adds no competing killer (D4/L-P5). Stateful work is only ever PROPOSED.

## Files (source of truth = this repo; `install.sh` applies it)

| file | role |
|---|---|
| `laws.py` | Python law predicates L-P2..L-P8 (R9-corrected L-P5; L-P1 deleted per R1; no Bend per R3) |
| `place.py` | pure `place(job, state)` -> AdmitHere / Route(groot) / Wait / Refuse (hard gate only; no cost score per R4) |
| `sampler.py` | read-only networkState; groot via local /proc, mbp via ONE cheap ssh pull (R8) |
| `engine.py` | engine-choice helper: job class -> engine + the one existing plane (build/test execs; others return a plan) |
| `optimize.py` | one cycle: sample -> decide -> log; observe-only (`NETOPT_DRYRUN=1`) |
| `decide.py` | groot-side one-shot verdict for the wrapper (reads cached state; ms-cheap) |
| `route-build` | mbp-side thin wrapper (WP1-B); fail-OPEN to local, never blocks |
| `test_place.py` | fixture tests (16): gate ordering, purity, law predicates |
| `systemd/*.timer/.service` | the deployed unit (Nice=19, MemoryMax=256M, oom 900, RandomizedDelaySec=20s) |
| `config.toml` | tunables (no IPs/host literals; aliases resolve via ssh config) |

## Control-plane reuse (no new systems, D8)

| job class | plane it drives |
|---|---|
| build/test | **remote-exec** (`tern-remote.service` / ssh) to groot, `-j nproc/2` |
| batch-inference | **llama.cpp** farm OpenAI endpoint (exllama for EXL2) — endpoint from `$Z0_LLAMA_ENDPOINT` |
| fine-tune | **k3s + kueue** + unsloth on `/mnt/zer0models` — *deferred* (GPU not advertised) |
| eval | **lm-eval-harness** vs the endpoint |
| generic-agent-task | **Hermes kanban** codex `gpt-6.1-sol` (never bare `codex exec`) |
| bounded-subtask | **route_worker** (z0intelligence MCP), posture-gated |
| config change | **host-drift** -> this repo (`~/workspace/.files`) |

## Deploy (groot)

```sh
bash install.sh            # observe-only DRY-RUN
bash install.sh --enact    # WP1-B: route new builds (only after the checks below)
bash install.sh --uninstall
```

Kill switch (halts enactment instantly; loop then only samples+logs):

```sh
touch ~/tmp/network/network-optimizer.OFF
```

## WP1-B preconditions (verify + record before `--enact`)

1. `netopt-decide build/test -- <cmd>` returns ROUTE/LOCAL over one ssh hop.
2. The build tree is present on groot and build scratch writes to
   `/mnt/zer0models` (groot `/` is 91% full).
3. Same toolchain versions on both hosts for the routed command.
4. groot gate returns Admit (headroom >= min_avail_mib, kills_last_10min == 0).
5. groot kill rate == 0 for the last 10 min.

Fail-open is the invariant: if any check or the ssh verdict is unavailable, the
wrapper runs the command locally. It never blocks the owner.

## Evidence

- State: `~/tmp/network/state/latest.json` (+ rolling snapshots)
- Decisions: `~/tmp/network/decisions.jsonl` (one line/cycle, with state hash + ref)
- Rollback: `~/tmp/network/rollback.txt`
