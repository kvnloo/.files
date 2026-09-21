# Fleet IaC

`.files` is the desired-state control repo for a **fleet** of hosts.

Terminology:

- **fleet** — all hosts managed by this repo
- **host** — one OS instance / physical or virtual computer
- **cluster** — a Kubernetes control/workload domain
- **workload** — something scheduled into a cluster
- **profile** — an application configuration variant, such as a Hermes profile
- **transition** — an explicit one-time state mutation
- **P0 state** — mutable data that must be restored after a rebuild

The repo already has useful sources of truth and should extend them instead of duplicating them:

- `packages/packages.toml` — cross-platform package registry
- `config/` — topic-oriented editable configuration and unit files
- `config/nix/` — optional Home Manager layer for portable user-space state
- `scripts/onboard` — normal human/agent onboarding UX
- `migration/` — existing one-time migration history, to be retired gradually
- workload repositories such as `hermes-k8s-lab` — Kubernetes manifests and workload-specific tests

## First-principles rules

1. **Observed state is not desired state.** A live package, service, or file is evidence only.
2. **One source of truth per setting.** Extend the canonical file instead of creating a second writer.
3. **Common first, host delta second.** Topic config stays shared; host-specific files contain only the delta.
4. **Convention beats mapping.** A stable host id should resolve the matching host overlay everywhere.
5. **No abstraction before repetition.** A little duplication across two hosts is cheaper than an inheritance engine.
6. **Plan before apply.** The lifecycle is collect → plan → review → apply → verify.
7. **Normal apply is non-destructive.** Filesystem conversion and partition edits use explicit transitions.
8. **Secrets are references, never values.**
9. **Mutable data is restored, not declared.**
10. **Workload repos own workload manifests.** This repo declares that a host wants a lab/cluster; the app repo owns its Jobs/Deployments/evals.
11. **Runtime changes need evidence.** Kubernetes/provider/SLM changes should carry correctness and latency/reliability measurements before promotion.
12. **Persistent manual changes are incomplete until codified** as desired state, an explicit transition, or restore metadata.

## Minimal target shape

The intended steady state stays small:

```text
.files/
├── fleet.toml                 # thin host/cluster inventory
├── packages/packages.toml     # package registry
├── config/                    # canonical topic-oriented config
├── scripts/onboard            # onboarding/module implementation
├── scripts/iac/               # collect / plan / apply / verify
├── transitions/               # explicit destructive one-offs
├── restore/p0.toml            # metadata only; no private data
└── migration/                 # legacy until migrated safely
```

There is intentionally no generic `roles/`, `services/`, or per-host copy of `config/` until real repetition justifies one.

## Rollouts and symlinks

A path migration must not turn `git pull` into an outage.

The rollout pattern is:

1. create a new worktree for the candidate branch;
2. run `./iac links scan` from the candidate worktree against the active checkout;
3. review the generated plan;
4. stage links against the candidate worktree and run smoke tests;
5. roll back immediately if a smoke test fails;
6. merge/update the canonical checkout;
7. cut links over to canonical paths;
8. keep compatibility symlinks for at least one rollout window before deleting old repo paths.

The scanner only considers symlinks whose targets resolve inside the active `.files` checkout. It never changes links during `scan`.

## Phase 1

The first implementation is deliberately read-only:

```sh
./iac collect
./iac collect --stdout
```

Observed state is stored outside Git by default:

```text
~/.local/state/dotfiles/iac/<hostname>/observed.json
```

The next slice adds `fleet.toml` and `./iac plan` only after observations from the real hosts are available.
