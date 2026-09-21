#!/bin/bash
# 7-verify-migration.sh - Comprehensive migration verification
# Verifies all aspects of the Ubuntu → CachyOS migration
#
# Run after: 6-restore-configs.sh

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
LOG_FILE="$LOG_DIR/verify-migration-$DATE.log"
REPORT_FILE="$LOG_DIR/migration-report-$DATE.txt"

mkdir -p "$LOG_DIR"

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========${NC}\n" | tee -a "$LOG_FILE"; }

# Test tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

test_result() {
    local status="$1"
    local test_name="$2"
    local details="$3"

    ((TOTAL_TESTS++))

    case "$status" in
        "pass")
            ((PASSED_TESTS++))
            echo "  ✅ PASS: $test_name" | tee -a "$LOG_FILE"
            ;;
        "fail")
            ((FAILED_TESTS++))
            echo "  ❌ FAIL: $test_name" | tee -a "$LOG_FILE"
            ;;
        "warn")
            ((WARNING_TESTS++))
            echo "  ⚠️  WARN: $test_name" | tee -a "$LOG_FILE"
            ;;
    esac

    if [[ -n "$details" ]]; then
        echo "         $details" | tee -a "$LOG_FILE"
    fi
}

# ===================================
# PARTITION VERIFICATION
# ===================================

verify_partitions() {
    log_section "Partition Verification"

    log "Checking partition layout..."

    # Check EFI partition
    if mountpoint -q /boot/efi; then
        local efi_size=$(df -h /boot/efi | tail -1 | awk '{print $2}')
        test_result "pass" "EFI partition mounted" "Size: $efi_size"
    else
        test_result "fail" "EFI partition not mounted" "Expected at /boot/efi"
    fi

    # Check root partition
    local root_fs=$(df -T / | tail -1 | awk '{print $2}')
    local root_size=$(df -h / | tail -1 | awk '{print $2}')

    if [[ "$root_fs" == "ext4" ]] || [[ "$root_fs" == "btrfs" ]]; then
        test_result "pass" "Root filesystem: $root_fs" "Size: $root_size"
    else
        test_result "warn" "Root filesystem: $root_fs" "Expected ext4 or btrfs, got $root_fs"
    fi

    # Check home partition
    if mountpoint -q /home; then
        local home_fs=$(df -T /home | tail -1 | awk '{print $2}')
        local home_size=$(df -h /home | tail -1 | awk '{print $2}')
        test_result "pass" "/home mounted ($home_fs)" "Size: $home_size"
    else
        test_result "warn" "/home not separate partition" "Using root partition"
    fi

    # Check workspace partition
    if mountpoint -q /workspace; then
        local ws_fs=$(df -T /workspace | tail -1 | awk '{print $2}')
        local ws_size=$(df -h /workspace | tail -1 | awk '{print $2}')

        if [[ "$ws_fs" == "xfs" ]]; then
            test_result "pass" "/workspace mounted (XFS)" "Size: $ws_size"
        else
            test_result "warn" "/workspace filesystem: $ws_fs" "Expected XFS for performance"
        fi
    else
        test_result "fail" "/workspace not mounted" "Required for AI agent workloads"
    fi

    # Check swap
    if swapon --show | grep -q "/dev/"; then
        local swap_size=$(swapon --show --noheadings | awk '{print $3}')
        test_result "pass" "Swap active" "Size: $swap_size"
    else
        test_result "warn" "No swap partition" "Consider adding for stability"
    fi
}

# ===================================
# FILESYSTEM PERFORMANCE
# ===================================

