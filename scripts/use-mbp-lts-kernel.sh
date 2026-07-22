#!/usr/bin/env bash

set -euo pipefail

grub_defaults=/etc/default/grub
backup=/etc/default/grub.pre-mbp-suspend-fix
lts_kernel=/boot/vmlinuz-linux-cachyos-lts

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

if [[ ! -f "$lts_kernel" ]]; then
  echo "The CachyOS LTS kernel is not installed: $lts_kernel" >&2
  exit 1
fi

if [[ ! -e "$backup" ]]; then
  cp -a "$grub_defaults" "$backup"
fi

sed -i "s|^GRUB_TOP_LEVEL=.*|GRUB_TOP_LEVEL='$lts_kernel'|" "$grub_defaults"
grub-mkconfig -o /boot/grub/grub.cfg

echo
echo "Configured $lts_kernel as the default kernel."
echo "Reboot, then verify with: uname -r"
