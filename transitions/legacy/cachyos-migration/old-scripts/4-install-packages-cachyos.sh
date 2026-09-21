#!/bin/bash
# 4-install-packages-cachyos.sh - Install packages on CachyOS from exported lists
# Based on: repos/migrate/research/package-migration-strategy.md
#
# This script runs ON the NEW CachyOS system to install packages
# Run after: 2-export-packages.sh on Ubuntu system

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
EXPORT_DIR="${EXPORT_DIR:-$SCRIPT_DIR/../package-export}"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/install-packages-$DATE.log"

mkdir -p "$LOG_DIR"

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========${NC}\n" | tee -a "$LOG_FILE"; }

error_exit() {
    log_error "$1"
    exit 1
}

# Verify we're on Arch/CachyOS
if [[ ! -f /etc/arch-release ]]; then
    error_exit "This script must run on Arch Linux / CachyOS"
fi

# Verify export directory exists
if [[ ! -d "$EXPORT_DIR" ]]; then
    error_exit "Export directory not found: $EXPORT_DIR"
fi

# ===================================
# PARU (AUR HELPER) INSTALLATION
# ===================================

install_paru() {
    log_section "Installing paru (AUR helper)"

    if command -v paru &> /dev/null; then
        log "paru already installed: $(paru --version)"
        return 0
    fi

    log "Installing base-devel and git..."
    sudo pacman -S --needed --noconfirm base-devel git || error_exit "Failed to install dependencies"

    log "Cloning paru from AUR..."
    local tmpdir=$(mktemp -d)
    git clone https://aur.archlinux.org/paru.git "$tmpdir/paru" || error_exit "Failed to clone paru"

    log "Building and installing paru..."
    cd "$tmpdir/paru"
    makepkg -si --noconfirm || error_exit "Failed to build paru"
    cd -
    rm -rf "$tmpdir"

    log "paru installed successfully"
}

# ===================================
# SYSTEM PACKAGES (PACMAN/AUR)
# ===================================

install_system_packages() {
    log_section "Installing System Packages from Converted Mapping"

    local mapping_file="$EXPORT_DIR/ubuntu-to-arch-mapping.txt"
    local manual_file="$EXPORT_DIR/apt-manual.txt"

    if [[ ! -f "$mapping_file" ]]; then
        log_warn "No mapping file found: $mapping_file"
        log_warn "Attempting direct installation from apt-manual.txt"
        mapping_file="$manual_file"
    fi

    if [[ ! -f "$mapping_file" ]]; then
        log_warn "No package list found, skipping system packages"
        return 0
    fi

    log "Processing package list: $mapping_file"

    local installed=0
    local failed=0
    local skipped=0

    # Extract Arch package names (3rd column if mapping file, whole line if manual)
    local packages=()
    if [[ "$mapping_file" == *"mapping"* ]]; then
        packages=($(awk '{print $3}' "$mapping_file" | sort -u))
    else
        packages=($(cat "$mapping_file" | sort -u))
    fi

    log "Found ${#packages[@]} packages to install"

    # Create failed packages log
    local failed_log="$LOG_DIR/failed-packages-$DATE.txt"
    > "$failed_log"

    for pkg in "${packages[@]}"; do
        # Skip empty lines
        [[ -z "$pkg" ]] && continue

        # Skip known problematic conversions
        if [[ "$pkg" =~ ^(base-files|init|systemd-sysv|ubuntu-)$ ]]; then
            log "Skipping Ubuntu-specific package: $pkg"
            ((skipped++))
            continue
        fi

        log "Installing: $pkg"

        # Try official repos first, then AUR
        if sudo pacman -S --needed --noconfirm "$pkg" 2>>"$LOG_FILE"; then
            ((installed++))
            log "  ✅ Installed from official repos"
        elif paru -S --needed --noconfirm "$pkg" 2>>"$LOG_FILE"; then
            ((installed++))
            log "  ✅ Installed from AUR"
        else
            ((failed++))
            log_warn "  ❌ Failed to install: $pkg"
            echo "$pkg" >> "$failed_log"
        fi
    done

    log ""
    log "System package installation summary:"
    log "  ✅ Installed: $installed"
    log "  ❌ Failed: $failed"
    log "  ⏭️  Skipped: $skipped"

    if [[ $failed -gt 0 ]]; then
        log_warn "Failed packages logged to: $failed_log"
        log_warn "Review and install manually if needed"
    fi
}

# ===================================
# LANGUAGE PACKAGE MANAGERS
# ===================================

