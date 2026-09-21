#!/usr/bin/env bash
# 05-setup-dev-services.sh - Install dev toolchains, enable services, apply system tuning
# Merges dev tools setup with system optimizations from old 5-configure-system.sh
#
# Run after: 02-deploy-dotfiles.sh
# Requires: base packages from 01-install-packages.sh

set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$DOTFILES/logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/setup-dev-services-$DATE.log"
mkdir -p "$LOG_DIR"

log()         { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn()    { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error()   { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }

backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        sudo cp -a "$file" "${file}.pre-migration-$DATE"
        log "  Backed up: $file"
    fi
}

# Track what was configured for the summary
declare -a CONFIGURED=()

# =============================================================================
# 1. NVM + Node.js
# =============================================================================
setup_nvm_node() {
    log_section "NVM + Node.js"

    # Use AUR-installed nvm (from /usr/share/nvm) — don't curl a duplicate
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [[ -s /usr/share/nvm/init-nvm.sh ]]; then
        source /usr/share/nvm/init-nvm.sh
        log "Loaded nvm from AUR package (/usr/share/nvm)"
    elif [[ -s "$NVM_DIR/nvm.sh" ]]; then
        source "$NVM_DIR/nvm.sh"
        log "Loaded nvm from $NVM_DIR"
    else
        log_warn "nvm not found — install via: paru -S nvm"
        return 1
    fi

    log "Installing Node.js 24..."
    nvm install 24
    nvm alias default 24
    nvm use 24
    log "Node $(node --version) active"

    log "Installing global npm packages..."
    npm install -g pnpm typescript ts-node nodemon
    log "Global packages: pnpm, typescript, ts-node, nodemon"

    CONFIGURED+=("Node.js $(node --version) via nvm, global packages installed")
}

# =============================================================================
# 2. Rust toolchain
# =============================================================================
setup_rust() {
    log_section "Rust Toolchain"

    if ! command -v rustup &>/dev/null; then
        log "Installing rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
        # shellcheck source=/dev/null
        source "$HOME/.cargo/env"
    else
        log "rustup already installed"
    fi

    log "Setting stable toolchain as default..."
    rustup default stable

    log "Installing components: clippy, rustfmt, rust-analyzer..."
    rustup component add clippy rustfmt rust-analyzer

    log "Rust $(rustc --version | awk '{print $2}') ready"
    CONFIGURED+=("Rust $(rustc --version | awk '{print $2}') with clippy, rustfmt, rust-analyzer")
}

# =============================================================================
# 3. Docker
# =============================================================================
setup_docker() {
    log_section "Docker"

    if ! command -v docker &>/dev/null; then
        log_warn "Docker not found -- install via 01-install-packages.sh first"
        return 0
    fi

    log "Enabling and starting Docker service..."
    sudo systemctl enable --now docker

    if ! id -nG "$USER" | grep -qw docker; then
        log "Adding $USER to docker group..."
        sudo usermod -aG docker "$USER"
        log_warn "Log out and back in for docker group to take effect"
    else
        log "User $USER already in docker group"
    fi

    log "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    CONFIGURED+=("Docker enabled, user added to docker group")
}

# =============================================================================
# 4. System services
# =============================================================================
setup_services() {
    log_section "System Services"

    local services=(tailscaled ollama NetworkManager bluetooth cronie)

    for svc in "${services[@]}"; do
        if systemctl list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}.service"; then
            log "Enabling ${svc}..."
            sudo systemctl enable --now "${svc}.service" 2>/dev/null \
                && CONFIGURED+=("Service: ${svc}") \
                || log_warn "Failed to enable ${svc} (may need package installed)"
        else
            log_warn "${svc}.service not found -- skipping"
        fi
    done
}

# =============================================================================
# 5. Sysctl tuning
# =============================================================================
setup_sysctl() {
    log_section "Sysctl Tuning"

    local target="/etc/sysctl.d/99-custom.conf"
    backup_file "$target"

    # Detect zram — CachyOS uses zram by default, which benefits from high swappiness
    if [[ -e /sys/block/zram0 ]]; then
        SWAPPINESS=180
        log "zram detected — using vm.swappiness=$SWAPPINESS"
    else
        SWAPPINESS=10
        log "No zram — using vm.swappiness=$SWAPPINESS"
    fi

    log "Writing optimized sysctl parameters..."
    sudo tee "$target" > /dev/null << 'EOF'
# Custom sysctl tuning -- dev workstation
# Generated by 05-setup-dev-services.sh

# File system
fs.file-max = 2097152
fs.nr_open = 2097152
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 512

# Virtual memory
vm.swappiness = 10
vm.max_map_count = 1048576
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
vm.vfs_cache_pressure = 50

# Network
net.core.somaxconn = 65535
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2

# Process limits
kernel.pid_max = 4194304
kernel.threads-max = 4194304
EOF

    # Apply dynamic swappiness (heredoc was single-quoted so we patch it)
    sudo sed -i "s/^vm.swappiness = .*/vm.swappiness = $SWAPPINESS/" "$target"

    log "Applying sysctl..."
    sudo sysctl --system 2>&1 | tail -1 | tee -a "$LOG_FILE"
    CONFIGURED+=("Sysctl: file-max 2M, swappiness $SWAPPINESS, inotify 524k watches")
}

# =============================================================================
# 6. I/O Scheduler udev rules
# =============================================================================
setup_io_scheduler() {
    log_section "I/O Scheduler (udev rules)"

    local target="/etc/udev/rules.d/60-io-scheduler.rules"
    backup_file "$target"

    log "Writing I/O scheduler udev rules..."
    sudo tee "$target" > /dev/null << 'EOF'
# I/O scheduler optimization
# NVMe: no scheduler needed (hardware handles it)
ACTION=="add|change", KERNEL=="nvme[0-9]n[0-9]", ATTR{queue/scheduler}="none"
# SSD: mq-deadline for balanced latency
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
# HDD: bfq for fairness
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="bfq"
EOF

    log "Reloading udev rules..."
    sudo udevadm control --reload-rules && sudo udevadm trigger
    CONFIGURED+=("I/O scheduler: none(NVMe), mq-deadline(SSD), bfq(HDD)")
}

# =============================================================================
# 7. PAM / systemd limits
# =============================================================================
setup_limits() {
    log_section "PAM / systemd Limits"

    local target="/etc/security/limits.d/99-custom.conf"
    backup_file "$target"

    log "Writing file and process limits..."
    sudo tee "$target" > /dev/null << 'EOF'
* soft nofile 1048576
* hard nofile 1048576
* soft nproc  65535
* hard nproc  65535
EOF

    CONFIGURED+=("Limits: nofile 1M, nproc 64k")
}

# =============================================================================
# 8. Summary
# =============================================================================
print_summary() {
    log_section "Setup Complete"

    echo -e "${GREEN}Configured:${NC}" | tee -a "$LOG_FILE"
    for item in "${CONFIGURED[@]}"; do
        echo -e "  ${GREEN}+${NC} $item" | tee -a "$LOG_FILE"
    done

    echo "" | tee -a "$LOG_FILE"
    log "Log saved to: $LOG_FILE"
    log_warn "Reboot recommended to apply all kernel/limits changes"
    log_warn "Log out/in required for docker group membership"
}

# =============================================================================
# Main
# =============================================================================
main() {
    log "Starting dev services setup..."
    log "Dotfiles repo: $DOTFILES"

    setup_nvm_node
    setup_rust
    setup_docker
    setup_services
    setup_sysctl
    setup_io_scheduler
    setup_limits
    print_summary
}

main "$@"
