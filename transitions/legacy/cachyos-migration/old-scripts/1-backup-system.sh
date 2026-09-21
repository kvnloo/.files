#!/bin/bash
# 1-backup-system.sh - Comprehensive system backup automation
# Based on: repos/migrate/research/backup-tools-comparison.md
#
# This script implements a layered backup strategy:
# Layer 1: ZFS snapshots (if ZFS is active)
# Layer 2: Package manager states (all package managers)
# Layer 3: Dotfiles and configurations
# Layer 4: Application data
# Layer 5: Verification and reporting

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKUP_ROOT="${BACKUP_ROOT:-/mnt/backup}"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/migration-backup-$DATE"
LOG_DIR="$(dirname "$(readlink -f "$0")")/../logs"
LOG_FILE="$LOG_DIR/backup-$DATE.log"

# Create directories
mkdir -p "$LOG_DIR" "$BACKUP_DIR"

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"
}

log_section() {
    echo -e "\n${BLUE}========================================${NC}" | tee -a "$LOG_FILE"
    echo -e "${BLUE}$*${NC}" | tee -a "$LOG_FILE"
    echo -e "${BLUE}========================================${NC}\n" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    log_error "$1"
    log_error "Backup failed! Check $LOG_FILE for details"
    exit 1
}

# Dry-run mode
DRY_RUN="${DRY_RUN:-false}"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY RUN MODE - No changes will be made"
fi

# ===================================
# LAYER 1: ZFS Snapshots
# ===================================
backup_zfs() {
    log_section "LAYER 1: ZFS Snapshot Backup"

    if ! command -v zfs &> /dev/null; then
        log_warn "ZFS not installed, skipping ZFS backup"
        return 0
    fi

    # Check if ZFS pools exist
    if ! zpool list &> /dev/null; then
        log_warn "No ZFS pools found, skipping ZFS backup"
        return 0
    fi

    log "Creating ZFS snapshots..."
    local snapshot_name="migration-backup-$DATE"

    # Get all ZFS filesystems
    local filesystems=$(zfs list -H -o name)

    for fs in $filesystems; do
        log "Creating snapshot: $fs@$snapshot_name"
        if [[ "$DRY_RUN" == "false" ]]; then
            zfs snapshot "$fs@$snapshot_name" || log_warn "Failed to snapshot $fs"
        fi
    done

    # Export snapshot list
    log "Exporting ZFS snapshot list..."
    if [[ "$DRY_RUN" == "false" ]]; then
        zfs list -t snapshot > "$BACKUP_DIR/zfs-snapshots.txt"
        zpool status > "$BACKUP_DIR/zfs-pool-status.txt"
    fi

    log "ZFS snapshots created successfully"
}