install_npm_packages() {
    log_section "Installing NPM Global Packages"

    local npm_file="$EXPORT_DIR/npm-packages.txt"

    if [[ ! -f "$npm_file" ]]; then
        log_warn "NPM package list not found: $npm_file"
        return 0
    fi

    if ! command -v npm &> /dev/null; then
        log "Installing Node.js and npm..."
        sudo pacman -S --needed --noconfirm nodejs npm || log_warn "Failed to install npm"
        return 1
    fi

    log "Installing global NPM packages..."
    local installed=0
    local failed=0

    while IFS= read -r pkg; do
        [[ -z "$pkg" ]] && continue

        log "Installing npm package: $pkg"
        if npm install -g "$pkg" 2>>"$LOG_FILE"; then
            ((installed++))
        else
            ((failed++))
            log_warn "Failed to install npm package: $pkg"
        fi
    done < "$npm_file"

    log "NPM packages installed: $installed, failed: $failed"
}

install_pip_packages() {
    log_section "Installing Python Pip Packages"

    local pip_file="$EXPORT_DIR/pip-requirements.txt"

    if [[ ! -f "$pip_file" ]]; then
        log_warn "Pip package list not found: $pip_file"
        return 0
    fi

    if ! command -v pip &> /dev/null; then
        log "Installing Python and pip..."
        sudo pacman -S --needed --noconfirm python python-pip || log_warn "Failed to install pip"
        return 1
    fi

    log "Installing pip packages from requirements..."
    if pip install --user -r "$pip_file" 2>>"$LOG_FILE"; then
        log "Pip packages installed successfully"
    else
        log_warn "Some pip packages failed to install"
    fi
}

install_cargo_packages() {
    log_section "Installing Cargo (Rust) Packages"

    local cargo_file="$EXPORT_DIR/cargo-packages.txt"

    if [[ ! -f "$cargo_file" ]]; then
        log_warn "Cargo package list not found: $cargo_file"
        return 0
    fi

    if ! command -v cargo &> /dev/null; then
        log "Installing Rust and Cargo..."
        sudo pacman -S --needed --noconfirm rust cargo || log_warn "Failed to install cargo"
        return 1
    fi

    log "Installing cargo packages..."
    local installed=0
    local failed=0

    while IFS= read -r line; do
        # Extract package name (first word before version)
        local pkg=$(echo "$line" | awk '{print $1}')
        [[ -z "$pkg" ]] && continue

        log "Installing cargo package: $pkg"
        if cargo install "$pkg" 2>>"$LOG_FILE"; then
            ((installed++))
        else
            ((failed++))
            log_warn "Failed to install cargo package: $pkg"
        fi
    done < "$cargo_file"

    log "Cargo packages installed: $installed, failed: $failed"
}

install_gem_packages() {
    log_section "Installing Ruby Gem Packages"

    local gem_file="$EXPORT_DIR/gem-packages.txt"

    if [[ ! -f "$gem_file" ]]; then
        log_warn "Gem package list not found: $gem_file"
        return 0
    fi

    if ! command -v gem &> /dev/null; then
        log "Installing Ruby..."
        sudo pacman -S --needed --noconfirm ruby || log_warn "Failed to install ruby"
        return 1
    fi

    log "Installing gem packages..."
    local installed=0
    local failed=0

    while IFS= read -r pkg; do
        [[ -z "$pkg" ]] && continue
        # Skip default gems
        [[ "$pkg" =~ ^(bigdecimal|io-console|json|psych|rdoc)$ ]] && continue

        log "Installing gem: $pkg"
        if gem install "$pkg" --user-install 2>>"$LOG_FILE"; then
            ((installed++))
        else
            ((failed++))
            log_warn "Failed to install gem: $pkg"
        fi
    done < "$gem_file"

    log "Gem packages installed: $installed, failed: $failed"
}

# ===================================
# UNIVERSAL PACKAGE FORMATS
# ===================================

install_flatpak_apps() {
    log_section "Installing Flatpak Applications"

    local flatpak_file="$EXPORT_DIR/flatpak-apps.txt"

    if [[ ! -f "$flatpak_file" ]]; then
        log_warn "Flatpak app list not found: $flatpak_file"
        return 0
    fi

    if ! command -v flatpak &> /dev/null; then
        log "Installing Flatpak..."
        sudo pacman -S --needed --noconfirm flatpak || log_warn "Failed to install flatpak"

        log "Adding Flathub repository..."
        flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    fi

    log "Installing Flatpak apps..."
    local installed=0
    local failed=0

    while IFS= read -r app; do
        [[ -z "$app" ]] && continue

        log "Installing Flatpak app: $app"
        if flatpak install -y flathub "$app" 2>>"$LOG_FILE"; then
            ((installed++))
        else
            ((failed++))
            log_warn "Failed to install Flatpak app: $app"
        fi
    done < "$flatpak_file"

    log "Flatpak apps installed: $installed, failed: $failed"
}

