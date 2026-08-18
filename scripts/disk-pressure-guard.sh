#!/usr/bin/env bash
set -euo pipefail

WARN_PERCENT=${DISK_GUARD_WARN_PERCENT:-15}
STOP_NEW_PERCENT=${DISK_GUARD_STOP_NEW_PERCENT:-10}
STOP_WRITERS_PERCENT=${DISK_GUARD_STOP_WRITERS_PERCENT:-5}
STATE_DIR=${DISK_GUARD_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/disk-pressure-guard}
UNIT_ALLOWLIST=${DISK_GUARD_UNIT_ALLOWLIST:-${XDG_CONFIG_HOME:-$HOME/.config}/disk-pressure-guard/stop-units}
MOUNTS=${DISK_GUARD_MOUNTS:-"/ /workspace"}
DRY_RUN=false
[[ ${1:-} == --dry-run ]] && DRY_RUN=true

for n in "$WARN_PERCENT" "$STOP_NEW_PERCENT" "$STOP_WRITERS_PERCENT"; do
  [[ $n =~ ^[0-9]+$ ]] && (( n >= 1 && n <= 99 )) || { printf 'invalid threshold: %s\n' "$n" >&2; exit 2; }
done
(( WARN_PERCENT > STOP_NEW_PERCENT && STOP_NEW_PERCENT > STOP_WRITERS_PERCENT )) || {
  echo 'thresholds must satisfy warn > stop-new > stop-writers' >&2; exit 2;
}

mkdir -p -- "$STATE_DIR"
exec 9>"$STATE_DIR/lock"
flock -n 9 || exit 0

tier=ok
report=""
for mount in $MOUNTS; do
  [[ -d $mount ]] || continue
  read -r bavail bsize favail ftotal < <(stat -f -c '%a %b %d %c' -- "$mount")
  byte_pct=$(( bsize == 0 ? 0 : bavail * 100 / bsize ))
  inode_pct=$(( ftotal == 0 ? 100 : favail * 100 / ftotal ))
  free_pct=$byte_pct
  (( inode_pct < free_pct )) && free_pct=$inode_pct
  current=ok
  (( free_pct <= WARN_PERCENT )) && current=warn
  (( free_pct <= STOP_NEW_PERCENT )) && current=stop-new-heavy-work
  (( free_pct <= STOP_WRITERS_PERCENT )) && current=stop-runaway-writers
  case "$current" in
    stop-runaway-writers) tier=stop-runaway-writers ;;
    stop-new-heavy-work) [[ $tier == stop-runaway-writers ]] || tier=stop-new-heavy-work ;;
    warn) [[ $tier == ok ]] && tier=warn ;;
  esac
  report+=$(printf '%s bytes_free_pct=%s inodes_free_pct=%s tier=%s' "$mount" "$byte_pct" "$inode_pct" "$current")
  report+=$'\n'
done

printf '%s' "$report"
printf '%s\n' "$tier" >"$STATE_DIR/tier.new"
mv -f -- "$STATE_DIR/tier.new" "$STATE_DIR/tier"
printf '%s' "$report" >"$STATE_DIR/report.new"
mv -f -- "$STATE_DIR/report.new" "$STATE_DIR/report"

if [[ $tier == stop-runaway-writers && -s $UNIT_ALLOWLIST ]]; then
  while IFS= read -r unit; do
    [[ $unit =~ ^[A-Za-z0-9_.@:-]+\.service$ ]] || continue
    if $DRY_RUN; then printf 'would-stop %s\n' "$unit"; else systemctl --user stop -- "$unit"; fi
  done <"$UNIT_ALLOWLIST"
fi

[[ $tier == ok || $tier == warn ]]
