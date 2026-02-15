#!/usr/bin/env bash
# 00b-prepare-nvme-installer.sh - Replace Arch ISO with CachyOS on NVMe installer partition
#
# The NVMe (nvme0n1) has an 8GB ext4 partition (p2, label "arch") that currently
# holds an Arch Linux ISO for loopbooting via GRUB. This script:
#   1. Downloads the CachyOS ISO (or uses a local copy)
#   2. Replaces the Arch ISO on nvme0n1p2 with the CachyOS ISO
#   3. Updates the GRUB 40_custom loopboot entry
#   4. Regenerates grub.cfg
#
# After running this, reboot and select "CachyOS Installer" from GRUB to
# install CachyOS onto the rest of the NVMe (partitions p1-p4 per MIGRATION-PLAN.md).
#
# Run ON UBUNTU before migration.

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/prepare-installer-$DATE.log"
mkdir -p "$LOG_DIR"

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }
error_exit() { log_error "$1"; exit 1; }

# Configuration
INSTALLER_PART="/dev/nvme0n1p2"
INSTALLER_UUID="0e306403-6b7c-4edc-a95c-2cd43e5532b1"
INSTALLER_LABEL="arch"
CACHYOS_DOWNLOAD_URL="https://mirror.cachyos.org/ISO/latest/cachyos-desktop-linux-250209.iso"
CACHYOS_ISO_NAME="cachyos-desktop-linux.iso"
MOUNT_POINT=""

