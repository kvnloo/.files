#!/usr/bin/env bash
# apply-performance-tuning.sh
# Apply safe, reversible performance tuning for CachyOS / i9-10900KF / RTX 3080 Ti.
# Run with: sudo ./scripts/apply-performance-tuning.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err() { echo -e "${RED}[-]${NC} $*" >&2; }

if [ "$EUID" -ne 0 ]; then
    err "This script must be run as root (use sudo)."
    exit 1
fi

BACKUP_DIR="/var/tmp/perf-tuning-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
log "Backing up current state to $BACKUP_DIR"

cp /etc/sysctl.d/*.conf "$BACKUP_DIR/" 2>/dev/null || true
cp /etc/scx_loader/config.toml "$BACKUP_DIR/" 2>/dev/null || true
cp /etc/udev/rules.d/*.rules "$BACKUP_DIR/" 2>/dev/null || true
cp /etc/default/grub "$BACKUP_DIR/" 2>/dev/null || true
sysctl -a > "$BACKUP_DIR/sysctl-before.txt" 2>/dev/null || true

# -----------------------------------------------------------------------------
# 1. CPU governor -> performance
# -----------------------------------------------------------------------------
log "Setting CPU governor to performance..."
if command -v cpupower >/dev/null 2>&1; then
    cpupower frequency-set -g performance >/dev/null
else
    for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        echo performance > "$gov"
    done
fi

# Persist governor
log "Creating cpupower systemd service..."
systemctl enable --now cpupower.service 2>/dev/null || true

# -----------------------------------------------------------------------------
# 2. Sysctl VM / scheduler / network tuning for 16 GB RAM + AI agents
# -----------------------------------------------------------------------------
log "Applying sysctl tuning..."
cat > /etc/sysctl.d/99-performance-tuning.conf <<'EOF'
# VM tuning for 16 GB RAM + heavy zram/agent workloads
vm.swappiness = 150
vm.vfs_cache_pressure = 50
vm.watermark_scale_factor = 125
vm.page-cluster = 0
vm.dirty_ratio = 20
vm.dirty_background_ratio = 10
vm.overcommit_memory = 1
vm.overcommit_ratio = 100

# Scheduler latency tuning
kernel.sched_latency_ns = 24000000
kernel.sched_min_granularity_ns = 3000000
kernel.sched_wakeup_granularity_ns = 4000000
kernel.sched_migration_cost_ns = 5000000
kernel.sched_autogroup_enabled = 0

# Network throughput and low latency
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65536
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 10
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.tcp_no_metrics_save = 1
net.ipv4.ip_local_port_range = 10000 65535
net.netfilter.nf_conntrack_max = 1048576

# File descriptors
fs.file-max = 2097152
fs.nr_open = 2097152
EOF

sysctl --system >/dev/null

# Load tcp_bbr if available
modprobe tcp_bbr 2>/dev/null || warn "tcp_bbr module not available"

# -----------------------------------------------------------------------------
# 3. sched-ext scheduler
# -----------------------------------------------------------------------------
log "Configuring sched-ext with scx_flow..."
mkdir -p /etc/scx_loader
cat > /etc/scx_loader/config.toml <<'EOF'
default_sched = "scx_flow"
default_mode = "Auto"

[scheds.scx_flow]
auto_mode = []

[scheds.scx_lavd]
auto_mode = ["--autopilot"]
EOF

log "Stopping ananicy-cpp (conflicts with sched-ext) and enabling scx_loader..."
systemctl disable --now ananicy-cpp.service 2>/dev/null || true
systemctl enable --now scx_loader.service 2>/dev/null || true

# -----------------------------------------------------------------------------
# 4. IRQ balance
# -----------------------------------------------------------------------------
log "Enabling irqbalance..."
if ! command -v irqbalance >/dev/null 2>&1; then
    pacman -S --noconfirm --needed irqbalance 2>/dev/null || warn "Could not install irqbalance"
fi
systemctl enable --now irqbalance.service 2>/dev/null || true

# -----------------------------------------------------------------------------
# 5. I/O scheduler udev rules
# -----------------------------------------------------------------------------
log "Ensuring NVMe I/O scheduler is 'none'..."
cat > /etc/udev/rules.d/60-ioscheduler.rules <<'EOF'
# NVMe: use none (multi-queue native)
ACTION=="add|change", KERNEL=="nvme[0-9]n[0-9]", ATTR{queue/scheduler}="none", ATTR{queue/nr_requests}="1024"
# SSD: use mq-deadline
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
# HDD: use bfq
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="bfq"
EOF
udevadm control --reload-rules
udevadm trigger --subsystem-match=block

# -----------------------------------------------------------------------------
# 6. USB autosuspend rules for input + DAC
# -----------------------------------------------------------------------------
log "Disabling USB autosuspend for input devices and Topping DX5..."
cat > /etc/udev/rules.d/50-usb-low-latency.rules <<'EOF'
# Input devices: keep powered
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{product}=="*Mouse*", TEST=="power/control", ATTR{power/control}="on"
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{product}=="*Keyboard*", TEST=="power/control", ATTR{power/control}="on"

# Wooting 60HE
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="31e3", ATTR{idProduct}=="1312", TEST=="power/control", ATTR{power/control}="on"

# Topping DX5 DAC
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="152a", ATTR{idProduct}=="8750", TEST=="power/control", ATTR{power/control}="on"

# Blue Snowball mic
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="0d8c", ATTR{idProduct}=="0005", TEST=="power/control", ATTR{power/control}="on"
EOF
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb

# -----------------------------------------------------------------------------
# 7. Transparent huge pages
# -----------------------------------------------------------------------------
log "Enabling transparent huge pages..."
if [ -f /sys/kernel/mm/transparent_hugepage/enabled ]; then
    echo always > /sys/kernel/mm/transparent_hugepage/enabled
fi

# -----------------------------------------------------------------------------
# 8. NVIDIA performance mode
# -----------------------------------------------------------------------------
if command -v nvidia-settings >/dev/null 2>&1 && command -v nvidia-smi >/dev/null 2>&1; then
    log "Setting NVIDIA persistence mode and PowerMizer preference..."
    nvidia-smi -pm 1 2>/dev/null || warn "Could not enable persistence mode"
    nvidia-settings -a '[gpu:0]/GPUPowerMizerMode=1' 2>/dev/null || warn "Could not set PowerMizer mode"
fi

# -----------------------------------------------------------------------------
# 9. Kernel cmdline reminder
# -----------------------------------------------------------------------------
warn "Boot-time parameters must be changed manually. Add to kernel cmdline:"
echo "    intel_pstate=passive threadirqs processor.max_cstate=1 intel_idle.max_cstate=1"
echo "    rcupdate.rcu_normal_after_boot=1 rcutree.enable_rcu_lazy=1 mitigations=off"
echo ""
warn "If using GRUB: edit /etc/default/grub, then run: sudo grub-mkconfig -o /boot/grub/grub.cfg"
warn "If using systemd-boot: edit /boot/loader/entries/*.conf"

# -----------------------------------------------------------------------------
# 10. Verification
# -----------------------------------------------------------------------------
log "Current status after tuning:"
echo "--- Governor ---"
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
echo "--- scx_loader ---"
systemctl is-active scx_loader || true
echo "--- irqbalance ---"
systemctl is-active irqbalance || true
echo "--- TCP congestion ---"
sysctl -n net.ipv4.tcp_congestion_control
echo "--- swappiness ---"
sysctl -n vm.swappiness

log "Performance tuning applied. Backup saved to $BACKUP_DIR"
log "Reboot recommended for kernel cmdline changes to take effect."
