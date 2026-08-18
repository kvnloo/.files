# Disk capacity guard

`disk-pressure-guard.sh` is monitoring and containment, not a general deleter.
It checks free bytes and free inodes on `/` and `/workspace` and writes an
atomic state under `~/.local/state/disk-pressure-guard/`. Missing targets,
fallback parent filesystems, wrong devices/filesystems, unsafe state paths,
concurrent execution, and publication failures return nonzero with an
`unknown` reason receipt. Unknown state never invokes stop actions.

Tiers (free percentage, lowest of bytes and inodes):

- `warn`: 15%
- `stop-new-heavy-work`: 10% (nonzero exit for heavy-work preflights)
- `stop-runaway-writers`: 5%

At the final tier it stops only syntactically valid `.service` names explicitly
listed in `~/.config/disk-pressure-guard/stop-units`; an absent or empty file
stops nothing. It never deletes files. Use `--dry-run` to print stop actions.
Targets use `mountpoint|device|filesystem` records in `DISK_GUARD_TARGETS`.
The checked mount identity must be exact; `*` is accepted for device or
filesystem only when an operator deliberately configures it. The default is
this host's `/|/dev/nvme0n1p1|xfs /workspace|/dev/nvme0n1p3|xfs` layout.

The allowlisted state parent must already exist, be owned by the caller, mode
0700, and reside on the same filesystem as its direct child state directory.
Every existing path component is checked with `lstat`; symlinks are rejected.
State directories/files are 0700/0600. Reports are written to private temporary
files and atomically renamed only after a second mount identity check.

## Runbook and rollback

1. Review `findmnt -rn -o TARGET,SOURCE,FSTYPE --target / --target /workspace`
   and adjust `DISK_GUARD_TARGETS` if the host layout intentionally changes.
2. Run `tests/test-disk-pressure-guard.sh`, then invoke the guard with
   `--dry-run`. Do not populate `stop-units` until each exact service is reviewed.
3. Installation/enabling is a separate operator action and was not performed.
4. Roll back by disabling/removing the timer and installed script, then revert
   the guard commit. State receipts can be retained; the guard never deletes data.
