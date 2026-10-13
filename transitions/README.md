# Transitions

This directory holds explicit one-time state transitions.

A normal `./iac apply` must never execute these implicitly. Destructive
operations require their own gates, review, verification, and human commit
boundary.

- `path-map.toml` describes repository path moves for symlink-safe rollout.
- `workspace-xfs-bcachefs.toml` describes the planned filesystem transition.
- `claudedocs`, `POLYBAR_PYWAL_USAGE.md`, `docs/archive` and `docs/legacy` were
  removed on 2026-10-13. The old notes stay in git history.
- `legacy/cachyos-migration/` and the root `migration` symlink were removed on
  2026-10-13. The one-shot CachyOS migration scripts stay in git history.
- `proposal_codexbar_aggregate.md` is not in this tree, so its mapped
  proposal path is not created.