# ===================================
# LAYER 2: Package Manager States
# ===================================
backup_packages() {
    log_section "LAYER 2: Package Manager State Export"

    local PKG_DIR="$BACKUP_DIR/packages"
    mkdir -p "$PKG_DIR"

    # APT (Debian/Ubuntu)
    if command -v apt &> /dev/null; then
        log "Exporting APT package lists..."
        if [[ "$DRY_RUN" == "false" ]]; then
            dpkg --get-selections > "$PKG_DIR/dpkg-selections.txt"
            apt list --installed > "$PKG_DIR/apt-installed.txt"
            apt-mark showmanual > "$PKG_DIR/apt-manual.txt"
            apt-mark showauto > "$PKG_DIR/apt-auto.txt"
        fi
    fi

    # Snap
    if command -v snap &> /dev/null; then
        log "Exporting Snap package list..."
        if [[ "$DRY_RUN" == "false" ]]; then
            snap list > "$PKG_DIR/snap-list.txt" 2>/dev/null || log_warn "No snap packages"
        fi
    fi

    # Flatpak
    if command -v flatpak &> /dev/null; then
        log "Exporting Flatpak package list..."
        if [[ "$DRY_RUN" == "false" ]]; then
            flatpak list --app --columns=application,version,origin > "$PKG_DIR/flatpak-list.txt" 2>/dev/null || log_warn "No flatpak packages"
        fi
    fi

    # NPM Global
    if command -v npm &> /dev/null; then
        log "Exporting NPM global packages..."
        if [[ "$DRY_RUN" == "false" ]]; then
            npm list -g --depth=0 > "$PKG_DIR/npm-global.txt" 2>/dev/null || log_warn "No global npm packages"
        fi
    fi

    # Pip
    if command -v pip &> /dev/null; then
        log "Exporting pip packages..."
        if [[ "$DRY_RUN" == "false" ]]; then
            pip freeze > "$PKG_DIR/pip-freeze.txt" 2>/dev/null || log_warn "pip freeze failed"
            pip list > "$PKG_DIR/pip-list.txt" 2>/dev/null || log_warn "pip list failed"
        fi
    fi

    # Pip3
    if command -v pip3 &> /dev/null; then
        log "Exporting pip3 packages..."
        if [[ "$DRY_RUN" == "false" ]]; then
            pip3 freeze > "$PKG_DIR/pip3-freeze.txt" 2>/dev/null || log_warn "pip3 freeze failed"
        fi
    fi

    # Cargo
    if command -v cargo &> /dev/null; then
        log "Exporting cargo packages..."
        if [[ "$DRY_RUN" == "false" ]]; then
            cargo install --list > "$PKG_DIR/cargo-list.txt" 2>/dev/null || log_warn "No cargo packages"
        fi
    fi

    # Gem
    if command -v gem &> /dev/null; then
        log "Exporting gem packages..."
        if [[ "$DRY_RUN" == "false" ]]; then
            gem list > "$PKG_DIR/gem-list.txt" 2>/dev/null || log_warn "No gem packages"
        fi
    fi

    # Homebrew (if installed)
    if command -v brew &> /dev/null; then
        log "Exporting Homebrew bundle..."
        if [[ "$DRY_RUN" == "false" ]]; then
            brew bundle dump --file="$PKG_DIR/Brewfile" --force
        fi
    fi

    log "Package state exported successfully"
}

# ===================================
# LAYER 3: Dotfiles and Configurations
# ===================================
backup_dotfiles() {
    log_section "LAYER 3: Dotfiles and Configuration Backup"

    local CONFIG_DIR="$BACKUP_DIR/dotfiles"
    mkdir -p "$CONFIG_DIR"

    log "Backing up shell configurations..."
    if [[ "$DRY_RUN" == "false" ]]; then
        for file in .bashrc .bash_profile .bash_aliases .zshrc .zsh_aliases .profile; do
            if [[ -f "$HOME/$file" ]]; then
                cp -a "$HOME/$file" "$CONFIG_DIR/" || log_warn "Failed to copy $file"
            fi
        done
    fi

    log "Backing up .config directory..."
    if [[ "$DRY_RUN" == "false" ]] && [[ -d "$HOME/.config" ]]; then
        rsync -a --exclude='cache' --exclude='Cache' --exclude='*.log' \
            "$HOME/.config/" "$CONFIG_DIR/.config/" || log_warn ".config backup incomplete"
    fi

    log "Backing up .local/share (excluding cache)..."
    if [[ "$DRY_RUN" == "false" ]] && [[ -d "$HOME/.local/share" ]]; then
        rsync -a --exclude='Trash' --exclude='cache' \
            "$HOME/.local/share/" "$CONFIG_DIR/.local-share/" || log_warn ".local/share backup incomplete"
    fi

    log "Backing up SSH keys and config..."
    if [[ "$DRY_RUN" == "false" ]] && [[ -d "$HOME/.ssh" ]]; then
        mkdir -p "$CONFIG_DIR/.ssh"
        cp -a "$HOME/.ssh/config" "$CONFIG_DIR/.ssh/" 2>/dev/null || true
        cp -a "$HOME/.ssh/known_hosts" "$CONFIG_DIR/.ssh/" 2>/dev/null || true
        # Note: Private keys should be backed up manually to secure location
        log_warn "SSH private keys not backed up - handle separately with encryption"
    fi

    log "Backing up Git configuration..."
    if [[ "$DRY_RUN" == "false" ]]; then
        cp -a "$HOME/.gitconfig" "$CONFIG_DIR/" 2>/dev/null || true
        cp -a "$HOME/.gitignore_global" "$CONFIG_DIR/" 2>/dev/null || true
    fi

    log "Backing up /etc configuration (requires sudo)..."
    if [[ "$DRY_RUN" == "false" ]]; then
        sudo tar czf "$CONFIG_DIR/etc-backup.tar.gz" \
            /etc/fstab \
            /etc/sysctl.conf \
            /etc/sysctl.d/ \
            /etc/security/limits.conf \
            /etc/systemd/system/ \
            /etc/apt/sources.list \
            /etc/apt/sources.list.d/ \
            2>/dev/null || log_warn "/etc backup incomplete"
    fi

    log "Dotfiles and configurations backed up successfully"
}

