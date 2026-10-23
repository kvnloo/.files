#!/usr/bin/env bash
# Explicit Arch deployment; package installation belongs to the root batch.
# No service is started by install. apply is the deliberately activating action.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir="$root/config/netdata"
action=${1:---help}
profile=${2:-}
desktop_user=${3:-${SUDO_USER:-kvn}}
case "$action" in
  --help|-h)
    printf '%s\n' \
      'Usage: setup-netdata.sh install|activate|apply desktop|mbp [desktop-user]' \
      'Requires installed packages: netdata smartmontools python libnotify.' \
      'install: install root-owned files; do not start/restart services.' \
      'activate: require matching installed files, enable socket and restart Netdata.' \
      'apply: install then activate (interactive sudo required when not root).' \
      'desktop requires NVMe backing /var/cache; mbp requires local nonrotational SSD.' \
      'Dashboard: http://127.0.0.1:19999; remote access uses SSH forwarding only.'
    exit 0 ;;
  install|activate|apply) ;;
  *) printf 'Unknown action: %s\n' "$action" >&2; exit 2 ;;
esac
case "$profile" in desktop|mbp) ;; *) printf 'Select desktop or mbp.\n' >&2; exit 2 ;; esac
if (( EUID != 0 )); then
  exec sudo /usr/bin/bash "$root/scripts/setup-netdata.sh" "$action" "$profile" "$desktop_user"