verify_filesystem_performance() {
    log_section "Filesystem Performance Verification"

    log "Checking mount options..."

    # Check for noatime
    local noatime_count=$(mount | grep -c "noatime" || echo "0")
    if [[ $noatime_count -ge 2 ]]; then
        test_result "pass" "noatime mount option" "Found on $noatime_count filesystems"
    else
        test_result "warn" "noatime not widely used" "Performance may be suboptimal"
    fi

    # Check XFS workspace optimizations
    if mountpoint -q /workspace; then
        local ws_opts=$(mount | grep "/workspace" | grep -oP 'type \w+ \(\K[^)]+')

        if echo "$ws_opts" | grep -q "largeio"; then
            test_result "pass" "XFS largeio enabled" "Optimized for large files"
        else
            test_result "warn" "XFS largeio not enabled" "Consider remounting with largeio"
        fi

        if echo "$ws_opts" | grep -q "logbufs"; then
            test_result "pass" "XFS log buffers optimized" "Better write performance"
        else
            test_result "warn" "XFS log buffers not tuned" "Consider adding logbufs=8"
        fi
    fi

    # I/O Scheduler check
    log ""
    log "Checking I/O schedulers..."

    for dev in /sys/block/nvme*; do
        if [[ -d "$dev" ]]; then
            local device=$(basename "$dev")
            local scheduler=$(cat "$dev/queue/scheduler" | grep -oP '\[\K[^\]]+')

            if [[ "$scheduler" == "none" ]]; then
                test_result "pass" "NVMe I/O scheduler: $device" "Using 'none' (optimal)"
            else
                test_result "warn" "NVMe I/O scheduler: $device" "Using '$scheduler', expected 'none'"
            fi
        fi
    done

    for dev in /sys/block/sd*; do
        if [[ -d "$dev" ]]; then
            local device=$(basename "$dev")
            local rotational=$(cat "$dev/queue/rotational" 2>/dev/null || echo "1")
            local scheduler=$(cat "$dev/queue/scheduler" | grep -oP '\[\K[^\]]+')

            if [[ "$rotational" == "0" ]]; then
                # SSD
                if [[ "$scheduler" == "none" ]] || [[ "$scheduler" == "mq-deadline" ]]; then
                    test_result "pass" "SSD I/O scheduler: $device" "Using '$scheduler'"
                else
                    test_result "warn" "SSD I/O scheduler: $device" "Using '$scheduler', expected 'none' or 'mq-deadline'"
                fi
            fi
        fi
    done
}

# ===================================
# SYSTEM LIMITS
# ===================================

verify_system_limits() {
    log_section "System Limits Verification"

    log "Checking file descriptor limits..."

    # Current shell limits
    local nofile_soft=$(ulimit -Sn)
    local nofile_hard=$(ulimit -Hn)

    if [[ $nofile_soft -ge 1048576 ]]; then
        test_result "pass" "Soft file descriptor limit" "$nofile_soft (target: 1048576)"
    else
        test_result "fail" "Soft file descriptor limit too low" "$nofile_soft (target: 1048576)"
    fi

    if [[ $nofile_hard -ge 1048576 ]]; then
        test_result "pass" "Hard file descriptor limit" "$nofile_hard (target: 1048576)"
    else
        test_result "fail" "Hard file descriptor limit too low" "$nofile_hard (target: 1048576)"
    fi

    # Process limits
    local nproc_soft=$(ulimit -Su)
    if [[ "$nproc_soft" == "unlimited" ]] || [[ $nproc_soft -ge 4194304 ]]; then
        test_result "pass" "Process limit" "$nproc_soft"
    else
        test_result "warn" "Process limit may be low" "$nproc_soft"
    fi

    # Kernel parameters
    log ""
    log "Checking kernel parameters..."

    local fs_file_max=$(sysctl -n fs.file-max)
    if [[ $fs_file_max -ge 2097152 ]]; then
        test_result "pass" "fs.file-max" "$fs_file_max (target: 2097152)"
    else
        test_result "fail" "fs.file-max too low" "$fs_file_max (target: 2097152)"
    fi

    local swappiness=$(sysctl -n vm.swappiness)
    if [[ $swappiness -le 10 ]]; then
        test_result "pass" "vm.swappiness" "$swappiness (target: ≤10)"
    else
        test_result "warn" "vm.swappiness high" "$swappiness (target: ≤10 for performance)"
    fi

    local somaxconn=$(sysctl -n net.core.somaxconn)
    if [[ $somaxconn -ge 65535 ]]; then
        test_result "pass" "net.core.somaxconn" "$somaxconn (target: 65535)"
    else
        test_result "warn" "net.core.somaxconn low" "$somaxconn (target: 65535)"
    fi
}

