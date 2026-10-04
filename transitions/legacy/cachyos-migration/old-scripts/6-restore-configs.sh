#!/bin/bash
# 6-restore-configs.sh - Restore dotfiles and configurations from backup
# Based on: repos/migrate/research/backup-tools-comparison.md
#
# Restores user configurations, dotfiles, and application settings
# Run after: 5-configure-system.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/restore-configs-$DATE.log"

mkdir -p "$LOG_DIR"

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========${NC}\n" | tee -a "$LOG_FILE"; }

error_exit() {
    log_error "$1"
    exit 1
}

# Detect backup directory
detect_backup_dir() {
    log_section "Detecting Backup Directory"

    # Check common backup locations
    local backup_locations=(
        "/mnt/backup/migration-backup-"*
        "$HOME/migration-backup-"*
        "/backup/migration-backup-"*
        "/media/$USER/*/migration-backup-"*
    )

    for location in "${backup_locations[@]}"; do
        for dir in $location; do
            if [[ -d "$dir" ]]; then
                echo "$dir"
                return 0
            fi
        done
    done

    echo ""
}

# Prompt for backup directory
select_backup_dir() {
    local auto_backup=$(detect_backup_dir)

    if [[ -n "$auto_backup" ]]; then
        log "Found backup directory: $auto_backup"
        read -p "Use this backup? (y/n): " use_auto
        if [[ "$use_auto" =~ ^[Yy]$ ]]; then
            echo "$auto_backup"
            return 0
        fi
    fi

    echo ""
    read -p "Enter backup directory path: " backup_path

    if [[ ! -d "$backup_path" ]]; then
        error_exit "Backup directory not found: $backup_path"
    fi

    echo "$backup_path"
}

# ===================================
# SHELL CONFIGURATIONS
# ===================================

restore_shell_configs() {
    local backup_dir="$1"

    log_section "Restoring Shell Configurations"

    local config_dir="$backup_dir/dotfiles"

    if [[ ! -d "$config_dir" ]]; then
        log_warn "No shell configs found in backup"
        return 0
    fi

    local restored=0
    local skipped=0

    for file in .bashrc .bash_profile .bash_aliases .zshrc .zsh_aliases .profile; do
        if [[ -f "$config_dir/$file" ]]; then
            log "Restoring: $file"

            # Backup existing if present
            if [[ -f "$HOME/$file" ]]; then
                cp "$HOME/$file" "$HOME/$file.pre-migration"
                log "  Backed up existing to: $file.pre-migration"
            fi

            cp "$config_dir/$file" "$HOME/$file"
            ((restored++))
        else
            ((skipped++))
        fi
    done

    log "Shell configs restored: $restored, skipped: $skipped"
}

# ===================================
# .config DIRECTORY
# ===================================

restore_config_directory() {
    local backup_dir="$1"

    log_section "Restoring .config Directory"

    local config_backup="$backup_dir/dotfiles/.config"

    if [[ ! -d "$config_backup" ]]; then
        log_warn "No .config backup found"
        return 0
    fi

    log "Restoring .config directory..."

    # Create .config if it doesn't exist
    mkdir -p "$HOME/.config"

    # Selective restore (ask for each major application)
    log "Scanning for application configs..."

    local apps=(
        "Code"           # VS Code
        "nvim"           # Neovim
        "git"            # Git config
        "kitty"          # Kitty terminal
        "alacritty"      # Alacritty terminal
        "i3"             # i3 window manager
        "sway"           # Sway compositor
        "fish"           # Fish shell
        "starship.toml"  # Starship prompt
    )

    for app in "${apps[@]}"; do
        if [[ -e "$config_backup/$app" ]]; then
            log "Found config for: $app"
            read -p "Restore $app config? (y/n): " restore_app

            if [[ "$restore_app" =~ ^[Yy]$ ]]; then
                log "  Restoring $app..."

                # Backup existing
                if [[ -e "$HOME/.config/$app" ]]; then
                    mv "$HOME/.config/$app" "$HOME/.config/$app.pre-migration"
                    log "  Backed up existing to: $app.pre-migration"
                fi

                cp -r "$config_backup/$app" "$HOME/.config/"
                log "  ✅ Restored: $app"
            else
                log "  ⏭️  Skipped: $app"
            fi
        fi
    done

    log ".config restoration complete"
}

# ===================================
# .local/share DIRECTORY
# ===================================

