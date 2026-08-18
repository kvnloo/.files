# Storage incident — 2026-08-18

## Picture

```text
/workspace XFS: 331.6 GiB total
BEFORE  [####################] 100%   1.1 GiB free
AFTER   [###################.]  97%  12.1 GiB free
                                  ^ 11.0 GiB net headroom recovered

/ root XFS: 99.9 GiB total
AFTER   [###################.]  97%   3.7 GiB free  (still critical)
```

## Where it went

- `/workspace/zer0`: 173.2 GB, primarily canonical products (94.0 GB), OSS (64.5 GB), experiments (7.3 GB), clients (6.1 GB). Preserved.
- `/workspace/hermes-home`: 34.4 GB, including profiles (12.2 GB), kanban (3.5 GB), source (3.5 GB). Preserved.
- Reproducible caches before cleanup: `/workspace/cache` 22.1 GB (uv 16.4 GB), pnpm store 4.2 GB, npm cache lane 4.7 GB.
- Root contains 44.9 GB under `/home`, 22.7 GB `/usr`, 11.8 GB `/opt`, 3.8 GB `/var`; root remains under-provisioned for this workload.
- Inodes were not the triggering limit: workspace moved from 72% used to 19% used after cache pruning; byte capacity was the immediate failure.

## Safe recovery performed

- `UV_CACHE_DIR=/workspace/cache/uv uv cache clean`: tool reported 111,573 files / 15.0 GiB removed.
- `npm cache clean --force --cache /workspace/cache/npm`: reproducible cache only.
- `pnpm store prune --store-dir /workspace/.pnpm-store`: tool reported 66,214 files / 667 MB and 905 packages removed.
- Stopped four orphaned `npm run matrix` process groups plus their Chromium descendants; each had run ~2h45m from a deleted `kanban_hold_harness` worktree. Preserved the parent `start.py --keep-home` harness because ownership/terminal state was not proven.
- No repositories, dirty worktrees, models, datasets, attachments, product assets, Trash, Downloads, snapshots, or user documents were deleted.

## Root cause and recurrence

The immediate ENOSPC condition was cumulative reproducible package/build caches on the 332 GB `/workspace` XFS partition, amplified by long-lived E2E matrix/browser groups whose worktree had already been deleted. Canonical product/OSS data consumes most capacity, so cache cleanup alone buys limited runway. At the current workload, a single new 10–15 GB cache/model build can return the filesystem to stop-work territory.

## Permanent control

Dotfiles commit `2397224705ccd228b51b7e399d1b9240b4f79969` adds a fail-closed byte+inode guard with tiers 15% warn, 10% stop-new-heavy-work, 5% allowlisted writer stop. It uses locking, atomic state writes, dry-run, and an explicit service allowlist; it never deletes files. Service installation/enabling was intentionally not performed.

## Remaining Captain gates

1. Root remains at 97%; authorize a separate root-capacity migration/resize or explicit removal of selected applications/data. No resize/repartition was attempted.
2. Review and merge/cherry-pick the isolated dotfiles commit, then explicitly install and enable the user timer.
3. Populate `~/.config/disk-pressure-guard/stop-units` only with reviewed runaway-writer services.
4. Bounty scout unit `bounty-scout.service` is inactive and not installed under that name; it was not restarted. No production bounty DB was mutated.
