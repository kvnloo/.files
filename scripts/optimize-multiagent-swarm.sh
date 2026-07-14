#!/usr/bin/env bash
#
# Apply (or revert) in-flight system optimizations for multi-agent swarm development on CachyOS.
#
# Usage:
#   sudo ./scripts/optimize-multiagent-swarm.sh        # apply optimizations
#   sudo ./scripts/optimize-multiagent-swarm.sh --revert
#
# Hardware: Intel i9-10900KF (10C/10T with SMT disabled), 16 GB RAM, RTX 3080 Ti
# Workload: 30+ AI agent harnesses (Codex, Claude Code, Kimi) + browsers + dev servers
#
# All changes are reversible without a reboot:
#   - sysctl values can be removed and `sysctl --system` re-run
#   - scx_loader can be stopped/disabled; kernel falls back to default EEVDF/BORE
#   - governor can be switched back to schedutil
#   - ananicy-cpp can be re-enabled if desired
#
set -euo pipefail

REVERT=false
if [[ ${1:-} == "--revert" ]]; then
    REVERT=true
fi

log() { echo "[optimize] $*"; }
warn() { echo "[optimize] WARNING: $*" >&2; }

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (e.g., sudo $0)" >&2
    exit 1
fi

apply() {
    BACKUP_DIR="/root/system-optimize-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    log "Backing up existing configs to $BACKUP_DIR"
    cp -a /etc/sysctl.d/99-multiagent-swarm.conf "$BACKUP_DIR/" 2>/dev/null || true
    cp -a /etc/ananicy.d/99-multiagent-swarm.rules "$BACKUP_DIR/" 2>/dev/null || true
    cp -a /etc/scx_loader/config.toml "$BACKUP_DIR/" 2>/dev/null || true

    # -------------------------------------------------------------------------
    # 1. VM / memory tuning
    # -------------------------------------------------------------------------
    log "Writing /etc/sysctl.d/99-multiagent-swarm.conf"
    cat > /etc/sysctl.d/99-multiagent-swarm.conf <<'EOF'
# Multi-agent swarm development tuning
# CachyOS already sets several good defaults; this file fills the gaps.

# Keep VFS cache pressure at the CachyOS default (50) instead of the upstream 100.
vm.vfs_cache_pressure = 50

# Swappiness: CachyOS default is 150 which is tuned for zram-only swap.
# Because this box also has 32 GB of disk swap and is already spilling to it,
# lower to 100 to reduce premature eviction from RAM while still using zram.
vm.swappiness = 100

# Make kswapd more proactive to reduce sudden allocation stalls when agents spawn.
vm.watermark_scale_factor = 125

# Already set by CachyOS; keep it pinned here.
vm.page-cluster = 0

# Raise dirty thresholds to reduce writeback stalls during heavy I/O.
vm.dirty_ratio = 20
vm.dirty_background_ratio = 10
EOF

    log "Applying sysctl settings"
    sysctl --system

    # -------------------------------------------------------------------------
    # 2. CPU governor -> performance
    # -------------------------------------------------------------------------
    log "Switching CPU governor to performance"
    if command -v cpupower >/dev/null 2>&1; then
        cpupower frequency-set -g performance
    else
        for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
            echo performance > "$gov"
        done
    fi

    # -------------------------------------------------------------------------
    # 3. Ananicy-cpp rules for agent harnesses (kept on disk for fallback use)
    # -------------------------------------------------------------------------
    log "Writing /etc/ananicy.d/99-multiagent-swarm.rules"
    cat > /etc/ananicy.d/99-multiagent-swarm.rules <<'EOF'
# Priority boost for agent orchestrators (active only when ananicy-cpp is running)
{ "name": "kimi", "nice": -1, "ioclass": "best-effort", "ionice": 2 }
{ "name": "kimi-code", "nice": -1, "ioclass": "best-effort", "ionice": 2 }
{ "name": "codex", "nice": -1, "ioclass": "best-effort", "ionice": 2 }
{ "name": "claude", "nice": -1, "ioclass": "best-effort", "ionice": 2 }

# Deprioritize heavy but non-interactive background consumers
{ "name": "linux-wallpaperengine", "nice": 5, "ioclass": "idle", "ionice": 7 }
{ "name": "pytest", "nice": 2, "ioclass": "best-effort", "ionice": 4 }
EOF

    # -------------------------------------------------------------------------
    # 4. sched-ext: activate scx_flow via scx_loader
    #     CachyOS recommends stopping ananicy-cpp while a sched-ext scheduler is active
    #     because both manipulate process priorities and can conflict.
    # -------------------------------------------------------------------------
    log "Configuring scx_loader to use scx_flow"
    mkdir -p /etc/scx_loader
    cat > /etc/scx_loader/config.toml <<'EOF'
default_sched = "scx_flow"
default_mode = "Auto"
EOF

    log "Stopping ananicy-cpp (sched-ext conflicts with auto-nice daemons)"
    systemctl disable --now ananicy-cpp.service || true

    log "Enabling and starting scx_loader"
    systemctl enable --now scx_loader.service

    # -------------------------------------------------------------------------
    # 5. irqbalance for better interrupt distribution
    # -------------------------------------------------------------------------
    if ! command -v irqbalance >/dev/null 2>&1; then
        log "Installing irqbalance"
        pacman -S --noconfirm --needed irqbalance
    fi
    log "Enabling irqbalance"
    systemctl enable --now irqbalance.service

    # -------------------------------------------------------------------------
    # 6. Verification
    # -------------------------------------------------------------------------
    echo
    echo "=== VERIFICATION ==="
    echo "Active scheduler:"
    scxctl status 2>/dev/null || systemctl status scx_loader.service --no-pager | head -5

    echo
    echo "CPU governors:"
    cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort | uniq -c

    echo
    echo "VM tunables:"
    sysctl vm.swappiness vm.watermark_scale_factor vm.dirty_ratio vm.dirty_background_ratio vm.vfs_cache_pressure vm.page-cluster

    echo
    echo "Services:"
    systemctl is-active scx_loader.service irqbalance.service || true

    echo
    echo "Done. No reboot required."
    echo "If scx_flow causes instability, run:  sudo $0 --revert"
}

revert() {
    log "Reverting optimizations"

    log "Stopping scx_loader and restoring default kernel scheduler"
    systemctl stop scx_loader.service || true
    systemctl disable scx_loader.service || true

    log "Re-enabling ananicy-cpp"
    systemctl enable --now ananicy-cpp.service || true

    log "Restoring CPU governor to schedutil"
    if command -v cpupower >/dev/null 2>&1; then
        cpupower frequency-set -g schedutil
    else
        for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
            echo schedutil > "$gov"
        done
    fi

    log "Removing custom sysctl config"
    rm -f /etc/sysctl.d/99-multiagent-swarm.conf
    sysctl --system

    log "Stopping irqbalance (optional; harmless to leave enabled)"
    systemctl stop irqbalance.service || true
    systemctl disable irqbalance.service || true

    echo
    echo "Reverted. Kernel scheduler has fallen back to default EEVDF/BORE."
}

if $REVERT; then
    revert
else
    apply
fi
