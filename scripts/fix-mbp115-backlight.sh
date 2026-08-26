#!/usr/bin/env bash
# Fix dead screen-backlight control on the 2015 15" Retina MacBook Pro
# (MacBookPro11,4 / MacBookPro11,5, dual GPU behind apple_gmux).
#
# Symptom: brightness keys + OSD work, gmux_backlight/brightness moves, but the
# panel never dims and /sys/class/backlight/*/actual_brightness is pinned at
# 16777215 (0xFFFFFF) instead of tracking the requested value. The backlight is
# owned by the Intel GPU PWM, but the gmux default leaves the mux on the
# discrete AMD GPU, so the gmux_backlight interface is inert.
#
# Fix: register the real ACPI/Intel backlight interface via the
# acpi_backlight=video kernel parameter so F1/F2 actually drive the panel.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

grub=/etc/default/grub
param='acpi_backlight=video'

echo "=== current backlight state (pre-fix) ==="
ls -1 /sys/class/backlight/ 2>/dev/null || echo "(no backlight devices)"
for d in /sys/class/backlight/*; do
  echo "$d: brightness=$(cat "$d/brightness" 2>/dev/null) actual=$(cat "$d/actual_brightness" 2>/dev/null) max=$(cat "$d/max_brightness" 2>/dev/null)"
done

if [[ -f $grub ]]; then
  if grep -q 'acpi_backlight=' "$grub"; then
    echo "GRUB already has an acpi_backlight setting; leaving CMDLINE untouched:"
    grep 'acpi_backlight=' "$grub"
  else
    # Quote-agnostic: match either ' or " around the value.
    sed -i.bak-mbp115 -E \
      "s/^(GRUB_CMDLINE_LINUX_DEFAULT=)['\"]([^'\"]*)['\"]/\1'\2 ${param}'/" \
      "$grub"
    echo "Added $param to GRUB_CMDLINE_LINUX_DEFAULT:"
    grep '^GRUB_CMDLINE_LINUX_DEFAULT' "$grub"
  fi
  if command -v grub-mkconfig >/dev/null; then
    grub-mkconfig -o /boot/grub/grub.cfg
    echo "Regenerated /boot/grub/grub.cfg"
  fi
  # Verify the param made it into the boot config (catches silent sed no-ops).
  if grep -q "acpi_backlight=video" /boot/grub/grub.cfg 2>/dev/null; then
    echo "VERIFIED: acpi_backlight=video is present in /boot/grub/grub.cfg"
  else
    echo "WARNING: acpi_backlight=video NOT found in /boot/grub/grub.cfg -- edit may have failed" >&2
  fi
else
  echo "No $grub found; skipped GRUB edit. If you use systemd-boot, add"
  echo "  $param"
  echo "to the options line of your loader entry under /boot/loader/entries/ instead."
fi

echo
echo "=== NEXT STEPS ==="
echo "1. Reboot: sudo reboot"
echo "2. After reboot, verify the panel actually dims with F1/F2 and run:"
echo "     ls /sys/class/backlight/        # expect acpi_video0 / intel_backlight now present"
echo "     cat /sys/class/backlight/*/actual_brightness   # should TRACK the value, not 16777215"
echo
echo "If actual_brightness is STILL pinned at 16777215 after reboot, the fallback"
echo "is to swap the param for acpi_backlight=vendor (re-run this script after"
echo "editing GRUB_CMDLINE_LINUX_DEFAULT). Note: =vendor can make the interface"
echo "disappear on some models -- removing the param reverts to the current state."
