# Machine IaC

This directory is the declarative machine layer for `.files`.

The repo already has several useful sources of truth:

- `packages/packages.toml` — cross-platform package registry
- `config/` — editable configuration and unit files
- `config/nix/` — optional Home Manager layer for portable user-space state
- `scripts/onboard` — normal human/agent onboarding UX
- `migration/` — explicit one-time or destructive transitions

`machine/` adds the missing desired-state model. It does **not** replace those layers.

## Ownership model

| Layer | Owns |
| --- | --- |
| `machine/` | host roles, desired services/storage/repo topology, transition intent |
| `packages/` | package names and distro-specific installation mapping |
| `config/` | exact managed configuration files and systemd units |
| `config/nix/` | optional portable Home Manager state |
| `migration/` | explicit one-time/destructive state transitions |
| secrets backend | credential values |
| backup/restore | mutable P0 data such as databases, sessions, memory state |

## Invariants

1. **Observed state is not desired state.** A live package, service, or file is evidence only.
2. **Plan before apply.** The intended lifecycle is collect → plan → review → apply → verify.
3. **Normal convergence is non-destructive.** Filesystem conversion, partition edits, and similar transitions require a separate gated path.
4. **Secrets are references, never values.** No tokens, OAuth material, passwords, or private keys belong in machine manifests.
5. **Mutable state is restored, not declared.** Databases and agent/session history belong in a P0 restore manifest.
6. **Runtime changes need evidence.** Kubernetes/provider/SLM changes should carry correctness plus latency/reliability measurements before promotion.
7. **Persistent manual changes are incomplete until codified** as desired state, an explicit transition, or restore metadata.

## Phase 1

The first implementation is deliberately read-only:

```sh
./iac collect
./iac collect --stdout
```

The collector writes local observations under:

```text
~/.local/state/dotfiles/iac/<hostname>/observed.json
```

unless `--output` is supplied. It does not modify packages, services, mounts, or files under `/etc`.

Future slices tracked in GitHub issues will add desired host manifests, drift planning, Hermes/TencentDB topology, Kubernetes lab roles, P0 restore metadata, and explicit storage transitions.
