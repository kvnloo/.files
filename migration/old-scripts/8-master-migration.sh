#!/bin/bash
# 8-master-migration.sh - Master orchestration script for complete migration
# Coordinates all migration scripts with progress tracking and error handling
#
# Usage: sudo ./8-master-migration.sh [--skip-backup] [--auto-confirm]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/master-migration-$DATE.log"
CHECKPOINT_FILE="$LOG_DIR/migration-checkpoint.txt"

mkdir -p "$LOG_DIR"

# Migration stages
declare -a STAGES=(
    "backup:1-backup-system.sh:Comprehensive system backup"
    "export:2-export-packages.sh:Export and convert package lists"
    "partition:3-partition-disk.sh:Partition and format disks"
    "install:4-install-packages-cachyos.sh:Install packages on CachyOS"
    "configure:5-configure-system.sh:Apply system optimizations"
    "restore:6-restore-configs.sh:Restore configurations"
    "verify:7-verify-migration.sh:Verify migration success"
)

# Command line options
SKIP_BACKUP=false
AUTO_CONFIRM=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --auto-confirm)
            AUTO_CONFIRM=true
            shift
            ;;
        --help|-h)
            cat << EOF
Ubuntu → CachyOS Migration Master Script

Usage: sudo ./8-master-migration.sh [OPTIONS]

Options:
  --skip-backup      Skip backup stage (use existing backup)
  --auto-confirm     Automatically confirm all prompts (DANGEROUS!)
  --help, -h         Show this help message

Migration Stages:
  1. Backup         - Full system backup (ZFS, packages, configs, apps)
  2. Export         - Package list export and conversion mapping
  3. Partition      - Disk partitioning (Ubuntu system, interactive)
  4. Install        - Package installation (CachyOS system)
  5. Configure      - System optimization (CachyOS system)
  6. Restore        - Configuration restoration (CachyOS system)
  7. Verify         - Migration verification (CachyOS system)

Migration Phases:
  Phase 1 (Ubuntu):  Stages 1-3 (backup, export, partition)
  Phase 2 (Install): Ubuntu + CachyOS installation (manual)
  Phase 3 (CachyOS): Stages 4-7 (install, configure, restore, verify)

Important:
  - Stages 1-3 run on Ubuntu BEFORE OS installation
  - Install Ubuntu and CachyOS using prepared partitions
  - Stages 4-7 run on CachyOS AFTER installation
  - Run with sudo for system modifications
  - Review logs in: $LOG_DIR/

EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Logging functions
log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${CYAN}${BOLD}═══════════════════════════════════════════════════${NC}" | tee -a "$LOG_FILE"; echo -e "${CYAN}${BOLD}  $*${NC}" | tee -a "$LOG_FILE"; echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════${NC}\n" | tee -a "$LOG_FILE"; }
log_stage() { echo -e "\n${BLUE}${BOLD}▶ STAGE $1: $2${NC}\n" | tee -a "$LOG_FILE"; }

# Checkpoint management
save_checkpoint() {
    local stage="$1"
    echo "$stage:$(date +%s)" >> "$CHECKPOINT_FILE"
    log "Checkpoint saved: $stage"
}

get_last_checkpoint() {
    if [[ -f "$CHECKPOINT_FILE" ]]; then
        tail -1 "$CHECKPOINT_FILE" | cut -d: -f1
    else
        echo ""
    fi
}

is_stage_completed() {
    local stage="$1"
    if [[ -f "$CHECKPOINT_FILE" ]]; then
        grep -q "^$stage:" "$CHECKPOINT_FILE"
    else
        return 1
    fi
}

# Confirmation prompt
confirm() {
    local message="$1"

    if [[ "$AUTO_CONFIRM" == "true" ]]; then
        log_warn "Auto-confirm enabled, proceeding automatically"
        return 0
    fi

    echo -e "${YELLOW}$message${NC}"
    read -p "Continue? (y/n): " response

    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Operation cancelled by user"
        exit 1
    fi
}

