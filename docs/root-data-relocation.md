# Root → 4 TB relocation (t_bdc3baba)

## Outcome at a glance

```text
XFS root (100 GiB, 97% used) ── verified copy ──▶ Btrfs SATA SSD (3.7 TiB, 3.2 TiB free)
          │                                             │
          ├─ symlink: ~/comfyui-3080ti-research ────────┘
          └─ retained rollback backup: 8,735,744,000 allocated bytes

Current root blocks freed: 0 (intentional; reviewer must approve backup deletion)
Partition/reboot/sudo actions: 0
```

## Live storage identity

| Path | Device | FS | UUID | Options / persistence | State |
|---|---|---|---|---|---|
| `/` | NVMe `/dev/nvme0n1p1` | XFS | `9e575c2d-52cc-41ec-8b3f-15afd8191c81` | `noatime,lazytime`; fstab | 100 GiB, 3.7 GiB free (97% used) |
| `/workspace` | NVMe `/dev/nvme0n1p3` | XFS | `f70404dd-c13b-4070-8d7c-d6d5e91db153` | fstab | 332 GiB, 11 GiB free |
| `/mnt/zer0models` | SATA SSD `/dev/sdb2` | Btrfs | `3c8b6c35-4d36-4a69-b5f3-df88f07cbd82` | enabled `mnt-zer0models.mount`, `WantedBy=multi-user.target`, before Ollama; `noatime,compress=zstd:3` | 3.7 TiB, 3.2 TiB free |

The target is local SATA SSD, persistent by exact UUID, user-owned at its root, and already contains the canonical `home-offload/kvn` hierarchy. It is not encrypted at the filesystem/block layer as observed; therefore secrets/config/browser profiles were excluded. Root can boot without it, but relocated paths are unavailable until the enabled mount starts. The helper refuses a missing/wrong mount rather than creating data beneath an unmounted mountpoint.

## Executed migration

Candidate: `~/comfyui-3080ti-research` (research source mirrors and workflow templates; no live database/service)

- No open files found before copy and again before cutover.
- 13,898 objects; 12,327 regular files; 8,707,408,605 apparent bytes; 8,735,744,000 XFS allocated bytes.
- `rsync -aAXHSx --numeric-ids` to a unique incoming directory; no destination existed.
- Checksum rsync returned an empty itemized diff.
- Full SHA-256 + portable metadata manifest: 13,897 entries each side, equality PASS, manifest SHA-256 `20844981d67330e359b1007df262e3c3c0b8c4ade0860dd221c3a507d2fa5c18`.
- Manifest intentionally excludes directory `st_size`/`st_nlink`: XFS reports ordinary directory sizes/link counts while Btrfs reports zero/one. File bytes, file size/link count, type, mode, uid/gid, symlink target and xattrs are bound.
- All 14 nested Git repositories remained clean and resolved HEAD on the target.
- Runner `py_compile`, `--help`, read and write-through-symlink smoke PASS.
- Atomic cutover created:
  - link: `/home/kvn/comfyui-3080ti-research` → `/mnt/zer0models/home-offload/kvn/comfyui-3080ti-research`
  - backup: `/home/kvn/comfyui-3080ti-research.migration-backup.t_bdc3baba.20260818T213728Z`
  - evidence: `/mnt/zer0models/home-offload/kvn/.migration-receipts/t_bdc3baba-20260818T213728Z`
- Rollback: unlink only the symlink, then rename the retained backup to its original name. No target deletion is required.

## XFS → Btrfs compatibility gate

Copied-target fixture PASS: case sensitivity, sparse allocation, hardlinks, symlinks, xattrs, POSIX ACL, `flock`, mmap, executable bit, atomic rename + directory fsync, SQLite WAL/commit/reopen, Unix sockets and `O_TMPFILE`. Project-specific Git status and standard-library runner smoke passed. No project direct-I/O, container overlay, active SQLite, reflink-dependent build, or Unix-socket workload was identified. Btrfs CoW/compression and different directory metadata remain recorded differences. A real GPU workflow was not launched because that would spend production GPU work and is not needed to validate this source/reference tree; reviewer may require it before backup deletion.

## Ranked opportunity matrix

| Rank | Root allocation | Candidate | Classification | Gate / decision |
|---:|---:|---|---|---|
| 1 | 8.74 GB | `~/comfyui-3080ti-research` | migrated, backup retained | reviewer may approve backup deletion; this alone raises root to about 12% free, below 15% |
| 2 | 5.04 GB | `~/.grok` | application-specific/protected | sessions, memtrace and downloads; likely secrets/history; active Grok bridge. Do not move broadly without app shutdown + Btrfs DB/locking test |
| 3 | 2.55 GB | `~/Downloads` | mixed/private evidence | Telegram export and ad videos are not reproducible; archive-by-item only after human classification |
| 4 | 2.11 GB | `~/.pnpm-store/v3` | reproducible legacy cache | pnpm 11 reports active store v11 and prune does not remove v3; explicit old-store retirement proof needed |
| 5 | 1.43 GB | `~/.paperclip` | application-specific | instances + CLI installs; Paperclip retired but history retained, so no deletion/move without lineage check |
| 6 | 1.01 GB | `~/.gradle` | mostly reproducible cache | 856 MB caches, but preserve wrapper/config; app-native cleanup can be a later low-risk action |
| 7 | 10.86 GB | `~/.local` | protected/mixed | Flatpak, binaries, active SQLite/WAL services, app state; broad move rejected |
| 8 | 7.06 GB | `~/.config` | protected/mixed | live Hermes/browser/LevelDB/dconf writers and secrets; broad move rejected |

`~/.cache` and `~/.codex` already point to `/workspace`, so moving them would not free root. NPM `_npx` had active MCP processes and was excluded. Trash (277 MB) was not treated as reproducible. No model, dataset, download, private evidence, session store, browser profile, or config was deleted.

## Durable helper and test evidence

Isolated dotfiles branch `storage-relocation/t_bdc3baba` adds `scripts/home-relocate.py`. It is manual-only and supports `dry-run`, `commit`, and `rollback`; exact UUID/Btrfs mount gate; 10 GiB reserve; destination/incoming/symlink/split-brain refusal; open-writer refusal; nonblocking invocation lock; archive+xattr+ACL+hardlink+sparse copy; checksum verification before rename; retained source backup; and JSON receipt. It never deletes a source backup or target copy.

Integration fixture PASS: spaces, hardlink identity, sparse allocation, xattr, permissions, wrong UUID refusal, dry-run, commit, retained backup, symlink, rollback. Runtime migration also proves existing-destination and open-file preflight on the real candidate. Not destructively simulated: target-full and interrupted-rsync; implementation fails closed before cutover and preserves incoming data for inspection. Target-absent is enforced by the same exact `findmnt` target/UUID/type predicate as wrong-target.

## Review gates

1. Independently rehash/sample the sealed target and inspect the retained source backup.
2. Reverify mount identity, link, no writers, application smoke, and rollback command.
3. Approve or reject deletion of only the named backup. Until then actual root freed is zero.
4. If backup deletion is approved, root is expected to gain 8,735,744,000 allocated bytes (~8.13 GiB), reaching only ~12% free. Reinventory after deletion; do not force 15% by moving `.config`/`.local`.
5. Target data now shares the 4 TB disk's backup/failure domain and is not independently backed up by this task.