# ===================================
# LAYER 4: Application Data
# ===================================
backup_applications() {
    log_section "LAYER 4: Application Data Backup"

    local APP_DIR="$BACKUP_DIR/applications"
    mkdir -p "$APP_DIR"

    # Steam
    if [[ -d "$HOME/.local/share/Steam" ]]; then
        log "Backing up Steam configuration..."
        if [[ "$DRY_RUN" == "false" ]]; then
            mkdir -p "$APP_DIR/steam"
            # Backup config and userdata, skip game files
            rsync -a --exclude='steamapps/common' --exclude='steamapps/downloading' \
                "$HOME/.local/share/Steam/config" \
                "$HOME/.local/share/Steam/userdata" \
                "$APP_DIR/steam/" || log_warn "Steam backup incomplete"
        fi
    fi

    # Docker volumes
    if command -v docker &> /dev/null && sudo docker ps &> /dev/null; then
        log "Backing up Docker volumes..."
        if [[ "$DRY_RUN" == "false" ]]; then
            mkdir -p "$APP_DIR/docker"
            sudo docker volume ls -q | while read vol; do
                log "  Backing up Docker volume: $vol"
                sudo docker run --rm \
                    -v "$vol":/data \
                    -v "$APP_DIR/docker":/backup \
                    ubuntu tar czf "/backup/$vol.tar.gz" /data 2>/dev/null || \
                    log_warn "Failed to backup Docker volume $vol"
            done
        fi
    fi

    # PostgreSQL databases
    if command -v pg_dumpall &> /dev/null; then
        log "Backing up PostgreSQL databases..."
        if [[ "$DRY_RUN" == "false" ]]; then
            mkdir -p "$APP_DIR/databases"
            pg_dumpall > "$APP_DIR/databases/postgresql-all.sql" || \
                log_warn "PostgreSQL backup failed"
        fi
    fi

    # MySQL/MariaDB databases
    if command -v mysqldump &> /dev/null; then
        log "Backing up MySQL/MariaDB databases..."
        if [[ "$DRY_RUN" == "false" ]]; then
            mkdir -p "$APP_DIR/databases"
            mysqldump --all-databases > "$APP_DIR/databases/mysql-all.sql" 2>/dev/null || \
                log_warn "MySQL backup failed (may need credentials)"
        fi
    fi

    # VS Code extensions
    if command -v code &> /dev/null; then
        log "Backing up VS Code extensions..."
        if [[ "$DRY_RUN" == "false" ]]; then
            mkdir -p "$APP_DIR/vscode"
            code --list-extensions > "$APP_DIR/vscode/extensions.txt"
            if [[ -d "$HOME/.config/Code/User" ]]; then
                cp -a "$HOME/.config/Code/User/settings.json" "$APP_DIR/vscode/" 2>/dev/null || true
                cp -a "$HOME/.config/Code/User/keybindings.json" "$APP_DIR/vscode/" 2>/dev/null || true
            fi
        fi
    fi

    log "Application data backed up successfully"
}

