#!/bin/bash
# 2-export-packages.sh - Export and convert package lists for CachyOS
# Based on: repos/migrate/research/package-migration-strategy.md

set -euo pipefail

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# Configuration
EXPORT_DIR="$(dirname "$(readlink -f "$0")")/../package-export"
LOG_DIR="$(dirname "$(readlink -f "$0")")/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/export-packages-$DATE.log"

mkdir -p "$EXPORT_DIR" "$LOG_DIR"

log() { echo -e "${GREEN}[$( date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========${NC}\n" | tee -a "$LOG_FILE"; }

# Package name conversion rules
convert_package_name() {
    local pkg="$1"

    # Remove -dev suffix
    pkg="${pkg%-dev}"

    # python3- → python-
    pkg="${pkg/python3-/python-}"

    # Remove version numbers from lib packages
    pkg=$(echo "$pkg" | sed 's/-[0-9]\+\.[0-9]\+$//')

    # Remove -common, -bin suffixes
    pkg="${pkg%-common}"
    pkg="${pkg%-bin}"

    echo "$pkg"
}

# Export APT packages
export_apt() {
    log_section "Exporting APT Packages"

    if ! command -v apt &> /dev/null; then
        log_warn "APT not found, skipping"
        return
    fi

    log "Exporting manually installed packages..."
    comm -23 \
        <(apt-mark showmanual | sort -u) \
        <(gzip -dc /var/log/installer/initial-status.gz 2>/dev/null | sed -n 's/^Package: //p' | sort -u || echo "") \
        > "$EXPORT_DIR/apt-manual.txt"

    log "Exporting all installed packages with versions..."
    dpkg -l | awk '/^ii/ {print $2 "=" $3}' > "$EXPORT_DIR/apt-all-versioned.txt"

    log "Creating conversion mapping..."
    > "$EXPORT_DIR/ubuntu-to-arch-mapping.txt"

    while IFS= read -r pkg; do
        # Remove version if present
        pkg_name="${pkg%=*}"
        arch_name=$(convert_package_name "$pkg_name")

        if [[ "$pkg_name" != "$arch_name" ]]; then
            echo "$pkg_name → $arch_name" >> "$EXPORT_DIR/ubuntu-to-arch-mapping.txt"
        fi
    done < "$EXPORT_DIR/apt-manual.txt"

    log "APT packages exported: $(wc -l < "$EXPORT_DIR/apt-manual.txt") manual packages"
}

# Export language-specific packages
export_language_packages() {
    log_section "Exporting Language Package Managers"

    # NPM
    if command -v npm &> /dev/null; then
        log "Exporting NPM global packages..."
        npm list -g --depth=0 --json > "$EXPORT_DIR/npm-global.json" 2>/dev/null || true
        npm list -g --depth=0 | awk 'NR>1 {print $2}' | sed 's/@.*//' > "$EXPORT_DIR/npm-packages.txt" 2>/dev/null || true
    fi

    # Pip
    if command -v pip3 &> /dev/null; then
        log "Exporting pip packages..."
        pip3 freeze > "$EXPORT_DIR/pip-requirements.txt" 2>/dev/null || true
    fi

    # Cargo
    if command -v cargo &> /dev/null; then
        log "Exporting cargo packages..."
        cargo install --list | grep -v '^\s' > "$EXPORT_DIR/cargo-packages.txt" 2>/dev/null || true
    fi

    # Gem
    if command -v gem &> /dev/null; then
        log "Exporting gem packages..."
        gem list --no-versions > "$EXPORT_DIR/gem-packages.txt" 2>/dev/null || true
    fi
}

# Export universal package formats
export_universal_packages() {
    log_section "Exporting Universal Package Formats"

    # Flatpak
    if command -v flatpak &> /dev/null; then
        log "Exporting Flatpak apps..."
        flatpak list --app --columns=application > "$EXPORT_DIR/flatpak-apps.txt" 2>/dev/null || true
    fi

    # Snap (will need manual conversion to Flatpak/AUR on Arch)
    if command -v snap &> /dev/null; then
        log "Exporting Snap packages (manual conversion needed)..."
        snap list | awk 'NR>1 {print $1}' > "$EXPORT_DIR/snap-packages.txt" 2>/dev/null || true
        log_warn "Snap packages will need manual conversion to Flatpak or AUR equivalents"
    fi
}

