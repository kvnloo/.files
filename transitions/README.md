# Transitions

This directory holds explicit one-time state transitions.

A normal `./iac apply` must never execute these implicitly. Destructive
operations require their own gates, review, verification, and human commit
boundary.

- `path-map.toml` describes repository path moves for symlink-safe rollout.
- `workspace-xfs-bcachefs.toml` describes the planned filesystem transition.
- `legacy/cachyos-migration/` contains the original one-shot CachyOS migration
  scripts and research. The root `migration` path remains a compatibility
  symlink for one rollout window.