# ===================================
# PACKAGE INSTALLATION
# ===================================

verify_packages() {
    log_section "Package Installation Verification"

    log "Checking package managers..."

    # Pacman
    if command -v pacman &> /dev/null; then
        local pkg_count=$(pacman -Q | wc -l)
        test_result "pass" "Pacman package manager" "$pkg_count packages installed"
    else
        test_result "fail" "Pacman not found" "Critical failure"
    fi

    # AUR helper (paru/yay)
    if command -v paru &> /dev/null; then
        test_result "pass" "AUR helper (paru)" "$(paru --version | head -1)"
    elif command -v yay &> /dev/null; then
        test_result "pass" "AUR helper (yay)" "$(yay --version | head -1)"
    else
        test_result "warn" "No AUR helper found" "Install paru or yay for AUR access"
    fi

    # Language package managers
    local lang_managers=(
        "npm:Node.js package manager"
        "pip:Python package manager"
        "cargo:Rust package manager"
        "gem:Ruby package manager"
    )

    log ""
    log "Checking language package managers..."

    for manager in "${lang_managers[@]}"; do
        local cmd="${manager%%:*}"
        local desc="${manager##*:}"

        if command -v "$cmd" &> /dev/null; then
            test_result "pass" "$desc" "Installed"
        else
            test_result "warn" "$desc not found" "Install if needed for development"
        fi
    done

    # Flatpak
    if command -v flatpak &> /dev/null; then
        local flatpak_count=$(flatpak list --app 2>/dev/null | wc -l || echo "0")
        test_result "pass" "Flatpak" "$flatpak_count apps installed"
    else
        test_result "warn" "Flatpak not installed" "Install for universal apps"
    fi
}

# ===================================
# CONFIGURATION FILES
# ===================================

verify_configurations() {
    log_section "Configuration Verification"

    log "Checking user configurations..."

    # Shell config
    if [[ -f "$HOME/.bashrc" ]] || [[ -f "$HOME/.zshrc" ]]; then
        test_result "pass" "Shell configuration" "Found"
    else
        test_result "warn" "No shell configuration" ".bashrc or .zshrc not found"
    fi

    # Git config
    if [[ -f "$HOME/.gitconfig" ]]; then
        local git_user=$(git config --global user.name 2>/dev/null || echo "")
        if [[ -n "$git_user" ]]; then
            test_result "pass" "Git configuration" "User: $git_user"
        else
            test_result "warn" "Git user not configured" "Run: git config --global user.name"
        fi
    else
        test_result "warn" "Git configuration missing" ".gitconfig not found"
    fi

    # SSH config
    if [[ -f "$HOME/.ssh/config" ]]; then
        test_result "pass" "SSH configuration" "Found"
    else
        test_result "warn" "SSH configuration missing" ".ssh/config not found (may be optional)"
    fi

    # SSH keys
    local key_count=$(find "$HOME/.ssh" -type f -name "id_*" ! -name "*.pub" 2>/dev/null | wc -l || echo "0")
    if [[ $key_count -gt 0 ]]; then
        test_result "pass" "SSH private keys" "$key_count key(s) found"

        # Check permissions
        local bad_perms=$(find "$HOME/.ssh" -type f -name "id_*" ! -name "*.pub" ! -perm 600 2>/dev/null | wc -l || echo "0")
        if [[ $bad_perms -gt 0 ]]; then
            test_result "fail" "SSH key permissions" "$bad_perms key(s) with incorrect permissions (should be 600)"
        else
            test_result "pass" "SSH key permissions" "Correct (600)"
        fi
    else
        test_result "warn" "No SSH keys found" "Create or restore from backup"
    fi
}

