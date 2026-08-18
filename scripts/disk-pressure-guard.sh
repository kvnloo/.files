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
case $#:$* in
  0:) ;;
  1:--dry-run) DRY_RUN=true ;;
  *) printf 'usage: %s [--dry-run]\n' "$0" >&2; printf 'tier=unknown reason=invalid-arguments\n' >&2; exit 2 ;;
esac

state_ready=false
publish_snapshot() {
  local snapshot_tier=$1 snapshot_report=$2 reason=${3:-}
  SNAPSHOT_TIER=$snapshot_tier SNAPSHOT_REPORT=$snapshot_report SNAPSHOT_REASON=$reason \
    python3 - "$STATE_DIR" <<'PY'
import hashlib, json, os, sys, tempfile
root = sys.argv[1]
current = os.path.join(root, "current.json")
generation = 1
try:
    with open(current, "rb") as f:
        previous = json.load(f)
    generation = int(previous.get("generation", 0)) + 1
except FileNotFoundError:
    pass
payload = {
    "generation": generation,
    "report": os.environ["SNAPSHOT_REPORT"],
    "tier": os.environ["SNAPSHOT_TIER"],
}
reason = os.environ.get("SNAPSHOT_REASON", "")
if reason:
    payload["reason"] = reason
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
fd, tmp = tempfile.mkstemp(prefix=".snapshot.", dir=root)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    if os.environ.get("DISK_GUARD_TEST_PUBLISH_FAIL") == "enospc":
        raise OSError(28, "No space left on device")
    os.replace(tmp, current)
    dfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
except BaseException:
    try: os.close(fd)
    except OSError: pass
    try: os.unlink(tmp)
    except OSError: pass
    raise
PY
}
fail() {
  local reason=$1 rc=${2:-3}
  if $state_ready; then
    publish_snapshot unknown "reason=$reason" "$reason" 2>/dev/null || true
  fi
  printf 'tier=unknown reason=%s\n' "$reason" >&2
  exit "$rc"
}

for n in "$WARN_PERCENT" "$STOP_NEW_PERCENT" "$STOP_WRITERS_PERCENT"; do
  [[ $n =~ ^[0-9]+$ ]] && (( n >= 1 && n <= 99 )) || fail "invalid-threshold:$n" 2
done
(( WARN_PERCENT > STOP_NEW_PERCENT && STOP_NEW_PERCENT > STOP_WRITERS_PERCENT )) || fail invalid-threshold-order 2
[[ $STATE_DIR == "$STATE_PARENT"/* && $STATE_DIR != "$STATE_PARENT/"*/* ]] || fail state-outside-allowlisted-parent

# The installer/tmpfiles phase creates STATE_PARENT. The guard creates only its direct leaf.
# Catch every setup error here so an unavailable state root yields a stable stderr receipt.
if ! python3 - "$STATE_PARENT" "$STATE_DIR" <<'PY'
import os, stat, sys
parent, leaf = map(os.path.abspath, sys.argv[1:])
uid = os.geteuid()
try:
    cur = os.sep
    for part in parent.split(os.sep):
        if not part: continue
        cur = os.path.join(cur, part)
        st = os.lstat(cur)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode): raise ValueError("path-component")
    st = os.lstat(parent)
    if st.st_uid != uid or st.st_mode & 0o077: raise ValueError("parent-owner-or-mode")
    try: os.mkdir(leaf, 0o700)
    except FileExistsError: pass
    st = os.lstat(leaf)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode): raise ValueError("leaf-type")
    if st.st_uid != uid or st.st_mode & 0o077: raise ValueError("leaf-owner-or-mode")
    if os.path.dirname(os.path.realpath(leaf)) != os.path.realpath(parent): raise ValueError("containment")
    if os.stat(leaf).st_dev != os.stat(parent).st_dev: raise ValueError("mount-boundary")
except BaseException:
    raise SystemExit(1)
PY
then
  printf 'tier=unknown reason=unsafe-or-unavailable-state\n' >&2
  exit 3
fi
state_ready=true