# Stage execution
execute_stage() {
    local stage_id="$1"
    local script="$2"
    local description="$3"
    local stage_num="$4"

    log_stage "$stage_num" "$description"

    # Check if already completed
    if is_stage_completed "$stage_id"; then
        log_warn "Stage '$stage_id' already completed (found in checkpoint)"
        read -p "Re-run this stage? (y/n): " rerun

        if [[ ! "$rerun" =~ ^[Yy]$ ]]; then
            log "Skipping stage: $stage_id"
            return 0
        fi
    fi

    # Confirm execution
    confirm "⚠️  About to execute: $script"

    # Execute script
    local script_path="$SCRIPT_DIR/$script"

    if [[ ! -f "$script_path" ]]; then
        log_error "Script not found: $script_path"
        return 1
    fi

    log "Executing: $script_path"

    local start_time=$(date +%s)

    if bash "$script_path"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log "${GREEN}✅ Stage completed successfully${NC} (${duration}s)"
        save_checkpoint "$stage_id"
        return 0
    else
        local exit_code=$?
        log_error "❌ Stage failed with exit code: $exit_code"
        log_error "Check logs for details: $LOG_DIR/"
        return $exit_code
    fi
}

# System detection
detect_system() {
    if [[ -f /etc/arch-release ]]; then
        echo "cachyos"
    elif [[ -f /etc/lsb-release ]]; then
        if grep -q "Ubuntu" /etc/lsb-release; then
            echo "ubuntu"
        else
            echo "unknown"
        fi
    else
        echo "unknown"
    fi
}

# Phase determination
get_current_phase() {
    local system=$(detect_system)
    local last_checkpoint=$(get_last_checkpoint)

    if [[ "$system" == "ubuntu" ]]; then
        if [[ -z "$last_checkpoint" ]] || [[ "$last_checkpoint" == "backup" ]] || [[ "$last_checkpoint" == "export" ]]; then
            echo "phase1"
        elif [[ "$last_checkpoint" == "partition" ]]; then
            echo "phase2"
        else
            echo "unknown"
        fi
    elif [[ "$system" == "cachyos" ]]; then
        echo "phase3"
    else
        echo "unknown"
    fi
}

# Display migration overview
show_migration_overview() {
    log_section "MIGRATION OVERVIEW"

    cat << EOF
${BOLD}Ubuntu → CachyOS Dual-Boot Migration${NC}

${BOLD}Phase 1: Preparation (Ubuntu System)${NC}
  Stage 1: Backup         - Full system backup
  Stage 2: Export         - Package list export and conversion
  Stage 3: Partition      - Disk partitioning and formatting

${BOLD}Phase 2: Installation (Manual)${NC}
  - Install Ubuntu on prepared partitions
  - Install CachyOS on prepared partitions
  - Configure dual-boot (systemd-boot or GRUB)

${BOLD}Phase 3: Finalization (CachyOS System)${NC}
  Stage 4: Install        - Package installation
  Stage 5: Configure      - System optimization
  Stage 6: Restore        - Configuration restoration
  Stage 7: Verify         - Migration verification

${BOLD}Current Status:${NC}
  System: $(detect_system)
  Phase: $(get_current_phase)
  Last checkpoint: $(get_last_checkpoint || echo "None")

${BOLD}Logs Directory:${NC} $LOG_DIR

EOF
}

# Phase 1 execution (Ubuntu)
execute_phase1() {
    log_section "PHASE 1: PREPARATION (Ubuntu System)"

    log "This phase runs on your current Ubuntu system"
    log "It will backup data, export packages, and partition disks"

    confirm "⚠️  Ready to start Phase 1 on Ubuntu system?"

    # Stage 1: Backup
    if [[ "$SKIP_BACKUP" == "true" ]]; then
        log_warn "Skipping backup stage (--skip-backup flag)"
    else
        execute_stage "backup" "1-backup-system.sh" "Comprehensive System Backup" "1/3" || return 1
    fi

    # Stage 2: Export
    execute_stage "export" "2-export-packages.sh" "Package Export and Conversion" "2/3" || return 1

    # Stage 3: Partition (requires user interaction)
    log_warn "⚠️  CRITICAL: Next stage will DESTROY ALL DATA on selected disks!"
    execute_stage "partition" "3-partition-disk.sh" "Disk Partitioning" "3/3" || return 1

    log_section "PHASE 1 COMPLETED"

    cat << EOF

${GREEN}✅ Phase 1 completed successfully!${NC}

${BOLD}Next Steps:${NC}

1. ${BOLD}Review the partition layout:${NC}
   lsblk -f
   cat $LOG_DIR/fstab-entries-*.txt

2. ${BOLD}Install Ubuntu:${NC}
   - Boot from Ubuntu installer
   - Select "Something else" for partitioning
   - Use prepared partitions (DO NOT format again)
   - Install bootloader to EFI partition

3. ${BOLD}Install CachyOS:${NC}
   - Boot from CachyOS installer
   - Use manual partitioning
   - Use prepared partitions (DO NOT format again)
   - Share EFI partition with Ubuntu

4. ${BOLD}After both OS installations, boot into CachyOS and run:${NC}
   sudo ./8-master-migration.sh

This will execute Phase 3 (stages 4-7) to complete the migration.

${BOLD}Backup Location:${NC} $(ls -d /mnt/backup/migration-backup-* 2>/dev/null || echo "See backup script output")
${BOLD}Package Export:${NC} $SCRIPT_DIR/../package-export/

EOF
}