cleanup() {
    if [[ -n "${MOUNT_POINT:-}" ]] && mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        log "Cleaning up: unmounting $MOUNT_POINT"
        sudo umount "$MOUNT_POINT" 2>/dev/null || true
    fi
    if [[ -n "${MOUNT_POINT:-}" ]] && [[ -d "$MOUNT_POINT" ]]; then
        rmdir "$MOUNT_POINT" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# -------------------------------------------------------
# Preflight checks
# -------------------------------------------------------
log_section "Preflight Checks"

[[ $EUID -eq 0 ]] && error_exit "Do not run as root. Script uses sudo where needed."

# Verify the installer partition exists
if ! lsblk "$INSTALLER_PART" &>/dev/null; then
    error_exit "Installer partition $INSTALLER_PART not found"
fi

# Verify UUID matches expected
ACTUAL_UUID=$(lsblk -no UUID "$INSTALLER_PART" 2>/dev/null)
if [[ "$ACTUAL_UUID" != "$INSTALLER_UUID" ]]; then
    log_warn "UUID mismatch: expected $INSTALLER_UUID, got $ACTUAL_UUID"
    log_warn "Proceeding with detected UUID: $ACTUAL_UUID"
    INSTALLER_UUID="$ACTUAL_UUID"
fi

PART_SIZE=$(lsblk -bno SIZE "$INSTALLER_PART" 2>/dev/null)
PART_SIZE_GB=$(( PART_SIZE / 1073741824 ))
log "Installer partition: $INSTALLER_PART ($PART_SIZE_GB GB, UUID: $INSTALLER_UUID)"

# -------------------------------------------------------
# Get CachyOS ISO
# -------------------------------------------------------
log_section "CachyOS ISO"

ISO_PATH=""

# Check if user provided a local ISO as argument
if [[ ${1:-} == *.iso ]] && [[ -f "$1" ]]; then
    ISO_PATH="$1"
    log "Using local ISO: $ISO_PATH"
elif [[ ${1:-} == *.iso ]]; then
    error_exit "ISO file not found: $1"
fi

if [[ -z "$ISO_PATH" ]]; then
    # Check common download locations
    for candidate in \
        "$HOME/Downloads/cachyos"*.iso \
        "$HOME/Downloads/CachyOS"*.iso \
        "/tmp/cachyos"*.iso; do
        if [[ -f "$candidate" ]]; then
            ISO_PATH="$candidate"
            log "Found local ISO: $ISO_PATH"
            break
        fi
    done
fi

if [[ -z "$ISO_PATH" ]]; then
    log "No local CachyOS ISO found."
    log ""
    log "Please download the CachyOS Desktop ISO from:"
    log "  https://cachyos.org/download/"
    log ""
    log "Then re-run this script with the ISO path:"
    log "  $0 /path/to/cachyos-desktop-linux-XXXXXX.iso"
    log ""
    read -rp "Or press Enter to download now (~2.5GB), Ctrl+C to abort: "

    ISO_PATH="/tmp/$CACHYOS_ISO_NAME"
    log "Downloading CachyOS ISO to $ISO_PATH ..."
    log_warn "URL may be outdated. Check https://cachyos.org/download/ for latest."

    if command -v curl &>/dev/null; then
        curl -L -o "$ISO_PATH" "$CACHYOS_DOWNLOAD_URL" 2>&1 | tee -a "$LOG_FILE"
    elif command -v wget &>/dev/null; then
        wget -O "$ISO_PATH" "$CACHYOS_DOWNLOAD_URL" 2>&1 | tee -a "$LOG_FILE"
    else
        error_exit "Neither curl nor wget available for download"
    fi
fi

# Verify ISO exists and is reasonable size (>1GB)
[[ -f "$ISO_PATH" ]] || error_exit "ISO file not found: $ISO_PATH"
ISO_SIZE=$(stat -c%s "$ISO_PATH" 2>/dev/null)
ISO_SIZE_MB=$(( ISO_SIZE / 1048576 ))
if [[ $ISO_SIZE -lt 1073741824 ]]; then
    error_exit "ISO seems too small ($ISO_SIZE_MB MB). Expected >1GB for CachyOS Desktop."
fi
log "ISO size: ${ISO_SIZE_MB} MB"

# Verify partition has enough space
if [[ $ISO_SIZE -gt $PART_SIZE ]]; then
    error_exit "ISO ($ISO_SIZE_MB MB) is larger than partition ($PART_SIZE_GB GB)"
fi

# -------------------------------------------------------
# Confirmation
# -------------------------------------------------------
log_section "Confirmation"

log "This will:"
log "  1. Mount $INSTALLER_PART"
log "  2. Remove the old Arch ISO from it"
log "  3. Copy CachyOS ISO ($ISO_SIZE_MB MB) onto it"
log "  4. Update GRUB entry in /etc/grub.d/40_custom"
log "  5. Regenerate grub.cfg"
log ""
log "The installer partition contents will be replaced."
log "No other partitions or drives will be touched."
echo ""
read -rp "Proceed? (y/N): " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { log "Aborted by user."; exit 0; }

# -------------------------------------------------------
# Mount and replace ISO
# -------------------------------------------------------
log_section "Replacing ISO"

MOUNT_POINT=$(mktemp -d /tmp/installer-part.XXXX)

# Unmount if already mounted
if mount | grep -q "$INSTALLER_PART"; then
    EXISTING_MOUNT=$(mount | grep "$INSTALLER_PART" | awk '{print $3}')
    log "Partition already mounted at $EXISTING_MOUNT, unmounting..."
    sudo umount "$INSTALLER_PART" || error_exit "Failed to unmount $INSTALLER_PART"
fi

log "Mounting $INSTALLER_PART at $MOUNT_POINT"
sudo mount "$INSTALLER_PART" "$MOUNT_POINT" || error_exit "Failed to mount $INSTALLER_PART"

# Remove old ISO(s)
OLD_ISOS=$(find "$MOUNT_POINT" -maxdepth 1 -name "*.iso" 2>/dev/null)
if [[ -n "$OLD_ISOS" ]]; then
    log "Removing old ISO(s):"
    echo "$OLD_ISOS" | while read -r f; do
        log "  $(basename "$f") ($(du -h "$f" | cut -f1))"
    done
    sudo rm -f "$MOUNT_POINT"/*.iso
else
    log "No existing ISO files found on partition"
fi

# Copy CachyOS ISO
log "Copying CachyOS ISO to partition..."
if command -v pv &>/dev/null; then
    pv "$ISO_PATH" | sudo tee "$MOUNT_POINT/$CACHYOS_ISO_NAME" >/dev/null
else
    sudo cp -v "$ISO_PATH" "$MOUNT_POINT/$CACHYOS_ISO_NAME" 2>&1 | tee -a "$LOG_FILE"
fi

# Verify copy
COPIED_SIZE=$(stat -c%s "$MOUNT_POINT/$CACHYOS_ISO_NAME" 2>/dev/null)
if [[ "$COPIED_SIZE" != "$ISO_SIZE" ]]; then
    error_exit "Size mismatch after copy: expected $ISO_SIZE, got $COPIED_SIZE"
fi
log "ISO copied and verified ($ISO_SIZE_MB MB)"

# Show partition usage
df -h "$MOUNT_POINT" | tee -a "$LOG_FILE"

sudo umount "$MOUNT_POINT"
MOUNT_POINT=""
log "Partition unmounted"

# -------------------------------------------------------
# Update GRUB entry
# -------------------------------------------------------
log_section "Updating GRUB"

GRUB_CUSTOM="/etc/grub.d/40_custom"

# Back up current entry
if [[ -f "$GRUB_CUSTOM" ]]; then
    sudo cp "$GRUB_CUSTOM" "$GRUB_CUSTOM.pre-cachyos-$DATE"
    log "Backed up $GRUB_CUSTOM"
fi

# Write new entry
# CachyOS uses a different boot structure than Arch:
#   - Kernel: boot/vmlinuz-linux
#   - Initrd: boot/initramfs-linux.img
#   - Boot params: copytoram loads entire ISO into RAM (installer runs from RAM,
#     safe to repartition the source drive during install)
sudo tee "$GRUB_CUSTOM" > /dev/null << GRUBEOF
#!/bin/sh
exec tail -n +3 \$0
# This file provides an easy way to add custom menu entries.  Simply type the
# menu entries you want to add after this comment.  Be careful not to change
# the 'exec tail' line above.
#
menuentry "CachyOS Installer (loopboot from NVMe)" {
    insmod part_gpt
    insmod ext2
    insmod loopback
    insmod iso9660
    search --no-floppy --fs-uuid --set=root $INSTALLER_UUID

    set iso_path="/$CACHYOS_ISO_NAME"
    loopback loop (\${root})\${iso_path}

    linux   (loop)/boot/vmlinuz-linux \\
            img_dev=/dev/disk/by-uuid/$INSTALLER_UUID \\
            img_loop=\${iso_path} \\
            copytoram=y \\
            cow_spacesize=4G \\
            driver=free
    initrd  (loop)/boot/initramfs-linux.img
}
GRUBEOF

log "GRUB entry written to $GRUB_CUSTOM"

# Regenerate grub.cfg
log "Regenerating grub.cfg..."
sudo update-grub 2>&1 | tee -a "$LOG_FILE" || sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | tee -a "$LOG_FILE"
log "GRUB configuration updated"

# -------------------------------------------------------
# Summary
# -------------------------------------------------------
log_section "Summary"

log "CachyOS installer is ready on $INSTALLER_PART"
log ""
log "ISO:        $CACHYOS_ISO_NAME ($ISO_SIZE_MB MB)"
log "Partition:  $INSTALLER_PART (UUID: $INSTALLER_UUID)"
log "GRUB entry: 'CachyOS Installer (loopboot from NVMe)'"
log "Log:        $LOG_FILE"
log ""
log "Next steps:"
log "  1. Run: ./migration/00a-backup-nvme-windows.sh   (back up nvme0n1p1 Windows data)"
log "  2. Commit dotfiles: git add -A && git commit && git push"
log "  3. Reboot and select 'CachyOS Installer (loopboot from NVMe)' from GRUB"
log "  4. In Calamares installer: manual partition nvme0n1"
log "     - Delete p1 (458GB NTFS)"
log "     - Keep p2 (8GB installer at END of disk -- do not touch)"
log "     - Create in freed space: p1 1GB FAT32 /boot/efi"
log "     -                        p3 100GB XFS /"
log "     -                        p4 32GB swap"
log "     -                        p5 ~318GB XFS /workspace"
log "     Physical order: [EFI][Root][Swap][Workspace][Installer(p2)]"
log "  5. After CachyOS is stable, delete p2 and extend /workspace rightward (+8GB)"
log ""
log_warn "IMPORTANT: During CachyOS install, use MANUAL partitioning."
log_warn "Do NOT select 'Erase disk' -- it will destroy the installer partition."
log_warn "The installer runs from RAM (copytoram=y), so p2 is safe during install,"
log_warn "but Calamares 'erase disk' would still wipe all partitions."
