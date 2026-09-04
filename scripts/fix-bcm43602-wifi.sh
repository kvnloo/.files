#!/usr/bin/env bash
# Persist the ArchWiki/CachyOS fix for Apple/Dell BCM43602 (14e4:43ba):
# disable firmware 4-way offload so wpa_supplicant 2.11 can finish the handshake.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

conf=/etc/modprobe.d/brcmfmac-bcm43602.conf
grub=/etc/default/grub
param='brcmfmac.feature_disable=0x82000'

printf 'options brcmfmac feature_disable=0x82000\n' >"$conf"
echo "Wrote $conf"

if [[ -f $grub ]]; then
  if grep -q 'brcmfmac.feature_disable=' "$grub"; then
    echo "GRUB already has a brcmfmac.feature_disable setting"
  else
    sed -i.bak-bcm43602 \
      "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"\\(.*\\)\"/GRUB_CMDLINE_LINUX_DEFAULT=\"\\1 ${param}\"/" \
      "$grub"
    if command -v grub-mkconfig >/dev/null; then
      grub-mkconfig -o /boot/grub/grub.cfg
    fi
    echo "Added $param to GRUB_CMDLINE_LINUX_DEFAULT"
  fi
fi

if lsmod | grep -q '^brcmfmac'; then
  echo "Reloading brcmfmac (wlan0 will drop briefly)..."
  modprobe -r brcmfmac_wcc brcmfmac 2>/dev/null || modprobe -r brcmfmac || true
  modprobe brcmfmac feature_disable=0x82000
fi

echo
echo "Check: cat /sys/module/brcmfmac/parameters/feature_disable"
echo "Then:  nmcli device set wlan0 autoconnect yes"
echo "        nmcli device wifi connect Mxin ifname wlan0"
echo "Reboot if the module would not unload (brcmfmac in use)."
