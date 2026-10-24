#!/usr/bin/env bash
# Explicit setup only: never activate keyboard interception during installation.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
action=${1:---help}
case "$action" in
  install|activate|disable) ;;
  --help|-h)
    printf '%s\n' \
      'Usage: setup-desktop-modal.sh install|activate|disable' \
      'install: install keyd, the Wooting-only config and the layer relay; activate nothing.' \
      'activate: enable/restart keyd and the relay; revoke direct keyd socket access.' \
      'disable: stop/disable keyd and the relay; leave the config available for inspection.'
    exit 0 ;;
  *) printf 'Unknown action: %s\n' "$action" >&2; exit 2 ;;
esac
if (( EUID != 0 )); then
  exec sudo /usr/bin/bash "$root/scripts/setup-desktop-modal.sh" "$action"
fi

relay_units=(keyd-layers.socket keyd-layers.service)

if [[ "$action" == disable ]]; then
  systemctl disable --now keyd-layers.socket keyd-layers.service
  systemctl disable --now keyd.service
  exit 0
fi

# Another config could match additional keyboards or mice. Never widen scope.
for config in /etc/keyd/*.conf; do
  [[ -e "$config" ]] || continue
  if [[ "$config" != /etc/keyd/default.conf ]]; then
    printf 'Refusing activation alongside another keyd config: %s\n' "$config" >&2
    exit 1
  fi
done

source_config="$root/config/keyd/default.conf"
if [[ "$action" == install ]]; then
  pacman -S --needed keyd
  keyd check "$source_config"
  if ! cmp -s -- "$source_config" /etc/keyd/default.conf; then
    if systemctl is-active --quiet keyd.service; then
      printf 'Stop keyd explicitly before replacing its configuration.\n' >&2
      exit 1
    fi
    if [[ -e /etc/keyd/default.conf ]]; then
      backup=$(mktemp /etc/keyd/default.conf.backup.XXXXXXXX)
      cp -a -- /etc/keyd/default.conf "$backup"
      printf 'Previous configuration saved to %s\n' "$backup"
    fi
    install -Dm644 "$source_config" /etc/keyd/default.conf
    keyd check /etc/keyd/default.conf
  fi
  # The relay runs with the keyd group, so it must be a root-owned copy.
  install -Dm755 -o root -g root "$root/scripts/keyd-layers" /usr/local/bin/keyd-layers
  for unit in "${relay_units[@]}"; do
    install -Dm644 -o root -g root "$root/config/systemd/system/$unit" "/etc/systemd/system/$unit"
  done
  systemctl daemon-reload
  printf 'Installed. Nothing was activated or restarted; activate separately.\n'
else
  if ! cmp -s -- "$source_config" /etc/keyd/default.conf ||
     ! cmp -s -- "$root/scripts/keyd-layers" /usr/local/bin/keyd-layers; then
    printf 'Installed configuration differs. Run the install action first.\n' >&2
    exit 1
  fi
  for unit in "${relay_units[@]}"; do
    if ! cmp -s -- "$root/config/systemd/system/$unit" "/etc/systemd/system/$unit"; then
      printf 'Installed %s differs. Run the install action first.\n' "$unit" >&2
      exit 1
    fi
  done
  keyd check /etc/keyd/default.conf
  # /run/keyd.socket accepts bindings, input and root command() actions.
  # Users read layer state through keyd-layers; nobody joins the keyd group.
  members=$(getent group keyd | cut -d: -f4)
  if [[ -n "$members" ]]; then
    printf 'Removing keyd group members: %s\n' "$members"
    gpasswd -M '' keyd
  fi
  systemctl enable keyd.service keyd-layers.socket
  systemctl restart keyd.service
  # Restart recreated the socket; drop any ad-hoc ACL that was added afterwards.
  setfacl -b /run/keyd.socket
  systemctl stop keyd-layers.service keyd-layers.socket
  systemctl start keyd-layers.socket
  systemctl status keyd.service keyd-layers.socket --no-pager
fi