# ===================================
# SYSTEM PERFORMANCE
# ===================================

verify_performance() {
    log_section "System Performance Check"

    # CPU Governor
    if [[ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
        local governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
        if [[ "$governor" == "performance" ]]; then
            test_result "pass" "CPU governor" "performance"
        else
            test_result "warn" "CPU governor" "$governor (expected 'performance')"
        fi
    else
        test_result "warn" "CPU governor not available" "May not support frequency scaling"
    fi

    # Memory
    local total_mem=$(free -h | awk '/^Mem:/ {print $2}')
    local available_mem=$(free -h | awk '/^Mem:/ {print $7}')
    test_result "pass" "System memory" "Total: $total_mem, Available: $available_mem"

    # Disk space
    log ""
    log "Checking disk space..."

    df -h | grep -E "^/dev/" | while read line; do
        local usage=$(echo "$line" | awk '{print $5}' | tr -d '%')
        local mount=$(echo "$line" | awk '{print $6}')
        local size=$(echo "$line" | awk '{print $2}')

        if [[ $usage -lt 80 ]]; then
            test_result "pass" "Disk space: $mount" "$size total, ${usage}% used"
        elif [[ $usage -lt 90 ]]; then
            test_result "warn" "Disk space: $mount" "$size total, ${usage}% used (getting full)"
        else
            test_result "fail" "Disk space: $mount" "$size total, ${usage}% used (critically low)"
        fi
    done
}

# ===================================
# BOOTLOADER
# ===================================

verify_bootloader() {
    log_section "Bootloader Verification"

    if [[ -d /boot/efi/loader ]]; then
        test_result "pass" "systemd-boot installed" "Found at /boot/efi/loader"

        # Check boot entries
        local entries=$(bootctl list 2>/dev/null | grep -c "title:" || echo "0")
        if [[ $entries -ge 2 ]]; then
            test_result "pass" "Boot entries" "$entries entries (dual-boot detected)"
        elif [[ $entries -eq 1 ]]; then
            test_result "warn" "Boot entries" "Only 1 entry found (expected 2 for dual-boot)"
        else
            test_result "fail" "Boot entries" "No entries found"
        fi
    elif [[ -d /boot/grub ]]; then
        test_result "pass" "GRUB installed" "Found at /boot/grub"

        # Check for both OS entries
        if grep -q "Ubuntu\|ubuntu" /boot/grub/grub.cfg && grep -q "CachyOS\|cachyos" /boot/grub/grub.cfg; then
            test_result "pass" "Dual-boot configuration" "Both Ubuntu and CachyOS found"
        else
            test_result "warn" "Dual-boot configuration" "Check /boot/grub/grub.cfg"
        fi
    else
        test_result "fail" "Bootloader not detected" "Neither systemd-boot nor GRUB found"
    fi
}

# ===================================
# WORKSPACE ACCESS TEST
# ===================================

verify_workspace_access() {
    log_section "Workspace Access Verification"

    if [[ ! -d /workspace ]]; then
        test_result "fail" "Workspace directory missing" "/workspace does not exist"
        return
    fi

    # Write test
    local test_file="/workspace/.migration-test-$$"
    if touch "$test_file" 2>/dev/null; then
        test_result "pass" "Workspace write access" "Can create files"
        rm -f "$test_file"
    else
        test_result "fail" "Workspace write access" "Cannot create files (check permissions)"
    fi

    # Large file test (simulate AI agent workload)
    log ""
    log "Testing workspace I/O performance..."

    local test_data="/workspace/.perf-test-$$"
    local dd_result=$(dd if=/dev/zero of="$test_data" bs=1M count=100 oflag=direct 2>&1 || echo "FAILED")

    if echo "$dd_result" | grep -q "copied"; then
        local speed=$(echo "$dd_result" | grep -oP '\d+\.?\d* [MG]B/s')
        test_result "pass" "Workspace write performance" "$speed"
        rm -f "$test_data"
    else
        test_result "fail" "Workspace write performance test failed" ""
    fi
}

# ===================================
# GENERATE REPORT
# ===================================

generate_report() {
    log_section "Generating Migration Report"

    cat > "$REPORT_FILE" << EOF
═══════════════════════════════════════════════════════════════
    MIGRATION VERIFICATION REPORT
═══════════════════════════════════════════════════════════════

Generated: $(date)
System: $(uname -a)
Hostname: $(hostname)

═══════════════════════════════════════════════════════════════
    TEST SUMMARY
═══════════════════════════════════════════════════════════════

Total Tests: $TOTAL_TESTS
✅ Passed:   $PASSED_TESTS
❌ Failed:   $FAILED_TESTS
⚠️  Warnings: $WARNING_TESTS

Success Rate: $(echo "scale=1; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc)%

═══════════════════════════════════════════════════════════════
    OVERALL STATUS
═══════════════════════════════════════════════════════════════

EOF

    if [[ $FAILED_TESTS -eq 0 ]] && [[ $WARNING_TESTS -eq 0 ]]; then
        cat >> "$REPORT_FILE" << EOF
✅ EXCELLENT: Migration completed successfully with no issues!

Your system is fully optimized and ready for AI agent workloads.

EOF
    elif [[ $FAILED_TESTS -eq 0 ]]; then
        cat >> "$REPORT_FILE" << EOF
✅ GOOD: Migration completed successfully with minor warnings.

Review warnings and address as needed. System is functional.

EOF
    elif [[ $FAILED_TESTS -le 2 ]]; then
        cat >> "$REPORT_FILE" << EOF
⚠️  ATTENTION NEEDED: Migration mostly successful, but critical issues found.

Address failed tests before putting system into production use.

EOF
    else
        cat >> "$REPORT_FILE" << EOF
❌ CRITICAL: Multiple failures detected during verification.

Review and resolve all failed tests before using the system.
Consider re-running migration scripts or manual intervention.

EOF
    fi

    cat >> "$REPORT_FILE" << EOF
═══════════════════════════════════════════════════════════════
    DETAILED LOG
═══════════════════════════════════════════════════════════════

See full details in: $LOG_FILE

═══════════════════════════════════════════════════════════════
    NEXT STEPS
═══════════════════════════════════════════════════════════════

1. Review this report and the detailed log
2. Address any failed tests (❌)
3. Consider addressing warnings (⚠️) for optimal performance
4. Test your critical applications and workflows
5. Set up regular backups using the backup script (1-backup-system.sh)
6. Enjoy your optimized dual-boot setup!

For support and troubleshooting, refer to:
  - Migration research: repos/migrate/research/
  - Script logs: $LOG_DIR/
  - System documentation: /workspace/docs/ (if applicable)

═══════════════════════════════════════════════════════════════
EOF

    cat "$REPORT_FILE"
}

# ===================================
# MAIN EXECUTION
# ===================================

main() {
    log "Starting migration verification..."
    log "Log file: $LOG_FILE"

    verify_partitions
    verify_filesystem_performance
    verify_system_limits
    verify_packages
    verify_configurations
    verify_performance
    verify_bootloader
    verify_workspace_access

    generate_report

    log ""
    log "${GREEN}✅ Verification completed!${NC}"
    log "📊 Report: $REPORT_FILE"
    log "📝 Detailed log: $LOG_FILE"
    log ""

    if [[ $FAILED_TESTS -eq 0 ]]; then
        log "${GREEN}🎉 Migration successful! All critical tests passed.${NC}"
    else
        log "${RED}⚠️  $FAILED_TESTS test(s) failed. Review report for details.${NC}"
    fi
}

main
