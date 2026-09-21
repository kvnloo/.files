# Agent onboarding for .files

This repository is both a dotfiles repo and the desired-state control repo for a small fleet.

## First contact

When the user asks about setup/install/onboarding:

```sh
./scripts/onboard status --json
```

Ask before running mutating onboarding modules. The terminal installer remains:

```sh
./install
```

## Persistent-change rule

A persistent manual machine change is not complete until the same task does one
of these:

1. represents the desired state in the existing canonical source;
2. adds an explicit one-time transition; or
3. records mutable P0 restore metadata.

Do not create a second source of truth when one already exists.

Examples:

- package groups: `packages/packages.toml`
- exact config/unit files: `config/`
- portable user state: `config/nix/`
- fleet/host intent: `fleet.toml`
- destructive one-offs: `transitions/`
- mutable restore metadata: `restore/`

## Architecture rules

- common config first, host delta second
- convention beats another mapping layer
- do not introduce inheritance because two hosts repeat a few values
- workload repos own Kubernetes Jobs/Deployments/evals; `.files` owns host prerequisites and references
- observed state is evidence, never automatically desired state
- normal IaC apply must remain reversible/idempotent and non-destructive
- secrets are references only
- runtime changes should carry correctness plus latency/reliability evidence

See `docs/iac.md`.

## Path-migration rollout

Never assume a repository path rename is safe because the Git diff is safe.
The live machine may have symlinks pointing at the old path.

Before a path-moving PR is merged into the active checkout:

1. create a candidate worktree;
2. use `./iac links scan` with `transitions/path-map.toml`;
3. review the frozen plan;
4. stage links into the candidate;
5. run doctor/plan/smoke checks;
6. rollback on any regression;
7. only after approval update the canonical checkout and cut links back to it.

See `docs/iac-rollout.md`.

## Safety rules for public clones

- Never commit Sunshine credentials, Tailscale auth keys, API tokens, OAuth tokens, private keys, or secret values.
- Never read browser credential stores, keyrings, password-manager databases, `.env`, or auth files for an inventory task.
- Prefer tracked helpers under `scripts/` and `config/`.
- When unsure, run `./scripts/onboard doctor` and `./iac plan` before changing system files.

## Setup modules

Recommended baseline:

| Module | Purpose |
| --- | --- |
| `core-links` | shell/tmux/git/Hyprland/nvim/noctalia/Waybar/PipeWire links and helpers |
| `agent-skills` | workspace-copilot links for supported harnesses |

Optional modules remain in `scripts/onboard`: `agent-tools`, `tailnet-ssh`,
`nix-home`, and `audio-evolution`.