handle_snap_packages() {
    log_section "Snap Package Conversion"

    local snap_file="$EXPORT_DIR/snap-packages.txt"

    if [[ ! -f "$snap_file" ]]; then
        log "No snap packages to convert"
        return 0
    fi

    log_warn "Snap packages require manual conversion to Flatpak or AUR equivalents"
    log "Snap packages found:"

    cat "$snap_file" | tee -a "$LOG_FILE"

    log ""
    log "Suggested conversions (review manually):"
    log "  - code (VSCode) → Install from AUR: paru -S visual-studio-code-bin"
    log "  - spotify → Flatpak: flatpak install flathub com.spotify.Client"
    log "  - discord → Flatpak: flatpak install flathub com.discordapp.Discord"
    log "  - Check AUR and Flathub for other equivalents"

    echo "Snap package conversion needed" > "$LOG_DIR/snap-conversion-$DATE.txt"
    cat "$snap_file" >> "$LOG_DIR/snap-conversion-$DATE.txt"
}

# ===================================
# VERIFICATION
# ===================================

verify_installation() {
    log_section "Installation Verification"

    log "Checking installed package managers..."

    local status="✅ INSTALLED"
    local missing="❌ MISSING"

    echo "Package Managers:" | tee -a "$LOG_FILE"
    command -v pacman &> /dev/null && echo "  pacman: $status" || echo "  pacman: $missing"
    command -v paru &> /dev/null && echo "  paru: $status" || echo "  paru: $missing"
    command -v npm &> /dev/null && echo "  npm: $status" || echo "  npm: $missing"
    command -v pip &> /dev/null && echo "  pip: $status" || echo "  pip: $missing"
    command -v cargo &> /dev/null && echo "  cargo: $status" || echo "  cargo: $missing"
    command -v gem &> /dev/null && echo "  gem: $status" || echo "  gem: $missing"
    command -v flatpak &> /dev/null && echo "  flatpak: $status" || echo "  flatpak: $missing"

    log ""
    log "Package counts:"
    echo "  Pacman packages: $(pacman -Q | wc -l)"
    command -v npm &> /dev/null && echo "  NPM global: $(npm list -g --depth=0 2>/dev/null | tail -n +2 | wc -l)"
    command -v pip &> /dev/null && echo "  Pip packages: $(pip list 2>/dev/null | tail -n +3 | wc -l)"
    command -v cargo &> /dev/null && echo "  Cargo packages: $(cargo install --list 2>/dev/null | grep -c '^ ' || echo 0)"
    command -v flatpak &> /dev/null && echo "  Flatpak apps: $(flatpak list --app 2>/dev/null | wc -l)"
}

# ===================================
# SUMMARY
# ===================================

generate_summary() {
    log_section "Installation Summary"

    local summary_file="$LOG_DIR/install-summary-$DATE.txt"

    cat > "$summary_file" << EOF
CachyOS Package Installation Summary
Generated: $(date)

Export Source: $EXPORT_DIR
Installation Log: $LOG_FILE

Package Installation Status:
$(verify_installation 2>&1)

Next Steps:
1. Review failed packages log (if exists): $LOG_DIR/failed-packages-$DATE.txt
2. Manually install critical failed packages
3. Convert Snap packages (see: $LOG_DIR/snap-conversion-$DATE.txt)
4. Run configuration script: 5-configure-system.sh
5. Restore dotfiles and configs: 6-restore-configs.sh

Notes:
- Some Ubuntu-specific packages were skipped (systemd-sysv, ubuntu-*, etc.)
- Check AUR for Ubuntu package equivalents if needed
- Language-specific packages (npm, pip, cargo, gem) are cross-platform
- Flatpak apps should work identically to Ubuntu

EOF

    cat "$summary_file"
}

# ===================================
# MAIN EXECUTION
# ===================================

main() {
    log "Starting package installation on CachyOS..."
    log "Export directory: $EXPORT_DIR"
    log "Log file: $LOG_FILE"

    # Install paru first
    install_paru

    # Update system before installing packages
    log_section "Updating System"
    log "Running system update..."
    sudo pacman -Syu --noconfirm || log_warn "System update had warnings"

    # Install packages in order
    install_system_packages
    install_npm_packages
    install_pip_packages
    install_cargo_packages
    install_gem_packages
    install_flatpak_apps
    handle_snap_packages

    # Verify and summarize
    verify_installation
    generate_summary

    log ""
    log "${GREEN}✅ Package installation completed!${NC}"
    log "📁 Export source: $EXPORT_DIR"
    log "📝 Log file: $LOG_FILE"
    log ""
    log "⚠️  Important:"
    log "  - Review $LOG_DIR/failed-packages-$DATE.txt for packages that need manual installation"
    log "  - Check $LOG_DIR/snap-conversion-$DATE.txt for Snap package alternatives"
    log "  - Next: Run 5-configure-system.sh to apply system optimizations"
}

main
