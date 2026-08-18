# Disk capacity guard

`disk-pressure-guard.sh` is monitoring and containment, not a general deleter.
It checks free bytes and free inodes on `/` and `/workspace` and writes an
atomic state under `~/.local/state/disk-pressure-guard/`.

Tiers (free percentage, lowest of bytes and inodes):

- `warn`: 15%
- `stop-new-heavy-work`: 10% (nonzero exit for heavy-work preflights)
- `stop-runaway-writers`: 5%

At the final tier it stops only syntactically valid `.service` names explicitly
listed in `~/.config/disk-pressure-guard/stop-units`; an absent or empty file
stops nothing. It never deletes files. Use `--dry-run` to print stop actions.
Thresholds and mounts can be overridden with `DISK_GUARD_*` variables for
fixture tests. Installation/enabling remains an explicit operator action.
