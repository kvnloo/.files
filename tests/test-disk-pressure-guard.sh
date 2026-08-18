#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=$(mktemp -d); trap 'rm -rf -- "$root"' EXIT
mkdir -m 700 "$root/state-parent" "$root/bin"; mount="$root/mount"; mkdir "$mount"
real_stat=$(command -v stat)
cat >"$root/bin/findmnt" <<'EOF'
#!/usr/bin/env bash
path=${*: -1}; [[ -e ${MOUNT_GONE_FILE:-/nonexistent} ]] && exit 1
[[ $path == "${FIXTURE_MOUNT:-}" ]] || { printf '/fallback /dev/parent ext4\n'; exit; }
printf '%s %s %s\n' "$path" "${FIXTURE_SOURCE:-/dev/test}" "${FIXTURE_FSTYPE:-xfs}"
EOF
cat >"$root/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$SYSTEMCTL_LOG"
EOF
chmod 700 "$root/bin/"*
base=(env PATH="$root/bin:$PATH" DISK_GUARD_STATE_PARENT="$root/state-parent" DISK_GUARD_STATE_DIR="$root/state-parent/guard" DISK_GUARD_TARGETS="$mount|/dev/test|xfs" FIXTURE_MOUNT="$mount")
run() { "${base[@]}" "$repo/scripts/disk-pressure-guard.sh" "$@"; }
expect_fail() { local n=$1; shift; if "$@" >"$root/out" 2>"$root/err"; then echo "FAIL $n: accepted" >&2; exit 1; fi; grep -q 'tier=unknown' "$root/err" || { echo "FAIL $n: no unknown" >&2; exit 1; }; }
snapshot() { sha256sum "$root/state-parent/guard/current.json"; }

run >/dev/null
[[ $(stat -c %a "$root/state-parent/guard") == 700 && $(stat -c %a "$root/state-parent/guard/current.json") == 600 ]]
python3 -m json.tool "$root/state-parent/guard/current.json" >/dev/null
first=$(snapshot); run --dry-run >/dev/null; [[ $first != "$(snapshot)" ]]
for arg in nonsense --dry-run=1 --; do before=$(snapshot); expect_fail cli run "$arg"; grep -q '^usage:' "$root/err"; [[ $before == "$(snapshot)" ]]; done
before=$(snapshot); expect_fail cli-extra run --dry-run extra; [[ $before == "$(snapshot)" ]]

expect_fail missing-parent env "${base[@]}" DISK_GUARD_STATE_PARENT="$root/missing" DISK_GUARD_STATE_DIR="$root/missing/guard" "$repo/scripts/disk-pressure-guard.sh"; ! grep -q Traceback "$root/err"
printf x >"$root/notdir"; expect_fail notdir env "${base[@]}" DISK_GUARD_STATE_PARENT="$root/notdir" DISK_GUARD_STATE_DIR="$root/notdir/guard" "$repo/scripts/disk-pressure-guard.sh"; ! grep -q Traceback "$root/err"
expect_fail missing-mount env "${base[@]}" FIXTURE_MOUNT=/missing "$repo/scripts/disk-pressure-guard.sh"
expect_fail wrong-device env "${base[@]}" FIXTURE_SOURCE=/dev/wrong "$repo/scripts/disk-pressure-guard.sh"
expect_fail wrong-fs env "${base[@]}" FIXTURE_FSTYPE=ext4 "$repo/scripts/disk-pressure-guard.sh"
expect_fail malformed env "${base[@]}" DISK_GUARD_TARGETS=broken "$repo/scripts/disk-pressure-guard.sh"
expect_fail empty env "${base[@]}" DISK_GUARD_TARGETS=' ' "$repo/scripts/disk-pressure-guard.sh"

mkdir -m 700 "$root/foreign" "$root/real-parent"; ln -s "$root/real-parent" "$root/parent-link"
expect_fail symlink-parent env "${base[@]}" DISK_GUARD_STATE_PARENT="$root/parent-link" DISK_GUARD_STATE_DIR="$root/parent-link/guard" "$repo/scripts/disk-pressure-guard.sh"
rm -rf "$root/state-parent/guard"; ln -s "$root/foreign" "$root/state-parent/guard"; expect_fail symlink-leaf run
rm "$root/state-parent/guard"; chmod 755 "$root/state-parent"; expect_fail mode run; chmod 700 "$root/state-parent"; run >/dev/null

