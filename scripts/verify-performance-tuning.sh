#!/usr/bin/env bash
# verify-performance-tuning.sh
# Verify the performance tuning applied by apply-performance-tuning.sh.

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

ERRORS=0

check_cmd() {
    local name="$1"
    local expected="$2"
    local actual
    actual=$(eval "$name" 2>/dev/null) || actual=""
    if [ "$actual" = "$expected" ]; then
        pass "$name => $actual"
    else
        fail "$name => $actual (expected $expected)"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "=== CPU Governor ==="
GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "unknown")
if [ "$GOV" = "performance" ]; then
    pass "CPU governor is performance"
else
    fail "CPU governor is $GOV"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== sched-ext Scheduler ==="
if systemctl is-active --quiet scx_loader; then
    pass "scx_loader is active"
    if [ -r /etc/scx_loader/config.toml ]; then
        DEFAULT=$(grep -E '^default_sched' /etc/scx_loader/config.toml | cut -d= -f2 | tr -d ' "')
        pass "Default scheduler: $DEFAULT"
    fi
else
    fail "scx_loader is not active"
    ERRORS=$((ERRORS + 1))
fi

if systemctl is-active --quiet ananicy-cpp; then
    warn "ananicy-cpp is still active (may conflict with sched-ext)"
else
    pass "ananicy-cpp is stopped"
fi

echo ""
echo "=== irqbalance ==="
if systemctl is-active --quiet irqbalance; then
    pass "irqbalance is active"
else
    warn "irqbalance is not active"
fi

echo ""
echo "=== Kernel Command Line ==="
cmdline=$(cat /proc/cmdline)
for param in intel_pstate=passive threadirqs processor.max_cstate intel_idle.max_cstate rcupdate.rcu_normal_after_boot rcutree.enable_rcu_lazy; do
    if echo "$cmdline" | grep -q "$param"; then
        pass "Kernel cmdline contains $param"
    else
        warn "Kernel cmdline missing $param"
    fi
done

echo ""
echo "=== Sysctl Checks ==="
check_cmd "sysctl -n vm.swappiness" "150"
check_cmd "sysctl -n vm.vfs_cache_pressure" "50"
check_cmd "sysctl -n vm.page-cluster" "0"
check_cmd "sysctl -n kernel.sched_autogroup_enabled" "0"
check_cmd "sysctl -n net.core.somaxconn" "65535"

CC=$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || echo "unknown")
if [ "$CC" = "bbr" ]; then
    pass "TCP congestion control is bbr"
else
    warn "TCP congestion control is $CC (bbr recommended)"
fi

echo ""
echo "=== I/O Scheduler ==="
SCHED_RAW=$(cat /sys/block/nvme0n1/queue/scheduler 2>/dev/null || echo "unknown")
SCHED_ACTIVE=$(echo "$SCHED_RAW" | awk '{print $1}')
if [ "$SCHED_ACTIVE" = "none" ]; then
    pass "NVMe scheduler is none"
else
    fail "NVMe scheduler is not none: $SCHED_RAW"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== Transparent Huge Pages ==="
if [ -r /sys/kernel/mm/transparent_hugepage/enabled ]; then
    if grep -q '\[always\]' /sys/kernel/mm/transparent_hugepage/enabled; then
        pass "THP enabled"
    else
        warn "THP not always enabled: $(cat /sys/kernel/mm/transparent_hugepage/enabled)"
    fi
fi

echo ""
echo "=== GPU ==="
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,persistence_mode,power.draw,clocks.gr,clocks.mem --format=csv,noheader || true
else
    warn "nvidia-smi not found"
fi

echo ""
echo "=== Memory / Swap ==="
free -h
swapon --show
zramctl || true

echo ""
echo "=== UEFI Hidden Settings Diff ==="
if [ -x ./scripts/uefi-hidden-settings-inspector.py ]; then
    python3 ./scripts/uefi-hidden-settings-inspector.py diff >/dev/null 2>&1 || true
    if [ -f logs/uefi-hidden-settings-diff.md ]; then
        pass "logs/uefi-hidden-settings-diff.md exists"
    else
        warn "logs/uefi-hidden-settings-diff.md not generated"
    fi
else
    warn "uefi-hidden-settings-inspector.py not found"
fi

echo ""
if [ "$ERRORS" -eq 0 ]; then
    pass "All critical checks passed."
else
    fail "$ERRORS critical check(s) failed. Review output above."
fi
exit "$ERRORS"
