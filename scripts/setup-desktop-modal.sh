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
      'install: install keyd and the Wooting-only config; leave service stopped.' \
      'activate: explicitly enable/restart keyd with the reviewed config.' \
      'disable: stop/disable keyd; leave the config available for inspection.'
    exit 0 ;;
  *) printf 'Unknown action: %s\n' "$action" >&2; exit 2 ;;
esac
if (( EUID != 0 )); then
  exec sudo /usr/bin/bash "$root/scripts/setup-desktop-modal.sh" "$action"
fi

if [[ "$action" == disable ]]; then
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
  if systemctl is-active --quiet keyd.service; then
    printf 'Stop keyd explicitly before replacing its configuration.\n' >&2
    exit 1
  fi
  pacman -S --needed keyd
  keyd check "$source_config"
  if [[ -e /etc/keyd/default.conf ]]; then
    backup=$(mktemp /etc/keyd/default.conf.backup.XXXXXXXX)
    cp -a -- /etc/keyd/default.conf "$backup"
    printf 'Previous configuration saved to %s\n' "$backup"
  fi
  install -Dm644 "$source_config" /etc/keyd/default.conf
  keyd check /etc/keyd/default.conf
  printf 'Installed. Keyboard interception is not active; activate separately.\n'
else
  if ! cmp -s -- "$source_config" /etc/keyd/default.conf; then
    printf 'Installed configuration differs. Run the install action first.\n' >&2
    exit 1
  fi
  keyd check /etc/keyd/default.conf
  systemctl enable keyd.service
  systemctl restart keyd.service
  systemctl status keyd.service --no-pager
fi
