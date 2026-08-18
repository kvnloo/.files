#!/usr/bin/env bash
set -euo pipefail
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
state="$root/state with spaces"
allow="$root/allow"
printf '%s\n%s\n' 'fixture-writer.service' '../bad.service' >"$allow"

out=$(DISK_GUARD_STATE_DIR="$state" DISK_GUARD_UNIT_ALLOWLIST="$allow" \
  DISK_GUARD_MOUNTS="$root" DISK_GUARD_WARN_PERCENT=99 \
  DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 \
  scripts/disk-pressure-guard.sh --dry-run || true)
[[ -s "$state/tier" && -s "$state/report" ]]
[[ $out == *"$root bytes_free_pct="* ]]

if DISK_GUARD_STATE_DIR="$root/bad" DISK_GUARD_WARN_PERCENT=5 \
  DISK_GUARD_STOP_NEW_PERCENT=10 DISK_GUARD_STOP_WRITERS_PERCENT=1 \
  scripts/disk-pressure-guard.sh >/dev/null 2>&1; then
  echo 'invalid threshold ordering accepted' >&2; exit 1
fi

mkdir -p "$root/link-target"
ln -s "$root/link-target" "$root/link"
DISK_GUARD_STATE_DIR="$root/symlink-state" DISK_GUARD_MOUNTS="$root/link" \
  scripts/disk-pressure-guard.sh >/dev/null

echo PASS
