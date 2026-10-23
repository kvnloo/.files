#!/usr/bin/env bash
# Keep bulk data off the root disk. Declarative and idempotent; never run by
# ./scripts/onboard.
#
#        scripts/setup-storage.sh plan            show drift from config/storage/<host>/
#   sudo scripts/setup-storage.sh apply           converge (copies data, edits fstab, mounts)
#   sudo scripts/setup-storage.sh cleanup --yes   delete <path>.old* copies once the bind mount is live
#        scripts/setup-storage.sh check           offline validation
#
# Managed state, all from config/storage/<host>/:
#   *.mount                -> /etc/systemd/system/
#   docker-daemon.json     -> /etc/docker/daemon.json
#   relocations.conf       -> /etc/fstab bind lines + systemd RequiresMountsFor drop-ins
# Every file it replaces is backed up as <file>.bak.<timestamp> first.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${STORAGE_HOST:-$(hostname)}"
CFG="$REPO/config/storage/$HOST"
DROPIN=10-z0-storage.conf
FSTAB=/etc/fstab
TS=$(date +%Y%m%d%H%M%S)
DRIFT=0

die() { echo "setup-storage: $*" >&2; exit 1; }
say() { echo "==> $*"; }
ok() { echo "  ok     $*"; }
drift() { echo "  DRIFT  $*"; DRIFT=1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run with sudo"; }
[ -d "$CFG" ] || die "no storage config for host '$HOST' ($CFG)"

# --- config parsing -------------------------------------------------------
binds() { awk '$1=="bind"{print $2, $3}' "$CFG/relocations.conf"; }
bind_services() { awk -v p="$1" '$1=="bind" && $2==p {for(i=4;i<=NF;i++) print $i}' "$CFG/relocations.conf"; }
required_services() { awk '$1=="require"{print $2}' "$CFG/relocations.conf" | sort -u; }
required_paths() { awk -v s="$1" '$1=="require" && $2==s {print $3}' "$CFG/relocations.conf"; }

fstab_line() { echo "$2 $1 none bind,x-systemd.requires-mounts-for=$(dirname "$2") 0 0"; }
is_bound() { [ -d "$1" ] && [ -d "$2" ] && [ "$(stat -c %d:%i "$1")" = "$(stat -c %d:%i "$2")" ]; }
dropin_body() {
  echo "# Managed by .files scripts/setup-storage.sh. Do not edit."
  echo "[Unit]"
  required_paths "$1" | while read -r p; do echo "RequiresMountsFor=$p"; done
}

# Install $2 at $1 only if it differs. Prints changed|same.
put_file() {
  local dst=$1 src=$2 mode=${3:-0644}
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then echo same; return; fi
  [ -f "$dst" ] && cp -a "$dst" "$dst.bak.$TS"
  install -D -m "$mode" "$src" "$dst"; echo changed
}

# --- plan -----------------------------------------------------------------
cmd_plan() {
  say "storage plan for $HOST"
  local u name
  for u in "$CFG"/*.mount; do
    [ -e "$u" ] || continue; name=$(basename "$u")
    if cmp -s "$u" "/etc/systemd/system/$name"; then ok "$name installed"; else drift "$name differs or missing"; fi
    if systemctl is-active -q "$name"; then ok "$name active"; else drift "$name not active"; fi
  done
  if [ -f "$CFG/docker-daemon.json" ]; then
    if cmp -s "$CFG/docker-daemon.json" /etc/docker/daemon.json; then ok "docker daemon.json"; else drift "docker daemon.json differs"; fi
  fi
  local path target
  while read -r path target; do
    if grep -Fqx "$(fstab_line "$path" "$target")" $FSTAB; then ok "fstab: $path"; else drift "fstab line missing for $path"; fi
    if is_bound "$path" "$target"; then ok "$path is bound to $target"; else drift "$path is not bound to $target"; fi
    compgen -G "$path.old*" >/dev/null && echo "  note   old copy present: $(compgen -G "$path.old*" | tr '\n' ' ')(run cleanup --yes)"
  done < <(binds)
  local s f
  for s in $(required_services); do
    f=/etc/systemd/system/$s.d/$DROPIN
    if [ -f "$f" ] && [ "$(cat "$f")" = "$(dropin_body "$s")" ]; then ok "$s waits for its mounts"; else drift "$s drop-in missing or stale"; fi
  done
  [ $DRIFT -eq 0 ] && say "no drift" || say "drift found; run: sudo $0 apply"
  return 0
}

# --- apply ----------------------------------------------------------------
stop_units() {
  local s
  for s in "$@"; do
    # Socket activation would restart the service mid-copy.
    systemctl list-unit-files "${s%.service}.socket" >/dev/null 2>&1 && systemctl stop "${s%.service}.socket" || true
    systemctl stop "$s" || true
  done
}
start_units() {
  local s
  for s in "$@"; do
    systemctl list-unit-files "${s%.service}.socket" >/dev/null 2>&1 && systemctl start "${s%.service}.socket" || true
  done
  for s in "$@"; do systemctl start "$s"; done
}

relocate() {
  local path=$1 target=$2 line services
  line=$(fstab_line "$path" "$target")
  mapfile -t services < <(bind_services "$path")
  if is_bound "$path" "$target"; then
    ok "$path already bound"
  else
    say "relocating $path -> $target (stopping: ${services[*]})"
    stop_units "${services[@]}"
    install -d "$target"
    if [ -d "$path" ] && [ -n "$(ls -A "$path")" ]; then
      rsync -aHAX --numeric-ids "$path/" "$target/"
      # Second pass must find nothing left to copy, or we stop here.
      [ -z "$(rsync -aHAXn --numeric-ids --itemize-changes "$path/" "$target/")" ] || die "copy of $path is not complete; nothing moved"
      local old="$path.old"; [ -e "$old" ] && old="$path.old.$TS"
      mv "$path" "$old"; say "old copy kept at $old"
      install -d -m "$(stat -c %a "$target")" "$path"
    else
      install -d "$path"
    fi
  fi
  if ! grep -Fqx "$line" $FSTAB; then
    grep -qE "^[^#]*[[:space:]]$path[[:space:]]" $FSTAB && die "$FSTAB already has a different entry for $path; fix it by hand"
    cp -a $FSTAB "$FSTAB.bak.$TS"; echo "$line" >>$FSTAB; say "fstab: added $path"
  fi
  systemctl daemon-reload
  is_bound "$path" "$target" || mount "$path"
  is_bound "$path" "$target" || die "$path did not bind to $target"
}

cmd_apply() {
  need_root
  local u name changed=0
  for u in "$CFG"/*.mount; do
    [ -e "$u" ] || continue; name=$(basename "$u")
    [ "$(put_file "/etc/systemd/system/$name" "$u")" = changed ] && changed=1
    systemctl daemon-reload; systemctl enable --now "$name" >/dev/null
  done
  if [ -f "$CFG/docker-daemon.json" ]; then
    python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$CFG/docker-daemon.json" || die "bad docker-daemon.json"
    if [ "$(put_file /etc/docker/daemon.json "$CFG/docker-daemon.json")" = changed ]; then
      say "docker daemon.json changed; restarting docker"; systemctl restart docker
    fi
  fi
  local s tmp restart=()
  for s in $(required_services); do
    tmp=$(mktemp); dropin_body "$s" >"$tmp"
    [ "$(put_file "/etc/systemd/system/$s.d/$DROPIN" "$tmp")" = changed ] && say "$s now waits for: $(required_paths "$s" | tr '\n' ' ')"
    rm -f "$tmp"
  done
  systemctl daemon-reload
  local path target
  while read -r path target; do relocate "$path" "$target"; done < <(binds)
  # Bring back anything a relocation stopped.
  while read -r path target; do
    mapfile -t restart < <(bind_services "$path")
    for s in "${restart[@]}"; do systemctl is-enabled -q "$s" 2>/dev/null && ! systemctl is-active -q "$s" && start_units "$s"; done
  done < <(binds)
  DRIFT=0; cmd_plan
}

cmd_cleanup() {
  need_root
  [ "${1:-}" = "--yes" ] || die "this deletes <path>.old* copies; re-run with --yes"
  local path target o
  while read -r path target; do
    is_bound "$path" "$target" || { say "skip $path: not bound yet"; continue; }
    for o in $(compgen -G "$path.old*" || true); do
      say "removing $o ($(du -sh "$o" | cut -f1))"; rm -rf --one-file-system "$o"
    done
  done < <(binds)
}

cmd_check() {
  bash -n "$0" && say "script syntax ok"
  [ -f "$CFG/relocations.conf" ] || die "missing relocations.conf"
  awk '!/^[[:space:]]*(#|$)/ && !(($1=="bind" && NF>=4) || ($1=="require" && NF==3)) {print "bad line " NR ": " $0; bad=1} END{exit bad}' "$CFG/relocations.conf" || die "bad relocations.conf"
  [ ! -f "$CFG/docker-daemon.json" ] || python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$CFG/docker-daemon.json"
  local u; for u in "$CFG"/*.mount; do [ -e "$u" ] && { systemd-analyze verify "$u" 2>&1 | grep -v "^$" || true; }; done
  say "config ok"
}

case "${1:-}" in
  plan|"") cmd_plan ;;
  apply) cmd_apply ;;
  cleanup) shift; cmd_cleanup "$@" ;;
  check) cmd_check ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
