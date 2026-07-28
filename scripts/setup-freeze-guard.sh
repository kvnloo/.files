#!/usr/bin/env bash
# setup-freeze-guard.sh — prevent memory-thrash freezes (run with sudo)
#
# Installs two layers of protection:
#  1. earlyoom  — kills the biggest memory hog BEFORE the system starts
#     thrashing (MemAvailable < 5% AND swap free < 65%, i.e. zram full).
#     Never touches the compositor/terminals/audio; prefers browsers,
#     electron and runaway interpreters. Sends a dunst notification on kill.
#  2. MGLRU min_ttl_ms=1000 — kernel-level backstop: protect the last
#     second of working set and OOM-kill instead of thrashing.
#
# Thresholds are tuned for: 15.5GiB RAM, 15.5GiB zram (prio 100) +
# 32GiB disk swap (prio -1). "Swap free < 65%" ≈ zram is full and the
# system is about to spill onto slow disk swap — the freeze point.

set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

echo "==> Installing earlyoom"
pacman -S --needed --noconfirm earlyoom

echo "==> Configuring earlyoom thresholds"
cat > /etc/default/earlyoom << 'EOF'
EARLYOOM_ARGS="-r 0 -m 5 -s 65 -n \
 --avoid '^(systemd|systemd-.*|Hyprland|Xwayland|Xorg|sddm|kitty|alacritty|tmux|waybar|dunst|pipewire|wireplumber|dbus.*|NetworkManager|sshd)$' \
 --prefer '^(chromium|chrome|electron|zen-bin|Isolated Web Co|Web Content|node|python.*)$'"
EOF

echo "==> Enabling earlyoom (disabling systemd-oomd to avoid double-killers)"
systemctl disable --now systemd-oomd 2>/dev/null || true
systemctl enable --now earlyoom

echo "==> MGLRU anti-thrash (min_ttl_ms=1000, persisted via tmpfiles.d)"
echo 1000 > /sys/kernel/mm/lru_gen/min_ttl_ms
cat > /etc/tmpfiles.d/mglru-min-ttl.conf << 'EOF'
w- /sys/kernel/mm/lru_gen/min_ttl_ms - - - - 1000
EOF

echo
echo "==> Verification"
systemctl is-active earlyoom
grep -o '\-m 5 -s 65' /etc/default/earlyoom
echo "min_ttl_ms: $(cat /sys/kernel/mm/lru_gen/min_ttl_ms)"
echo
echo "Done. Test anytime with: systemctl status earlyoom"
echo "Kills are logged to the journal: journalctl -u earlyoom -f"
