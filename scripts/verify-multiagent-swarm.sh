#!/usr/bin/env bash
#
# Verify the state of multi-agent swarm optimizations.
# Does not need root (some commands may show permission errors for root-only paths).
#
set -euo pipefail

echo "=== CPU Governor ==="
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort | uniq -c

echo
echo "=== CPU Frequency (avg) ==="
awk '/^cpu MHz/{sum+=$4; n++} END {printf "%.0f MHz across %d cores\n", sum/n, n}' /proc/cpuinfo

echo
echo "=== sched-ext / scx_loader ==="
systemctl is-active scx_loader.service 2>/dev/null && echo "scx_loader: active" || echo "scx_loader: inactive"
scxctl status 2>/dev/null || true

echo
echo "=== ananicy-cpp ==="
systemctl is-active ananicy-cpp.service 2>/dev/null && echo "ananicy-cpp: active" || echo "ananicy-cpp: inactive"

echo
echo "=== irqbalance ==="
systemctl is-active irqbalance.service 2>/dev/null && echo "irqbalance: active" || echo "irqbalance: inactive"

echo
echo "=== VM Tunables ==="
sysctl vm.swappiness vm.watermark_scale_factor vm.dirty_ratio vm.dirty_background_ratio vm.vfs_cache_pressure vm.page-cluster 2>/dev/null || true

echo
echo "=== Memory / Swap ==="
free -h

echo
echo "=== zram ==="
zramctl 2>/dev/null || true

echo
echo "=== Top 10 CPU consumers ==="
ps aux --sort=-%cpu | head -11

echo
echo "=== Top 10 RAM consumers ==="
ps aux --sort=-%mem | head -11

echo
echo "=== Load / Uptime ==="
uptime
