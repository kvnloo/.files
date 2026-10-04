# Transitions

This directory holds explicit one-time state transitions.

A normal `./iac apply` must never execute these implicitly. Destructive
operations require their own gates, review, verification, and human commit
boundary.

- `path-map.toml` describes repository path moves for symlink-safe rollout.
- `workspace-xfs-bcachefs.toml` describes the planned filesystem transition.
- `claudedocs` and `POLYBAR_PYWAL_USAGE.md` are compatibility symlinks to
  `docs/archive/claude` and `docs/legacy/POLYBAR_PYWAL_USAGE.md`.
- `migration/` is a compatibility symlink to `legacy/cachyos-migration/`.
  The 7-day hot window on `02-deploy-dotfiles.sh` (content commit 2026-09-17)
  cleared before 2026-10-04. Active scripts walk to `.git` for the repo root
  so `readlink -f` through the symlink does not retarget `DOTFILES`.
- `proposal_codexbar_aggregate.md` is not in this tree, so its mapped
  proposal path is not created.
