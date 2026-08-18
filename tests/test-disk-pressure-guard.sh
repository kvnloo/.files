#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
mkdir -m 700 "$root/state-parent" "$root/bin"
real_stat=$(command -v stat)
real_mv=$(command -v mv)
cat >"$root/bin/findmnt" <<'EOF'
#!/usr/bin/env bash
path=${*: -1}
[[ -e ${MOUNT_GONE_FILE:-/nonexistent} ]] && exit 1
[[ $path == "${FIXTURE_MOUNT:-}" ]] || { printf '/fallback /dev/parent ext4\n'; exit 0; }
printf '%s %s %s\n' "$path" "${FIXTURE_SOURCE:-/dev/test}" "${FIXTURE_FSTYPE:-xfs}"
EOF
cat >"$root/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$SYSTEMCTL_LOG"
EOF
chmod 700 "$root/bin/findmnt" "$root/bin/systemctl"
mount="$root/mount"; mkdir "$mount"
base=(env PATH="$root/bin:$PATH" DISK_GUARD_STATE_PARENT="$root/state-parent" DISK_GUARD_STATE_DIR="$root/state-parent/guard" DISK_GUARD_TARGETS="$mount|/dev/test|xfs" FIXTURE_MOUNT="$mount")
run() { "${base[@]}" "$repo/scripts/disk-pressure-guard.sh" "$@"; }
expect_fail() { local name=$1; shift; if "$@" >"$root/out" 2>"$root/err"; then echo "FAIL $name: accepted" >&2; exit 1; fi; grep -q 'tier=unknown\|tier=critical' "$root/err" || { echo "FAIL $name: no unknown receipt" >&2; exit 1; }; }

# Healthy execution, atomic modes, dry-run, and idempotence.
run >/dev/null
[[ $(stat -c %a "$root/state-parent/guard") == 700 ]]
[[ $(stat -c %a "$root/state-parent/guard/tier") == 600 ]]
first=$(sha256sum "$root/state-parent/guard/tier" "$root/state-parent/guard/report")
run --dry-run >/dev/null
[[ $first == "$(sha256sum "$root/state-parent/guard/tier" "$root/state-parent/guard/report")" ]]

expect_fail missing-mount env "${base[@]}" FIXTURE_MOUNT=/missing "$repo/scripts/disk-pressure-guard.sh"
expect_fail wrong-device env "${base[@]}" FIXTURE_SOURCE=/dev/wrong "$repo/scripts/disk-pressure-guard.sh"
expect_fail wrong-filesystem env "${base[@]}" FIXTURE_FSTYPE=ext4 "$repo/scripts/disk-pressure-guard.sh"
expect_fail malformed-config env "${base[@]}" DISK_GUARD_TARGETS=broken "$repo/scripts/disk-pressure-guard.sh"
expect_fail empty-config env "${base[@]}" DISK_GUARD_TARGETS=' ' "$repo/scripts/disk-pressure-guard.sh"

# Unsafe state parent, leaf symlink, ownership/mode policy.
mkdir -m 700 "$root/foreign"; mkdir -m 700 "$root/real-parent"
ln -s "$root/real-parent" "$root/parent-link"
expect_fail symlink-parent env "${base[@]}" DISK_GUARD_STATE_PARENT="$root/parent-link" DISK_GUARD_STATE_DIR="$root/parent-link/guard" "$repo/scripts/disk-pressure-guard.sh"
rm -rf "$root/state-parent/guard"; ln -s "$root/foreign" "$root/state-parent/guard"
expect_fail symlink-leaf run
rm "$root/state-parent/guard"; chmod 755 "$root/state-parent"
expect_fail unsafe-permissions run
chmod 700 "$root/state-parent"; run >/dev/null

# Concurrent lock fails closed while the first process is paused.
cat >"$root/pause" <<EOF
#!/usr/bin/env bash
touch "$root/paused"; while [[ ! -e "$root/release" ]]; do sleep 0.05; done
EOF
chmod 700 "$root/pause"
env "${base[@]:1}" DISK_GUARD_TEST_BEFORE_WRITE="$root/pause" "$repo/scripts/disk-pressure-guard.sh" >"$root/bg.out" 2>"$root/bg.err" & bg=$!
for _ in {1..100}; do [[ -e $root/paused ]] && break; sleep 0.02; done
expect_fail concurrent run
touch "$root/release"; wait "$bg"

# Mount disappears after measurement; prior published state remains intact.
old=$(sha256sum "$root/state-parent/guard/tier" "$root/state-parent/guard/report")
cat >"$root/disappear" <<EOF
#!/usr/bin/env bash
touch "$root/gone"
EOF
chmod 700 "$root/disappear"
expect_fail mount-race env "${base[@]}" MOUNT_GONE_FILE="$root/gone" DISK_GUARD_TEST_BEFORE_WRITE="$root/disappear" "$repo/scripts/disk-pressure-guard.sh"
[[ $old == "$(sha256sum "$root/state-parent/guard/tier" "$root/state-parent/guard/report")" ]]
rm -f "$root/gone"

# Interrupted pre-publish write leaves old state and removes temporary files.
cat >"$root/interrupt" <<'EOF'
#!/usr/bin/env bash
kill -TERM "$PPID"
EOF
chmod 700 "$root/interrupt"
if env "${base[@]}" DISK_GUARD_TEST_BEFORE_WRITE="$root/interrupt" "$repo/scripts/disk-pressure-guard.sh" >"$root/out" 2>"$root/err"; then
  echo 'FAIL interrupted: accepted' >&2; exit 1
fi
[[ $old == "$(sha256sum "$root/state-parent/guard/tier" "$root/state-parent/guard/report")" ]]
! compgen -G "$root/state-parent/guard/.tier.*" >/dev/null

# Deterministic report publish failure (ENOSPC equivalent) is nonzero and preserves old report.
cat >"$root/bin/mv" <<EOF
#!/usr/bin/env bash
[[ \${*: -1} == */report ]] && { echo 'No space left on device' >&2; exit 1; }
exec "$real_mv" "\$@"
EOF
chmod 700 "$root/bin/mv"
expect_fail enospc-report run
rm "$root/bin/mv"

# Inode exhaustion signal: zero available inodes drives stop tier and never deletes.
cat >"$root/bin/stat" <<EOF
#!/usr/bin/env bash
if [[ \$1 == -f ]]; then printf '100 100 0 100\n'; else exec "$real_stat" "\$@"; fi
EOF
chmod 700 "$root/bin/stat"
SYSTEMCTL_LOG="$root/systemctl.log" run --dry-run >"$root/inode.out" || true
grep -q 'inodes_free_pct=0 tier=stop-runaway-writers' "$root/inode.out"
[[ ! -e $root/systemctl.log ]]
rm "$root/bin/stat"

# Exact allowlist only; malformed entries fail closed and empty default stops nothing.
printf 'fixture-writer.service\n' >"$root/allow"
SYSTEMCTL_LOG="$root/systemctl.log" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_UNIT_ALLOWLIST="$root/allow" run --dry-run >"$root/allow.out" || true
grep -qx 'would-stop fixture-writer.service' < <(grep would-stop "$root/allow.out")
printf '../bad.service\n' >"$root/allow"
expect_fail malformed-allowlist env "${base[@]}" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_UNIT_ALLOWLIST="$root/allow" "$repo/scripts/disk-pressure-guard.sh"

echo PASS
