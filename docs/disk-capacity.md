# Disk capacity guard

`disk-pressure-guard.sh` is monitoring and containment, not a general deleter.
It checks free bytes and free inodes on `/` and `/workspace` and writes an
one authoritative atomic snapshot at
`~/.local/state/disk-pressure-guard/current.json`. Missing targets,
fallback parent filesystems, wrong devices/filesystems, unsafe state paths,
concurrent execution, and publication failures return nonzero with an
`unknown` reason receipt. Unknown state never invokes stop actions.

Tiers (free percentage, lowest of bytes and inodes):

- `warn`: 15%
- `stop-new-heavy-work`: 10% (nonzero exit for heavy-work preflights)
- `stop-runaway-writers`: 5%

At the final tier it stops only syntactically valid `.service` names explicitly
listed in `~/.config/disk-pressure-guard/stop-units`; an absent or zero-byte file
stops nothing. Before any stop, the complete regular file is checked for caller
ownership, mode 0600 (or stricter), exact service syntax, duplicates, blank
lines, comments, and whitespace. Any defect publishes `unknown` and performs
zero stop actions. It never deletes files. Use `--dry-run` to print stop actions;
all other arguments are rejected.

Allowlist presence is lexical: a dangling symlink is invalid, not absent. Before
opening, the guard uses `lstat` and accepts only a caller-owned, singly linked
regular file with private mode. It then opens with `O_NOFOLLOW|O_NONBLOCK`,
checks the descriptor's type, owner, mode, link count, device and inode against
the precheck, and bounds both size and read time. Directories, FIFOs, sockets,
devices, valid or dangling symlinks, hardlinks, and files replaced during the
check therefore fail closed without blocking or invoking a service action.
Targets use `mountpoint|device|filesystem` records in `DISK_GUARD_TARGETS`.
The checked mount identity must be exact; `*` is accepted for device or
filesystem only when an operator deliberately configures it. The default is
this host's `/|/dev/nvme0n1p1|xfs /workspace|/dev/nvme0n1p3|xfs` layout.

The allowlisted state parent must already exist, be owned by the caller, mode
0700, and reside on the same filesystem as its direct child state directory.
Every existing path component is checked with `lstat`; symlinks are rejected.
State directories/files are 0700/0600. Each JSON snapshot contains tier, report,
monotonic generation, and a SHA-256 of its canonical payload. It is fsynced,
renamed once, and followed by a directory fsync only after a second mount
identity check. ENOSPC or interruption before rename leaves the prior snapshot
wholly authoritative; if the state root itself is unavailable, the guard emits
a stable fail-safe `unknown` to stderr/journal and does not claim a durable receipt.

## Runbook and rollback

1. Review `findmnt -rn -o TARGET,SOURCE,FSTYPE --target / --target /workspace`
   and adjust `DISK_GUARD_TARGETS` if the host layout intentionally changes.
2. Run `tests/test-disk-pressure-guard.sh`, then invoke the guard with
   `--dry-run`. Do not populate `stop-units` until each exact service is reviewed.
3. Installation/enabling is a separate operator action and was not performed.
   Before starting the unit, link
   `config/user-tmpfiles.d/disk-pressure-guard.conf` into
   `~/.config/user-tmpfiles.d/` and run `systemd-tmpfiles --user --create`.
   This creates the first-run leaf at mode 0700. The service sandbox deliberately
   grants its guaranteed existing parent (`~/.local/state`), not a leaf that the
   service would need to create after namespace setup.
4. Roll back by disabling/removing the timer and installed script, then revert
   the guard commit and remove the tmpfiles link. State snapshots can be retained;
   the guard never deletes data.
