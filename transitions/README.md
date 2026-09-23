# Transitions

This directory holds explicit one-time state transitions.

A normal `./iac apply` must never execute these implicitly. Destructive
operations require their own gates, review, verification, and human commit
boundary.

- `path-map.toml` describes repository path moves for symlink-safe rollout.
- `workspace-xfs-bcachefs.toml` describes the planned filesystem transition.
- `claudedocs` and `POLYBAR_PYWAL_USAGE.md` are compatibility symlinks to
  `docs/archive/claude` and `docs/legacy/POLYBAR_PYWAL_USAGE.md`.
- `migration/` stays the canonical directory while `02-deploy-dotfiles.sh`
  is inside the 7-day hot window (content commit 2026-09-17). Its mapped
  destination `legacy/cachyos-migration/` is not created until that clears.
- `proposal_codexbar_aggregate.md` is not in this tree, so its mapped
  proposal path is not created.