LOCK_DIR=$STATE_DIR/.lock
if ! mkdir -m 700 -- "$LOCK_DIR" 2>/dev/null; then fail concurrent-run 75; fi
cleanup() { rm -f -- "$STATE_DIR"/.snapshot.$$*; rmdir -- "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

tier=ok
report=""
declare -a checked=()
validate_target() {
  local spec=$1 path source fstype extra actual actual_target actual_source actual_fstype
  IFS='|' read -r path source fstype extra <<<"$spec"
  [[ -n $path && -n $source && -n $fstype && -z ${extra:-} && $path == /* ]] || fail "malformed-target:$spec" 2
  actual=$(findmnt -rn -o TARGET,SOURCE,FSTYPE --target "$path" 2>/dev/null) || fail "target-missing:$path"
  [[ $(wc -l <<<"$actual") -eq 1 ]] || fail "target-ambiguous:$path"
  read -r actual_target actual_source actual_fstype <<<"$actual"
  [[ $actual_target == "$path" ]] || fail "target-not-mountpoint:$path:$actual_target"
  [[ $source == '*' || $actual_source == "$source" ]] || fail "target-wrong-device:$path:$actual_source"
  [[ $fstype == '*' || $actual_fstype == "$fstype" ]] || fail "target-wrong-filesystem:$path:$actual_fstype"
  VALIDATED_SOURCE=$actual_source VALIDATED_FSTYPE=$actual_fstype
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
  report+=$(printf '%s source=%s filesystem=%s bytes_free_pct=%s inodes_free_pct=%s tier=%s' "$mount" "$VALIDATED_SOURCE" "$VALIDATED_FSTYPE" "$byte_pct" "$inode_pct" "$current")$'\n'
done
((${#checked[@]} > 0)) || fail no-targets 2

if [[ -n ${DISK_GUARD_TEST_BEFORE_WRITE:-} ]]; then "$DISK_GUARD_TEST_BEFORE_WRITE"; fi
for spec in "${checked[@]}"; do validate_target "$spec"; done

# Phase one: validate the complete allowlist into an immutable array. No stop can
# occur until ownership, mode, syntax, empties, and duplicates all pass.
declare -a stop_units=()
if [[ $tier == stop-runaway-writers && ( -e $UNIT_ALLOWLIST || -L $UNIT_ALLOWLIST ) ]]; then
  validated=$(
    python3 - "$UNIT_ALLOWLIST" <<'PY'
import os, re, signal, stat, subprocess, sys
p = sys.argv[1]; uid = os.geteuid(); seen = set(); units = []
try:
    before = os.lstat(p)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != uid or
            before.st_mode & 0o077 or before.st_nlink != 1):
        raise ValueError()
    hook = os.environ.get("DISK_GUARD_TEST_ALLOWLIST_AFTER_LSTAT")
    if hook:
        subprocess.run([hook], check=True, timeout=2)
    signal.alarm(2)
    fd = os.open(p, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        after = os.fstat(fd)
        identity = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")
        if (not stat.S_ISREG(after.st_mode) or
                any(getattr(before, key) != getattr(after, key) for key in identity) or
                after.st_size > 65536):
            raise ValueError()
        data = bytearray()
        while len(data) <= 65536:
            chunk = os.read(fd, min(8192, 65537 - len(data)))
            if not chunk: break
            data.extend(chunk)
        if len(data) > 65536: raise ValueError()
    finally:
        os.close(fd)
        signal.alarm(0)
    lines = bytes(data).decode("utf-8").splitlines()
    for raw in lines:
        if not raw or raw != raw.strip() or raw.startswith("#"): raise ValueError()
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]+\.service", raw) or raw in seen: raise ValueError()
        seen.add(raw); units.append(raw)
except BaseException:
    raise SystemExit(1)
print("\n".join(units))
PY
  ) || fail invalid-allowlist 2
  mapfile -t parsed_units <<<"$validated"
  [[ -n $validated ]] || parsed_units=()
  stop_units=("${parsed_units[@]}")
fi
readonly stop_units

printf '%s' "$report"
publish_snapshot "$tier" "$report" 2>/dev/null || fail snapshot-publish-failed

# Phase two: side effects only after complete validation and authoritative publication.
for unit in "${stop_units[@]}"; do
  if $DRY_RUN; then printf 'would-stop %s\n' "$unit"; else systemctl --user stop -- "$unit"; fi
done
[[ $tier == ok || $tier == warn ]]