# Phase 3 execution (CachyOS)
execute_phase3() {
    log_section "PHASE 3: FINALIZATION (CachyOS System)"

    log "This phase runs on your new CachyOS system"
    log "It will install packages, configure system, restore configs, and verify"

    confirm "⚠️  Ready to start Phase 3 on CachyOS system?"

    # Stage 4: Install packages
    execute_stage "install" "4-install-packages-cachyos.sh" "Package Installation" "4/7" || return 1

    # Stage 5: Configure system
    execute_stage "configure" "5-configure-system.sh" "System Configuration" "5/7" || return 1

    log_warn "⚠️  System configuration applied. Reboot recommended before continuing."
    read -p "Reboot now? (y/n): " do_reboot

    if [[ "$do_reboot" =~ ^[Yy]$ ]]; then
        log "System will reboot in 10 seconds..."
        log "After reboot, run this script again to continue with stages 6-7"
        sleep 10
        reboot
    fi

    # Stage 6: Restore configs
    execute_stage "restore" "6-restore-configs.sh" "Configuration Restoration" "6/7" || return 1

    # Stage 7: Verify
    execute_stage "verify" "7-verify-migration.sh" "Migration Verification" "7/7" || return 1

    log_section "PHASE 3 COMPLETED"

    cat << EOF

${GREEN}✅ Phase 3 completed successfully!${NC}
${GREEN}🎉 MIGRATION COMPLETE!${NC}

${BOLD}Verification Report:${NC} $LOG_DIR/migration-report-*.txt

${BOLD}Next Steps:${NC}

1. ${BOLD}Review verification report${NC} for any issues
2. ${BOLD}Test your applications and workflows${NC}
3. ${BOLD}Set up regular backups${NC} using 1-backup-system.sh
4. ${BOLD}Verify dual-boot${NC} by rebooting and selecting Ubuntu
5. ${BOLD}Test workspace access${NC} from both Ubuntu and CachyOS

${BOLD}Important Files:${NC}
  - Logs: $LOG_DIR/
  - Verification: $LOG_DIR/migration-report-*.txt
  - Backup: $(ls -d /mnt/backup/migration-backup-* 2>/dev/null | head -1 || echo "See backup logs")

${BOLD}Enjoy your optimized dual-boot setup!${NC}

For issues or questions, refer to:
  - Migration research: repos/migrate/research/
  - Script logs: $LOG_DIR/
  - Individual script help: ./[script-name].sh --help

EOF
}

# Main execution
main() {
    # Banner
    cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     UBUNTU → CACHYOS DUAL-BOOT MIGRATION                      ║
║     Master Orchestration Script                               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

EOF

    log "Migration master script started"
    log "Log file: $LOG_FILE"
    log "Checkpoint file: $CHECKPOINT_FILE"

    # Root check
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi

    # Show overview
    show_migration_overview

    # Detect phase
    local current_phase=$(get_current_phase)
    local current_system=$(detect_system)

    log "Detected system: $current_system"
    log "Detected phase: $current_phase"

    case "$current_phase" in
        phase1)
            execute_phase1
            ;;
        phase2)
            cat << EOF
${YELLOW}⚠️  Phase 2: OS Installation Required${NC}

Disk partitioning is complete. Next steps:

1. Install Ubuntu using the prepared partitions
2. Install CachyOS using the prepared partitions
3. Configure dual-boot bootloader
4. Boot into CachyOS
5. Run this script again to continue with Phase 3

Partition layout: $LOG_DIR/fstab-entries-*.txt

EOF
            ;;
        phase3)
            execute_phase3
            ;;
        unknown)
            log_error "Unable to determine migration phase"
            log_error "System: $current_system"
            log_error "Last checkpoint: $(get_last_checkpoint || echo "None")"
            log_error ""
            log_error "If this is a fresh start, ensure you're running on Ubuntu."
            log_error "If migration was interrupted, check checkpoint file: $CHECKPOINT_FILE"
            exit 1
            ;;
    esac

    log ""
    log "${GREEN}Master migration script completed${NC}"
    log "Full log: $LOG_FILE"
}

# Trap for cleanup
trap 'log_error "Script interrupted"; exit 130' INT TERM

# Execute
main
