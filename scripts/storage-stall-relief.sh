#!/usr/bin/env bash
# Groot storage incident: diagnose; optionally bound background IO or relocate cache.
# No service stops, process kills, discard tuning, quota changes, or source deletion.
set -euo pipefail
umask 077
UUID=3c8b6c35-4d36-4a69-b5f3-df88f07cbd82
MOUNT=/mnt/zer0models
USER_NAME=kvn
USER_ID=$(id -u "$USER_NAME")
HOME_DIR=$(getent passwd "$USER_NAME" | cut -d: -f6)
OLD_CACHE=/mnt/zer0models/home-offload/kvn/offload-2026-09-21/cache
NEW_CACHE=/workspace/home-hot/kvn/cache
STATE=/run/storage-stall-relief
MODE=diagnose
QUIESCED=false
usage() {
    printf '%s\n' 'Usage: sudo bash scripts/storage-stall-relief.sh [--diagnose|--limit-background|--restore-background|--move-cache] [--writers-quiesced]' \
        'Default: fresh read-only SMART/Btrfs diagnostics.' \
        '--limit-background: reversible runtime-only SATA caps; preserves tighter limits.' \
        '--restore-background: restore only the device limits saved by this script.' \
        '--move-cache --writers-quiesced: copy, checksum-compare, then atomically repoint ~/.cache.' \
        'The last flag asserts YOU closed cache writers first; the script never stops them.'
}
for arg in "$@"; do
    case "$arg" in
        --diagnose) MODE=diagnose ;;
        --limit-background) MODE=limit ;;
        --restore-background) MODE=restore ;;
        --move-cache) MODE=move ;;
        --writers-quiesced) QUIESCED=true ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
