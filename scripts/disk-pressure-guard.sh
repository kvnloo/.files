#!/usr/bin/env bash
set -euo pipefail
umask 077

WARN_PERCENT=${DISK_GUARD_WARN_PERCENT:-15}
STOP_NEW_PERCENT=${DISK_GUARD_STOP_NEW_PERCENT:-10}
STOP_WRITERS_PERCENT=${DISK_GUARD_STOP_WRITERS_PERCENT:-5}
STATE_PARENT=${DISK_GUARD_STATE_PARENT:-${XDG_STATE_HOME:-$HOME/.local/state}}
STATE_DIR=${DISK_GUARD_STATE_DIR:-$STATE_PARENT/disk-pressure-guard}
UNIT_ALLOWLIST=${DISK_GUARD_UNIT_ALLOWLIST:-${XDG_CONFIG_HOME:-$HOME/.config}/disk-pressure-guard/stop-units}
TARGETS=${DISK_GUARD_TARGETS:-'/|/dev/nvme0n1p1|xfs /workspace|/dev/nvme0n1p3|xfs'}
DRY_RUN=false
[[ ${1:-} == --dry-run ]] && DRY_RUN=true
[[ $# -le 1 ]] || { printf 'usage: %s [--dry-run]\n' "$0" >&2; exit 2; }

fail() { printf 'tier=unknown reason=%s\n' "$1" >&2; exit "${2:-3}"; }
for n in "$WARN_PERCENT" "$STOP_NEW_PERCENT" "$STOP_WRITERS_PERCENT"; do
  [[ $n =~ ^[0-9]+$ ]] && (( n >= 1 && n <= 99 )) || fail "invalid-threshold:$n" 2
done
(( WARN_PERCENT > STOP_NEW_PERCENT && STOP_NEW_PERCENT > STOP_WRITERS_PERCENT )) || fail invalid-threshold-order 2
[[ $STATE_DIR == "$STATE_PARENT"/* && $STATE_DIR != "$STATE_PARENT/"*/* ]] || fail state-outside-allowlisted-parent

# Refuse symlinks, foreign ownership, non-directories, and group/world access in every
# existing state-path component. Creation is confined to one allowlisted real parent.
python3 - "$STATE_PARENT" "$STATE_DIR" <<'PY' || exit $?
import os, stat, sys
parent, leaf = sys.argv[1:]
uid = os.geteuid()
def reject(reason):
    print(f"tier=unknown reason=unsafe-state:{reason}", file=sys.stderr); raise SystemExit(3)
p = os.path.abspath(parent)
parts = p.split(os.sep)
cur = os.sep
for part in parts:
    if not part: continue
    cur = os.path.join(cur, part)
    st = os.lstat(cur)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode): reject(cur)
# The allowlisted parent itself must be private and owned; ancestors only need be real dirs.
st = os.lstat(p)
if st.st_uid != uid or st.st_mode & 0o077: reject("parent-owner-or-mode")
try: os.mkdir(leaf, 0o700)
except FileExistsError: pass
st = os.lstat(leaf)
if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or st.st_mode & 0o077:
    reject("leaf-owner-or-mode")
if os.path.dirname(os.path.realpath(leaf)) != os.path.realpath(p): reject("containment")
if os.stat(leaf).st_dev != os.stat(p).st_dev: reject("mount-boundary")
PY

LOCK_DIR=$STATE_DIR/.lock
if ! mkdir -m 700 -- "$LOCK_DIR" 2>/dev/null; then fail concurrent-run 75; fi
tier_tmp=$STATE_DIR/.tier.$$
report_tmp=$STATE_DIR/.report.$$
cleanup() { rm -f -- "$tier_tmp" "$report_tmp"; rmdir -- "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

tier=ok
report=""
declare -a checked=()
validate_target() {
  local spec=$1 path source fstype actual
  IFS='|' read -r path source fstype extra <<<"$spec"
  [[ -n $path && -n $source && -n $fstype && -z ${extra:-} && $path == /* ]] || fail "malformed-target:$spec" 2
  actual=$(findmnt -rn -o TARGET,SOURCE,FSTYPE --target "$path" 2>/dev/null) || fail "target-missing:$path"
  [[ $(wc -l <<<"$actual") -eq 1 ]] || fail "target-ambiguous:$path"
  read -r actual_target actual_source actual_fstype <<<"$actual"
  [[ $actual_target == "$path" ]] || fail "target-not-mountpoint:$path:$actual_target"
  [[ $source == '*' || $actual_source == "$source" ]] || fail "target-wrong-device:$path:$actual_source"
  [[ $fstype == '*' || $actual_fstype == "$fstype" ]] || fail "target-wrong-filesystem:$path:$actual_fstype"
}

for spec in $TARGETS; do
  validate_target "$spec"
  IFS='|' read -r mount _ _ <<<"$spec"
  checked+=("$spec")
  read -r bavail bsize favail ftotal < <(stat -f -c '%a %b %d %c' -- "$mount") || fail "stat-failed:$mount"
  (( bsize > 0 )) || fail "invalid-block-count:$mount"
  byte_pct=$(( bavail * 100 / bsize ))
  inode_pct=$(( ftotal == 0 ? 100 : favail * 100 / ftotal ))
  free_pct=$byte_pct; (( inode_pct < free_pct )) && free_pct=$inode_pct
  current=ok
  (( free_pct <= WARN_PERCENT )) && current=warn
  (( free_pct <= STOP_NEW_PERCENT )) && current=stop-new-heavy-work
  (( free_pct <= STOP_WRITERS_PERCENT )) && current=stop-runaway-writers
  case "$current" in
    stop-runaway-writers) tier=stop-runaway-writers ;;
    stop-new-heavy-work) [[ $tier == stop-runaway-writers ]] || tier=stop-new-heavy-work ;;
    warn) [[ $tier == ok ]] && tier=warn ;;
  esac
  report+=$(printf '%s source=%s filesystem=%s bytes_free_pct=%s inodes_free_pct=%s tier=%s' "$mount" "$actual_source" "$actual_fstype" "$byte_pct" "$inode_pct" "$current")$'\n'
done
((${#checked[@]} > 0)) || fail no-targets 2

# Test-only hook permits deterministic disappearance/interruption/ENOSPC fixtures.
if [[ -n ${DISK_GUARD_TEST_BEFORE_WRITE:-} ]]; then "$DISK_GUARD_TEST_BEFORE_WRITE"; fi
for spec in "${checked[@]}"; do validate_target "$spec"; done
printf '%s' "$report"
printf '%s\n' "$tier" >"$tier_tmp" || fail tier-write-failed
printf '%s' "$report" >"$report_tmp" || fail report-write-failed
chmod 600 -- "$tier_tmp" "$report_tmp"
mv -fT -- "$tier_tmp" "$STATE_DIR/tier" || fail tier-publish-failed
mv -fT -- "$report_tmp" "$STATE_DIR/report" || fail report-publish-failed

if [[ $tier == stop-runaway-writers && -f $UNIT_ALLOWLIST && ! -L $UNIT_ALLOWLIST ]]; then
  while IFS= read -r unit; do
    [[ -z $unit || $unit == \#* ]] && continue
    [[ $unit =~ ^[A-Za-z0-9_.@:-]+\.service$ ]] || fail "invalid-allowlist-entry:$unit" 2
    if $DRY_RUN; then printf 'would-stop %s\n' "$unit"; else systemctl --user stop -- "$unit"; fi
  done <"$UNIT_ALLOWLIST"
fi
[[ $tier == ok || $tier == warn ]]