# Generate installation script for CachyOS
generate_install_script() {
    log_section "Generating CachyOS Installation Script"

    cat > "$EXPORT_DIR/install-on-cachyos.sh" << 'INSTALL_SCRIPT'
#!/bin/bash
# Auto-generated installation script for CachyOS
# Run this on the new CachyOS system

set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

echo "Installing packages on CachyOS..."

# Install paru (AUR helper) if not present
if ! command -v paru &> /dev/null; then
    echo "Installing paru..."
    sudo pacman -S --needed base-devel git
    git clone https://aur.archlinux.org/paru.git /tmp/paru
    cd /tmp/paru
    makepkg -si --noconfirm
    cd -
    rm -rf /tmp/paru
fi

# Install converted packages from mapping
if [[ -f "$SCRIPT_DIR/ubuntu-to-arch-mapping.txt" ]]; then
    echo "Installing converted system packages..."
    awk '{print $3}' "$SCRIPT_DIR/ubuntu-to-arch-mapping.txt" | while read pkg; do
        paru -S --needed --noconfirm "$pkg" || echo "Failed to install: $pkg"
    done
fi

# Restore language package managers
echo "Restoring language-specific packages..."

# NPM
if [[ -f "$SCRIPT_DIR/npm-packages.txt" ]] && command -v npm &> /dev/null; then
    echo "Installing NPM packages..."
    xargs npm install -g < "$SCRIPT_DIR/npm-packages.txt" || true
fi

# Pip
if [[ -f "$SCRIPT_DIR/pip-requirements.txt" ]] && command -v pip &> /dev/null; then
    echo "Installing pip packages..."
    pip install -r "$SCRIPT_DIR/pip-requirements.txt" || true
fi

# Cargo
if [[ -f "$SCRIPT_DIR/cargo-packages.txt" ]] && command -v cargo &> /dev/null; then
    echo "Installing cargo packages..."
    while read pkg; do
        cargo install "$pkg" || true
    done < "$SCRIPT_DIR/cargo-packages.txt"
fi

# Flatpak
if [[ -f "$SCRIPT_DIR/flatpak-apps.txt" ]] && command -v flatpak &> /dev/null; then
    echo "Installing Flatpak apps..."
    while read app; do
        flatpak install -y "$app" || true
    done < "$SCRIPT_DIR/flatpak-apps.txt"
fi

echo "Package installation complete!"
echo "Check for any failed packages and install manually if needed."
INSTALL_SCRIPT

    chmod +x "$EXPORT_DIR/install-on-cachyos.sh"
    log "Installation script generated: $EXPORT_DIR/install-on-cachyos.sh"
}

# Generate summary report
generate_summary() {
    log_section "Export Summary"

    cat > "$EXPORT_DIR/SUMMARY.txt" << EOF
Package Export Summary
Generated: $(date)

System Packages (APT):
  - Manual packages: $(wc -l < "$EXPORT_DIR/apt-manual.txt" 2>/dev/null || echo "0")
  - Conversion mappings: $(wc -l < "$EXPORT_DIR/ubuntu-to-arch-mapping.txt" 2>/dev/null || echo "0")

Language Packages:
  - NPM global: $(wc -l < "$EXPORT_DIR/npm-packages.txt" 2>/dev/null || echo "0")
  - Pip: $(wc -l < "$EXPORT_DIR/pip-requirements.txt" 2>/dev/null || echo "0")
  - Cargo: $(wc -l < "$EXPORT_DIR/cargo-packages.txt" 2>/dev/null || echo "0")
  - Gem: $(wc -l < "$EXPORT_DIR/gem-packages.txt" 2>/dev/null || echo "0")

Universal Packages:
  - Flatpak: $(wc -l < "$EXPORT_DIR/flatpak-apps.txt" 2>/dev/null || echo "0")
  - Snap: $(wc -l < "$EXPORT_DIR/snap-packages.txt" 2>/dev/null || echo "0") (needs manual conversion)

Files:
  - apt-manual.txt: Manually installed packages
  - ubuntu-to-arch-mapping.txt: Package name conversions
  - install-on-cachyos.sh: Automated installation script
  - *-packages.txt: Language-specific package lists

Next Steps:
  1. Review ubuntu-to-arch-mapping.txt for accuracy
  2. Check snap-packages.txt and find AUR/Flatpak equivalents
  3. Copy this directory to CachyOS system
  4. Run ./install-on-cachyos.sh

EOF

    cat "$EXPORT_DIR/SUMMARY.txt"
}

# Main execution
main() {
    log "Starting package export process..."
    log "Export directory: $EXPORT_DIR"

    export_apt
    export_language_packages
    export_universal_packages
    generate_install_script
    generate_summary

    log ""
    log "${GREEN}✅ Package export completed successfully!${NC}"
    log "📁 Export location: $EXPORT_DIR"
    log "📝 Log file: $LOG_FILE"
}

main