[[ $EUID == 0 ]] || { printf 'Run with sudo.\n' >&2; exit 1; }
[[ $(findmnt -n -o UUID -T "$MOUNT") == "$UUID" ]] || { printf 'Wrong capacity filesystem; refusing.\n' >&2; exit 1; }
DEVICE=$(findmnt -n -o SOURCE -T "$MOUNT")
DEVICE=${DEVICE%%\[*}
DISK=$(lsblk -ndo PKNAME "$DEVICE")
[[ $DISK == sdb ]] || { printf 'Device mapping changed; review before proceeding.\n' >&2; exit 1; }
mkdir -p "$STATE"
chmod 700 "$STATE"
exec 9>"$STATE/lock"
flock -n 9 || { printf 'Another storage operation is running.\n' >&2; exit 1; }
as_user() { runuser -u "$USER_NAME" -- env XDG_RUNTIME_DIR="/run/user/$USER_ID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus" "$@"; }
read_diagnostics() {
    local rc=0
    date -Is
    # smartctl is a bitmask: report health errors without skipping later diagnostics.
    timeout -k 2 20 smartctl -a "/dev/$DISK" || rc=$?
    printf 'smartctl exit bitmask: %s\n' "$rc"
    timeout -k 2 15 btrfs filesystem usage -b "$MOUNT" || true
    timeout -k 2 15 btrfs device stats "$MOUNT" || true
    timeout -k 2 15 btrfs balance status "$MOUNT" || true
    timeout -k 2 15 btrfs qgroup show "$MOUNT" || true
    cat "/sys/fs/btrfs/$UUID/commit_stats" /proc/pressure/io /proc/pressure/memory
    free -h
    swapon --show
}
if [[ $MODE == diagnose ]]; then
    read_diagnostics
    exit 0
fi
if [[ $MODE == limit || $MODE == restore ]]; then
    DEVNO=$(lsblk -dn -o MAJ:MIN "/dev/$DISK")
    BASE="/sys/fs/cgroup/user.slice/user-$USER_ID.slice/user@$USER_ID.service"
    # Never cap the graphical/session slice: OMP and Tern share it with the desktop.
    for unit in agent.slice ctx.service agent-telemetry-refresh.service; do
        cg=$(as_user systemctl --user show "$unit" -p ControlGroup --value)
        [[ -n $cg ]] || continue
        file="/sys/fs/cgroup$cg/io.max"
        [[ -f $file && $file == "$BASE/"* ]] || { printf 'No delegated IO controller for %s; skipped.\n' "$unit"; continue; }
        save="$STATE/$unit.io.max"
        current=""
        while IFS= read -r line; do
            [[ $line == "$DEVNO "* ]] && current=$line
        done < "$file"
        if [[ $MODE == restore ]]; then
            [[ -f $save ]] || continue
            # Saved control-group path prevents restoring a recreated/different unit.
            IFS= read -r saved_file < "$save"
            [[ $saved_file == "$file" ]] || { printf 'Control group changed: %s; skipped.\n' "$unit"; continue; }
            saved=$(<"$save.values")
            printf '%s\n' "$saved" > "$file"
            rm -- "$save" "$save.values"
            printf 'Restored runtime SATA limits: %s\n' "$unit"
            continue
        fi
        [[ -f $save ]] || { printf '%s\n' "$file" > "$save"; printf '%s\n' "${current:-$DEVNO rbps=max wbps=max riops=max wiops=max}" > "$save.values"; }
        rbps=8000000; wbps=4000000
        # min(existing, incident cap): never increase another operator's limit.
        for field in $current; do
            case "$field" in
                rbps=*) value=${field#*=}; [[ $value == max ]] || { (( value >= rbps )) || rbps=$value; } ;;
                wbps=*) value=${field#*=}; [[ $value == max ]] || { (( value >= wbps )) || wbps=$value; } ;;
            esac
        done
        printf '%s rbps=%s wbps=%s\n' "$DEVNO" "$rbps" "$wbps" > "$file"
        printf 'Runtime SATA cap %s: read=%s B/s write=%s B/s (no restart).\n' "$unit" "$rbps" "$wbps"
    done
    printf 'Runtime limits expire with the cgroups/reboot; rollback: --restore-background. No persistent policy changed.\n'
    exit 0
fi
$QUIESCED || { printf 'Cache writers must be closed first; pass --writers-quiesced only after doing so.\n' >&2; exit 1; }
[[ $(findmnt -n -o FSTYPE -T /workspace) == xfs ]] || { printf 'Expected NVMe XFS workspace.\n' >&2; exit 1; }
[[ $(findmnt -n -o SOURCE -T /workspace) == /dev/nvme0n1p3 ]] || { printf 'Workspace device changed.\n' >&2; exit 1; }
[[ -L $HOME_DIR/.cache ]] || { printf '~/.cache is no longer the diagnosed symlink; refusing.\n' >&2; exit 1; }
SOURCE=$(readlink -f "$HOME_DIR/.cache")
if [[ $SOURCE == "$NEW_CACHE" ]]; then
    printf 'Cache already on NVMe; no change.\n'
    exit 0
fi
[[ $SOURCE == "$OLD_CACHE" ]] || { printf 'Cache source changed; refusing.\n' >&2; exit 1; }
# Leave 16 GiB for swap and normal workspace growth. Source remains intact.
NEEDED=$(ionice -c3 du -sxB1 "$SOURCE" | cut -f1)
AVAILABLE=$(df -B1 --output=avail /workspace | tr -d '[:alpha:][:space:]')
(( AVAILABLE >= NEEDED + 17179869184 )) || { printf 'Insufficient workspace headroom (need copy + 16 GiB).\n' >&2; exit 1; }
as_user mkdir -p -- "$NEW_CACHE"
# Both copying and home-link replacement run unprivileged, not root through user paths.
as_user ionice -c3 nice -n 19 rsync -aHAXS --numeric-ids --one-file-system -- "$SOURCE/" "$NEW_CACHE/"
COMPARE=$(as_user ionice -c3 nice -n 19 rsync -aHAXSnci --delete --numeric-ids --one-file-system -- "$SOURCE/" "$NEW_CACHE/")
[[ -z $COMPARE ]] || { printf 'Checksum/metadata comparison differs; cache link NOT changed:\n%s\n' "$COMPARE" >&2; exit 1; }
# mktemp reserves an unpredictable directory so another process cannot pre-create the link.
TMP=$(as_user mktemp -d "$HOME_DIR/.cache-cutover.XXXXXXXX")
trap '[[ -z ${TMP:-} ]] || { rm -f -- "$TMP/link"; rmdir -- "$TMP"; }' EXIT
as_user ln -s -- "$NEW_CACHE" "$TMP/link"
as_user mv -T -- "$TMP/link" "$HOME_DIR/.cache"
as_user rmdir -- "$TMP"
TMP=""
printf 'Cache now points to %s; original retained at %s. No services restarted.\n' "$NEW_CACHE" "$OLD_CACHE"
printf 'Reopen apps now. Rollback requires quiescing writers and reconciling any new cache entries before repointing.\n'