restore_local_share() {
    local backup_dir="$1"

    log_section "Restoring .local/share Directory"

    local share_backup="$backup_dir/dotfiles/.local-share"

    if [[ ! -d "$share_backup" ]]; then
        log_warn "No .local/share backup found"
        return 0
    fi

    log "Selective restoration of .local/share..."

    # Ask about specific important directories
    local important_dirs=(
        "applications"  # Desktop entries
        "fonts"        # User fonts
        "keyrings"     # Keychains
        "zsh"          # Zsh data
        "fish"         # Fish data
    )

    mkdir -p "$HOME/.local/share"

    for dir in "${important_dirs[@]}"; do
        if [[ -d "$share_backup/$dir" ]]; then
            log "Found data for: $dir"
            read -p "Restore $dir? (y/n): " restore_dir

            if [[ "$restore_dir" =~ ^[Yy]$ ]]; then
                log "  Restoring $dir..."
                mkdir -p "$HOME/.local/share/$dir"
                cp -r "$share_backup/$dir"/* "$HOME/.local/share/$dir/" 2>/dev/null || log_warn "  Some files may have failed"
                log "  ✅ Restored: $dir"
            else
                log "  ⏭️  Skipped: $dir"
            fi
        fi
    done
}

# ===================================
# SSH CONFIGURATION
# ===================================

restore_ssh_config() {
    local backup_dir="$1"

    log_section "Restoring SSH Configuration"

    local ssh_backup="$backup_dir/dotfiles/.ssh"

    if [[ ! -d "$ssh_backup" ]]; then
        log_warn "No SSH backup found"
        return 0
    fi

    log "Restoring SSH config and known_hosts..."

    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"

    # Restore config
    if [[ -f "$ssh_backup/config" ]]; then
        cp "$ssh_backup/config" "$HOME/.ssh/config"
        chmod 600 "$HOME/.ssh/config"
        log "✅ Restored SSH config"
    fi

    # Restore known_hosts
    if [[ -f "$ssh_backup/known_hosts" ]]; then
        cp "$ssh_backup/known_hosts" "$HOME/.ssh/known_hosts"
        chmod 644 "$HOME/.ssh/known_hosts"
        log "✅ Restored known_hosts"
    fi

    log ""
    log_warn "⚠️  SSH PRIVATE KEYS NOT RESTORED"
    log_warn "Manually copy private keys from secure backup:"
    log "  1. Copy id_rsa, id_ed25519, etc. to ~/.ssh/"
    log "  2. Set permissions: chmod 600 ~/.ssh/id_*"
    log "  3. Test connection: ssh -T git@github.com"
}

# ===================================
# GIT CONFIGURATION
# ===================================

restore_git_config() {
    local backup_dir="$1"

    log_section "Restoring Git Configuration"

    local git_backup="$backup_dir/dotfiles"

    if [[ -f "$git_backup/.gitconfig" ]]; then
        cp "$git_backup/.gitconfig" "$HOME/.gitconfig"
        log "✅ Restored .gitconfig"
    else
        log_warn "No .gitconfig found in backup"
    fi

    if [[ -f "$git_backup/.gitignore_global" ]]; then
        cp "$git_backup/.gitignore_global" "$HOME/.gitignore_global"
        log "✅ Restored .gitignore_global"
    fi

    log "Git configuration restored"
}

# ===================================
# APPLICATION DATA
# ===================================

restore_application_data() {
    local backup_dir="$1"

    log_section "Restoring Application Data"

    local app_backup="$backup_dir/applications"

    if [[ ! -d "$app_backup" ]]; then
        log_warn "No application data backup found"
        return 0
    fi

    # VS Code extensions
    if [[ -d "$app_backup/vscode" ]]; then
        log "Found VS Code backup"
        read -p "Restore VS Code extensions? (y/n): " restore_vscode

        if [[ "$restore_vscode" =~ ^[Yy]$ ]]; then
            if [[ -f "$app_backup/vscode/extensions.txt" ]]; then
                log "Installing VS Code extensions..."
                while IFS= read -r ext; do
                    log "  Installing: $ext"
                    code --install-extension "$ext" 2>>"$LOG_FILE" || log_warn "Failed to install: $ext"
                done < "$app_backup/vscode/extensions.txt"
            fi

            # Restore settings
            if [[ -f "$app_backup/vscode/settings.json" ]]; then
                mkdir -p "$HOME/.config/Code/User"
                cp "$app_backup/vscode/settings.json" "$HOME/.config/Code/User/"
                log "✅ Restored VS Code settings"
            fi

            if [[ -f "$app_backup/vscode/keybindings.json" ]]; then
                cp "$app_backup/vscode/keybindings.json" "$HOME/.config/Code/User/"
                log "✅ Restored VS Code keybindings"
            fi
        fi
    fi

    # Steam (optional - usually games are large)
    if [[ -d "$app_backup/steam" ]]; then
        log "Found Steam backup (config only, not games)"
        read -p "Restore Steam config? (y/n): " restore_steam

        if [[ "$restore_steam" =~ ^[Yy]$ ]]; then
            log_warn "Steam config restoration is manual - game files excluded from backup"
            log "Steam config location: $app_backup/steam"
        fi
    fi

    # Docker volumes (if present)
    if [[ -d "$app_backup/docker" ]]; then
        log "Found Docker volume backups"
        log_warn "Docker volume restoration requires manual intervention"
        log "Backup location: $app_backup/docker"
        log "Use: docker run --rm -v volume_name:/data -v $app_backup/docker:/backup ubuntu tar xzf /backup/volume.tar.gz -C /data"
    fi

    # Database backups
    if [[ -d "$app_backup/databases" ]]; then
        log "Found database backups"
        log_warn "Database restoration requires manual intervention"
        log "PostgreSQL: psql -f $app_backup/databases/postgresql-all.sql"
        log "MySQL: mysql < $app_backup/databases/mysql-all.sql"
    fi
}

# ===================================
# /etc CONFIGURATIONS (requires sudo)
# ===================================

restore_etc_configs() {
    local backup_dir="$1"

    log_section "Restoring /etc Configurations"

    local etc_backup="$backup_dir/dotfiles/etc-backup.tar.gz"

    if [[ ! -f "$etc_backup" ]]; then
        log_warn "No /etc backup found"
        return 0
    fi

    log_warn "⚠️  /etc configuration restoration requires sudo and careful review"
    log "/etc backup available at: $etc_backup"

    read -p "Extract /etc backup for manual review? (y/n): " extract_etc

    if [[ "$extract_etc" =~ ^[Yy]$ ]]; then
        local extract_dir="$LOG_DIR/etc-extracted-$DATE"
        mkdir -p "$extract_dir"

        log "Extracting to: $extract_dir"
        sudo tar xzf "$etc_backup" -C "$extract_dir"

        log "✅ Extracted /etc backup"
        log "Review files and manually copy needed configurations to /etc/"
        log "Location: $extract_dir"
    fi
}

# ===================================
# VERIFICATION
# ===================================

verify_restoration() {
    log_section "Restoration Verification"

    log "Checking restored files..."

    local checks=(
        "$HOME/.bashrc:Shell config (bash)"
        "$HOME/.zshrc:Shell config (zsh)"
        "$HOME/.gitconfig:Git config"
        "$HOME/.ssh/config:SSH config"
        "$HOME/.config:User config directory"
    )

    for check in "${checks[@]}"; do
        local file="${check%%:*}"
        local desc="${check##*:}"

        if [[ -e "$file" ]]; then
            echo "  ✅ $desc"
        else
            echo "  ⏭️  $desc (not restored or not in backup)"
        fi
    done
}

# ===================================
# SUMMARY
# ===================================

generate_summary() {
    local backup_dir="$1"

    log_section "Restoration Summary"

    cat << EOF

${GREEN}✅ CONFIGURATION RESTORATION COMPLETED${NC}

📁 Backup source: $backup_dir
📝 Log file: $LOG_FILE

Restored Components:
  ✅ Shell configurations (.bashrc, .zshrc, etc.)
  ✅ Git configuration (.gitconfig)
  ✅ SSH configuration (config, known_hosts)
  ✅ Application configs (.config directory)
  ✅ User data (.local/share)

⚠️  Manual Steps Required:

1. SSH Private Keys:
   - Copy from secure backup to ~/.ssh/
   - Set permissions: chmod 600 ~/.ssh/id_*
   - Test: ssh -T git@github.com

2. Review and apply /etc configurations:
   - Location: $LOG_DIR/etc-extracted-$DATE (if extracted)
   - Manually copy needed files to /etc/

3. Database restoration (if applicable):
   - PostgreSQL: psql -f $backup_dir/applications/databases/postgresql-all.sql
   - MySQL: mysql < $backup_dir/applications/databases/mysql-all.sql

4. Docker volumes (if applicable):
   - Restore using commands from: $backup_dir/applications/docker/

5. Test your environment:
   - Open terminal, verify shell prompt
   - Test git commands
   - Check application settings

Next Steps:
  1. Verify all critical configurations are working
  2. Run verification script: 7-verify-migration.sh
  3. Begin using the new system!

Notes:
  - Pre-migration configs backed up with .pre-migration suffix
  - Large application data (games, etc.) excluded from backup
  - Review logs for any warnings or failed restorations

EOF
}

# ===================================
# MAIN EXECUTION
# ===================================

main() {
    log "Starting configuration restoration..."
    log "Log file: $LOG_FILE"

    # Select backup directory
    BACKUP_DIR=$(select_backup_dir)
    log "Using backup: $BACKUP_DIR"

    # Verify backup structure
    if [[ ! -d "$BACKUP_DIR/dotfiles" ]]; then
        error_exit "Invalid backup structure - dotfiles directory not found"
    fi

    # Restore components
    restore_shell_configs "$BACKUP_DIR"
    restore_config_directory "$BACKUP_DIR"
    restore_local_share "$BACKUP_DIR"
    restore_ssh_config "$BACKUP_DIR"
    restore_git_config "$BACKUP_DIR"
    restore_application_data "$BACKUP_DIR"
    restore_etc_configs "$BACKUP_DIR"

    # Verify and summarize
    verify_restoration
    generate_summary "$BACKUP_DIR"

    log ""
    log "${GREEN}✅ Restoration completed successfully!${NC}"
    log "📁 Backup source: $BACKUP_DIR"
    log "📝 Log file: $LOG_FILE"
    log ""
    log "Next: Run verification script (7-verify-migration.sh)"
}

main