cat >"$root/pause" <<EOF
#!/usr/bin/env bash
touch "$root/paused"; while [[ ! -e "$root/release" ]]; do sleep 0.02; done
EOF
chmod 700 "$root/pause"; env "${base[@]:1}" DISK_GUARD_TEST_BEFORE_WRITE="$root/pause" "$repo/scripts/disk-pressure-guard.sh" >/dev/null 2>&1 & bg=$!
for _ in {1..100}; do [[ -e $root/paused ]] && break; sleep .02; done
expect_fail concurrent run; touch "$root/release"; wait "$bg"

old=$(snapshot); cat >"$root/disappear" <<EOF
#!/usr/bin/env bash
touch "$root/gone"
EOF
chmod 700 "$root/disappear"; expect_fail race env "${base[@]}" MOUNT_GONE_FILE="$root/gone" DISK_GUARD_TEST_BEFORE_WRITE="$root/disappear" "$repo/scripts/disk-pressure-guard.sh"; [[ $old != "$(snapshot)" ]]; rm "$root/gone"
old=$(snapshot); cat >"$root/interrupt" <<'EOF'
#!/usr/bin/env bash
kill -TERM "$PPID"
EOF
chmod 700 "$root/interrupt"; if env "${base[@]}" DISK_GUARD_TEST_BEFORE_WRITE="$root/interrupt" "$repo/scripts/disk-pressure-guard.sh" >"$root/out" 2>"$root/err"; then echo 'FAIL interrupt: accepted' >&2; exit 1; fi; [[ $old == "$(snapshot)" ]]; ! compgen -G "$root/state-parent/guard/.snapshot.*" >/dev/null
old=$(snapshot); expect_fail enospc env "${base[@]}" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_TEST_PUBLISH_FAIL=enospc "$repo/scripts/disk-pressure-guard.sh"; [[ $old == "$(snapshot)" ]]; ! compgen -G "$root/state-parent/guard/.snapshot.*" >/dev/null

cat >"$root/bin/stat" <<EOF
#!/usr/bin/env bash
if [[ \$1 == -f ]]; then printf '100 100 0 100\n'; else exec "$real_stat" "\$@"; fi
EOF
chmod 700 "$root/bin/stat"; run --dry-run >"$root/inode.out" || true; grep -q 'inodes_free_pct=0 tier=stop-runaway-writers' "$root/inode.out"; rm "$root/bin/stat"

# Absent/zero-byte allowlists are disabled; all nonempty files are validated completely.
: >"$root/allow"; chmod 600 "$root/allow"; SYSTEMCTL_LOG="$root/log" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_UNIT_ALLOWLIST="$root/allow" run --dry-run >/dev/null || true; [[ ! -e $root/log ]]
for contents in $'good.service\n../bad.service\n' $'good.service\ngood.service\n' $'good.service\n\n'; do
 printf '%s' "$contents" >"$root/allow"; chmod 600 "$root/allow"; rm -f "$root/log"
 expect_fail allowlist env "${base[@]}" SYSTEMCTL_LOG="$root/log" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_UNIT_ALLOWLIST="$root/allow" "$repo/scripts/disk-pressure-guard.sh"; [[ ! -e $root/log ]]
done
printf 'good.service\n' >"$root/allow"; chmod 644 "$root/allow"; expect_fail allowmode env "${base[@]}" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_UNIT_ALLOWLIST="$root/allow" "$repo/scripts/disk-pressure-guard.sh"
chmod 600 "$root/allow"; SYSTEMCTL_LOG="$root/log" DISK_GUARD_WARN_PERCENT=99 DISK_GUARD_STOP_NEW_PERCENT=98 DISK_GUARD_STOP_WRITERS_PERCENT=97 DISK_GUARD_UNIT_ALLOWLIST="$root/allow" run --dry-run >"$root/a" || true; grep -q '^would-stop good.service$' "$root/a"
python3 - "$root/state-parent/guard/current.json" <<'PY'
import hashlib,json,sys
p=json.load(open(sys.argv[1])); h=p.pop('content_sha256'); assert hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()==h
PY
echo PASS