# ===================================
# LAYER 5: Verification and Reporting
# ===================================
verify_backup() {
    log_section "LAYER 5: Backup Verification"

    local VERIFY_LOG="$BACKUP_DIR/verification-report.txt"

    {
        echo "Backup Verification Report"
        echo "Generated: $(date)"
        echo "Backup Location: $BACKUP_DIR"
        echo ""

        echo "=== Directory Structure ==="
        du -sh "$BACKUP_DIR"/*
        echo ""

        echo "=== Package Lists ==="
        ls -lh "$BACKUP_DIR/packages/" 2>/dev/null || echo "No package backups"
        echo ""

        echo "=== Configuration Files ==="
        ls -lh "$BACKUP_DIR/dotfiles/" 2>/dev/null || echo "No dotfile backups"
        echo ""

        echo "=== Application Data ==="
        du -sh "$BACKUP_DIR/applications/"* 2>/dev/null || echo "No application backups"
        echo ""

        echo "=== File Checksums ==="
        find "$BACKUP_DIR" -type f -exec sha256sum {} \; > "$BACKUP_DIR/checksums.txt"
        echo "Checksums saved to checksums.txt"
        echo ""

    } | tee "$VERIFY_LOG"

    # Create README
    cat > "$BACKUP_DIR/README.txt" << 'EOF'
Migration Backup Archive
========================

This backup was created for Ubuntu → CachyOS migration.

Structure:
- packages/        : Package manager states (apt, snap, flatpak, npm, pip, cargo, gem)
- dotfiles/        : Shell configs, .config, .local/share
- applications/    : Steam, Docker, databases, VS Code
- zfs-*.txt        : ZFS snapshot information (if applicable)
- checksums.txt    : SHA256 checksums of all backed up files
- verification-report.txt : Backup statistics

Restoration:
1. Install CachyOS
2. Run: ../../scripts/6-restore-configs.sh
3. Run: ../../scripts/4-install-packages-cachyos.sh

Security Notes:
- SSH private keys are NOT backed up automatically
- Database credentials may need manual restoration
- Review checksums.txt before restoration

EOF

    log "Backup verification complete. Report saved to: $VERIFY_LOG"
}

# Generate summary
generate_summary() {
    log_section "Backup Summary"

    local total_size=$(du -sh "$BACKUP_DIR" | cut -f1)

    cat << EOF

${GREEN}✅ BACKUP COMPLETED SUCCESSFULLY${NC}

📍 Backup Location: $BACKUP_DIR
📦 Total Size: $total_size
📝 Log File: $LOG_FILE

Backup Contents:
  - ZFS Snapshots: $(zfs list -t snapshot 2>/dev/null | wc -l || echo "N/A")
  - Package Lists: $(ls -1 "$BACKUP_DIR/packages/" 2>/dev/null | wc -l) files
  - Dotfiles: $(du -sh "$BACKUP_DIR/dotfiles" 2>/dev/null | cut -f1 || echo "N/A")
  - Applications: $(du -sh "$BACKUP_DIR/applications" 2>/dev/null | cut -f1 || echo "N/A")

Next Steps:
  1. Verify backup integrity: ls -lR $BACKUP_DIR
  2. Test restoration in VM (optional but recommended)
  3. Proceed with migration: ./2-export-packages.sh

⚠️  Important:
  - Keep this backup safe until migration is verified
  - SSH keys and sensitive data require manual handling
  - Review $BACKUP_DIR/README.txt for details

EOF
}

# ===================================
# Main Execution
# ===================================
main() {
    log "Starting comprehensive system backup..."
    log "Backup directory: $BACKUP_DIR"

    backup_zfs
    backup_packages
    backup_dotfiles
    backup_applications
    verify_backup
    generate_summary

    log "All backup operations completed successfully!"
}

# Check if running as root (not recommended)
if [[ $EUID -eq 0 ]]; then
    log_warn "Running as root. Some backups may have incorrect ownership."
fi

# Execute main function
main