fi
export PATH=/usr/bin:/usr/sbin
export LC_ALL=C
fail() { printf 'setup-netdata: %s\n' "$*" >&2; exit 1; }
[[ "$desktop_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || fail 'Invalid desktop user.'
uid=$(id -u "$desktop_user")
(( uid >= 1000 && uid != 65534 )) || fail 'Choose a real, unprivileged desktop user.'
for package in netdata smartmontools python libnotify; do
  pacman -Q "$package" >/dev/null || fail "Install $package through the coordinated root batch first."
done
# Do not silently migrate credentials or an existing Cloud deployment.
for claim in /etc/netdata/claim.conf /var/lib/netdata/cloud.d/claimed_id /var/lib/netdata/cloud.d/token; do
  [[ ! -s "$claim" ]] || fail "Existing Cloud claim input: $claim (resolve explicitly before deployment)."
done
if [[ -f /var/lib/netdata/cloud.d/cloud.conf ]] &&
   grep -Eq '^[[:space:]]*(token|claimed_id)[[:space:]]*=[[:space:]]*[^[:space:]]' /var/lib/netdata/cloud.d/cloud.conf; then
  fail 'Existing Cloud credentials in cloud.conf; no credentials were changed.'
fi
# Fail closed rather than quietly placing dbengine on an HDD, USB disk or tmpfs.
backing=$(findmnt -n -T /var/cache -o SOURCE)
backing=${backing%%\[*}
[[ "$backing" == /dev/* ]] || fail '/var/cache must be backed by a local block device.'
transports=$(lsblk -s -r -n -o TRAN "$backing")
if [[ "$profile" == desktop ]]; then
  [[ $'\n'"$transports"$'\n' == *$'\nnvme\n'* ]] || fail '/var/cache is not NVMe-backed on desktop.'
else
  [[ "$transports" != *usb* ]] || fail 'MBP cache must not be on the external USB disk.'
  while read -r type rotational; do
    [[ "$type" != disk || "$rotational" == 0 ]] || fail 'MBP cache must be on nonrotational storage.'
  done < <(lsblk -s -r -n -o TYPE,ROTA "$backing")
fi
# Ensure the packaged privilege helper is not writable by the daemon/user.
helper=/usr/lib/netdata/plugins.d/ndsudo
[[ -f "$helper" && ! -L "$helper" ]] || fail 'Missing Arch package ndsudo helper.'
[[ $(stat -c '%U:%G' "$helper") == root:netdata ]] || fail 'ndsudo must be package-owned root:netdata.'
[[ -u "$helper" ]] || fail 'Packaged ndsudo lacks setuid; SMART queries would not work.'
(( (8#$(stat -c '%a' "$helper") & 8#022) == 0 )) || fail 'ndsudo must not be group/world writable.'

stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
cat "$source_dir/netdata.conf" "$source_dir/profiles/$profile.conf" > "$stage/netdata.conf"
printf '[Service]\nUser=%s\nEnvironment=HOME=/nonexistent XDG_RUNTIME_DIR=/run/user/%s DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%s/bus\n' \
  "$desktop_user" "$uid" "$uid" > "$stage/desktop-user.conf"
printf '%s\n' "$profile" > "$stage/monitoring-profile"
# The environment file is not sourced, and the service never executes home/repo code.
files=(
  "$stage/netdata.conf|/etc/netdata/netdata.conf|644"
  "$stage/monitoring-profile|/etc/netdata/monitoring-profile|644"
  "$source_dir/go.d.conf|/etc/netdata/go.d.conf|644"
  "$source_dir/go.d/smartctl.conf|/etc/netdata/go.d/smartctl.conf|644"
  "$source_dir/netdata-desktop-notify|/usr/local/libexec/netdata-desktop-notify|755"
  "$source_dir/systemd/netdata.service.d/monitoring.conf|/etc/systemd/system/netdata.service.d/monitoring.conf|644"
  "$source_dir/systemd/netdata-desktop-notify.socket|/etc/systemd/system/netdata-desktop-notify.socket|644"
  "$source_dir/systemd/netdata-desktop-notify.service|/etc/systemd/system/netdata-desktop-notify.service|644"
  "$stage/desktop-user.conf|/etc/systemd/system/netdata-desktop-notify.service.d/desktop-user.conf|644"
)
for alert in disks swap infrastructure; do
  files+=("$source_dir/health.d/$alert.conf|/etc/netdata/health.d/$alert.conf|644")
done
if [[ "$profile" == mbp ]]; then
  files+=("$source_dir/systemd/mbp.conf|/etc/systemd/system/netdata.service.d/mbp.conf|644")
elif [[ -e /etc/systemd/system/netdata.service.d/mbp.conf ]]; then
  fail 'MBP resource override exists on desktop; remove it explicitly before switching host profiles.'
fi
if [[ "$action" == install || "$action" == apply ]]; then
  # Root ownership and real directories are part of the privilege boundary.
  for directory in /etc/netdata /etc/netdata/health.d /etc/netdata/go.d \
      /usr/local/libexec /var/backups /etc/systemd/system/netdata.service.d \
      /etc/systemd/system/netdata-desktop-notify.service.d; do
    [[ ! -L "$directory" ]] || fail "Refusing symlinked managed directory: $directory"
    install -d -o root -g root -m755 "$directory"
  done
  backup_dir=""
  for entry in "${files[@]}"; do
    IFS='|' read -r src dest mode <<< "$entry"
    [[ ! -L "$dest" ]] || fail "Refusing symlinked managed file: $dest"
    if [[ -e "$dest" ]] && ! cmp -s -- "$src" "$dest"; then
      if [[ -z "$backup_dir" ]]; then
        backup_dir=$(mktemp -d /var/backups/netdata-monitoring.XXXXXXXX)
      fi
      install -D -o root -g root -m600 "$dest" "$backup_dir$dest"
    fi
    install -D -o root -g root -m"$mode" "$src" "$dest"
  done
  [[ ! -L /etc/netdata/.opt-out-from-anonymous-statistics ]] || fail 'Opt-out marker is a symlink.'
  install -o root -g root -m644 /dev/null /etc/netdata/.opt-out-from-anonymous-statistics
  [[ ! -L /var/cache/netdata ]] || fail 'Cache directory must not be a symlink.'
  install -d -o netdata -g netdata -m750 /var/cache/netdata
  systemctl daemon-reload
  [[ -z "$backup_dir" ]] || printf 'Previous managed files saved to %s\n' "$backup_dir"
  printf 'Netdata %s files installed; storage limits are soft quotas.\n' "$profile"
fi
if [[ "$action" == activate || "$action" == apply ]]; then
  for entry in "${files[@]}"; do
    IFS='|' read -r src dest mode <<< "$entry"
    [[ ! -L "$dest" ]] && cmp -s -- "$src" "$dest" || fail "Installed file differs: $dest; run install first."
    [[ $(stat -c '%U:%G:%a' "$dest") == "root:root:$mode" ]] || fail "Unsafe ownership/mode: $dest"
  done
  [[ -f /etc/netdata/.opt-out-from-anonymous-statistics && ! -L /etc/netdata/.opt-out-from-anonymous-statistics ]] || fail 'Missing/unsafe telemetry opt-out marker.'
  # No root notification handler and no direct key/socket privileges for users.
  systemctl enable netdata.service netdata-desktop-notify.socket
  systemctl stop netdata-desktop-notify.service netdata-desktop-notify.socket
  systemctl start netdata-desktop-notify.socket
  systemctl restart netdata.service
  printf 'Activated Netdata on loopback; notifications target %s UID %s.\n' "$desktop_user" "$uid"
  printf 'Notification check: sudo -u netdata /usr/local/libexec/netdata-desktop-notify --test WARNING\n'
fi
