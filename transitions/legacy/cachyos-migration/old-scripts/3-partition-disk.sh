#!/bin/bash
# 3-partition-disk.sh - Interactive disk partitioning for dual-boot setup
# Based on: repos/migrate/research/partition-design.md
#
# WARNING: This script will DESTROY ALL DATA on selected disks
# Run ONLY after backing up all important data
#
# Partition Scheme:
# NVMe (500GB): EFI (1GB) + Ubuntu / (80GB) + CachyOS / (80GB) + Swap (32GB) + Cache (307GB)
# SATA SSD (4TB): Ubuntu /home (200GB) + CachyOS /home (200GB) + /workspace (3.6TB)

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LOG_DIR="$(dirname "$(readlink -f "$0")")/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/partition-disk-$DATE.log"

mkdir -p "$LOG_DIR"

# Logging functions
log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========================================${NC}" | tee -a "$LOG_FILE"; echo -e "${BLUE}$*${NC}" | tee -a "$LOG_FILE"; echo -e "${BLUE}========================================${NC}\n" | tee -a "$LOG_FILE"; }

# Error handling
error_exit() {
    log_error "$1"
    log_error "Partitioning failed! Check $LOG_FILE for details"
    exit 1
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   error_exit "This script must be run as root (use sudo)"
fi

# Safety check - must run interactively
if [[ ! -t 0 ]]; then
    error_exit "This script must be run interactively (not in a pipe or automated)"
fi

# ===================================
# DISK DETECTION AND SELECTION
# ===================================

detect_disks() {
    log_section "DISK DETECTION"

    log "Detecting available disks..."

    # List all disks (excluding loop devices, dm, etc)
    lsblk -d -n -o NAME,SIZE,TYPE,MODEL | grep -E "disk$" | tee -a "$LOG_FILE"

    echo ""
}

select_disk() {
    local disk_type="$1"  # "NVMe" or "SATA SSD"
    local expected_size="$2"

    echo -e "${YELLOW}Select disk for $disk_type (expected: $expected_size):${NC}"
    read -p "Enter disk name (e.g., nvme0n1, sda): " disk_name

    # Validate disk exists
    if [[ ! -b "/dev/$disk_name" ]]; then
        error_exit "Disk /dev/$disk_name does not exist"
    fi

    # Show disk details
    echo ""
    log "Selected disk: /dev/$disk_name"
    lsblk "/dev/$disk_name" | tee -a "$LOG_FILE"
    fdisk -l "/dev/$disk_name" | tee -a "$LOG_FILE"

    # Confirmation
    echo ""
    echo -e "${RED}⚠️  WARNING: ALL DATA ON /dev/$disk_name WILL BE DESTROYED!${NC}"
    echo -e "${RED}⚠️  This action CANNOT be undone!${NC}"
    read -p "Type 'YES' (all caps) to confirm: " confirmation

    if [[ "$confirmation" != "YES" ]]; then
        error_exit "Operation cancelled by user"
    fi

    echo "$disk_name"
}

# ===================================
# PARTITION CREATION - NVMe
# ===================================

partition_nvme() {
    local disk="$1"

    log_section "PARTITIONING NVMe DISK: /dev/$disk"

    log "Wiping existing partition table..."
    wipefs -a "/dev/$disk" || log_warn "Wipefs failed (may be clean already)"

    log "Creating new GPT partition table..."
    parted -s "/dev/$disk" mklabel gpt || error_exit "Failed to create GPT table"

    log "Creating partitions:"

    # Partition 1: EFI (1GB)
    log "  1. EFI System Partition (1GB)"
    parted -s "/dev/$disk" mkpart EFI fat32 1MiB 1025MiB
    parted -s "/dev/$disk" set 1 esp on

    # Partition 2: Ubuntu / (80GB)
    log "  2. Ubuntu Root (80GB)"
    parted -s "/dev/$disk" mkpart ubuntu-root ext4 1025MiB 82945MiB

    # Partition 3: CachyOS / (80GB)
    log "  3. CachyOS Root (80GB)"
    parted -s "/dev/$disk" mkpart cachyos-root btrfs 82945MiB 164865MiB

    # Partition 4: Swap (32GB)
    log "  4. Swap (32GB)"
    parted -s "/dev/$disk" mkpart swap linux-swap 164865MiB 197633MiB

    # Partition 5: Cache (rest of disk ~307GB)
    log "  5. Cache partition (remaining space)"
    parted -s "/dev/$disk" mkpart cache xfs 197633MiB 100%

    # Verify
    log "Partition table created successfully:"
    parted "/dev/$disk" print | tee -a "$LOG_FILE"

    echo "$disk"
}

# ===================================
# PARTITION CREATION - SATA SSD
# ===================================

partition_sata() {
    local disk="$1"

    log_section "PARTITIONING SATA SSD: /dev/$disk"

    log "Wiping existing partition table..."
    wipefs -a "/dev/$disk" || log_warn "Wipefs failed (may be clean already)"

    log "Creating new GPT partition table..."
    parted -s "/dev/$disk" mklabel gpt || error_exit "Failed to create GPT table"

    log "Creating partitions:"

    # Partition 1: Ubuntu /home (200GB)
    log "  1. Ubuntu /home (200GB)"
    parted -s "/dev/$disk" mkpart ubuntu-home ext4 1MiB 204801MiB

    # Partition 2: CachyOS /home (200GB)
    log "  2. CachyOS /home (200GB)"
    parted -s "/dev/$disk" mkpart cachyos-home ext4 204801MiB 409601MiB

    # Partition 3: /workspace (rest of disk ~3.6TB)
    log "  3. Workspace (remaining space)"
    parted -s "/dev/$disk" mkpart workspace xfs 409601MiB 100%

    # Verify
    log "Partition table created successfully:"
    parted "/dev/$disk" print | tee -a "$LOG_FILE"

    echo "$disk"
}

# ===================================
# FILESYSTEM FORMATTING
# ===================================

format_nvme() {
    local disk="$1"

    log_section "FORMATTING NVMe PARTITIONS"

    # Determine partition naming (nvme uses p1, p2; others use 1, 2)
    local p=""
    [[ "$disk" =~ nvme ]] && p="p"

    log "Formatting EFI partition..."
    mkfs.fat -F32 -n EFI "/dev/${disk}${p}1" || error_exit "Failed to format EFI"

    log "Formatting Ubuntu root (ext4 with optimal settings)..."
    mkfs.ext4 -L ubuntu-root -m 1 -O ^has_journal "/dev/${disk}${p}2" || error_exit "Failed to format Ubuntu root"
    tune2fs -o journal_data_writeback "/dev/${disk}${p}2"

    log "Formatting CachyOS root (btrfs with optimal settings)..."
    mkfs.btrfs -f -L cachyos-root "/dev/${disk}${p}3" || error_exit "Failed to format CachyOS root"

    log "Setting up swap..."
    mkswap -L swap "/dev/${disk}${p}4" || error_exit "Failed to create swap"

    log "Formatting cache partition (XFS with optimal settings)..."
    mkfs.xfs -f -L cache -d agcount=64 "/dev/${disk}${p}5" || error_exit "Failed to format cache"

    log "NVMe formatting complete"
}

format_sata() {
    local disk="$1"

    log_section "FORMATTING SATA SSD PARTITIONS"

    log "Formatting Ubuntu /home (ext4)..."
    mkfs.ext4 -L ubuntu-home -m 1 "/dev/${disk}1" || error_exit "Failed to format Ubuntu home"

    log "Formatting CachyOS /home (ext4)..."
    mkfs.ext4 -L cachyos-home -m 1 "/dev/${disk}2" || error_exit "Failed to format CachyOS home"

    log "Formatting /workspace (XFS with aggressive optimization)..."
    # Optimized for 1000+ concurrent agents with parallel I/O
    mkfs.xfs -f -L workspace \
        -d agcount=64,su=256k,sw=4 \
        -l size=128m,su=256k \
        -i size=512,maxpct=1 \
        "/dev/${disk}3" || error_exit "Failed to format workspace"

    log "SATA SSD formatting complete"
}

# ===================================
# FSTAB GENERATION
# ===================================

generate_fstab() {
    local nvme_disk="$1"
    local sata_disk="$2"
    local fstab_file="$LOG_DIR/fstab-entries-$DATE.txt"

    log_section "GENERATING FSTAB ENTRIES"

    # Determine partition naming
    local nvme_p=""
    [[ "$nvme_disk" =~ nvme ]] && nvme_p="p"

    log "Getting UUIDs..."

    cat > "$fstab_file" << EOF
# Generated fstab entries for dual-boot Ubuntu + CachyOS
# Date: $(date)
# NVMe disk: /dev/$nvme_disk
# SATA SSD: /dev/$sata_disk

# EFI System Partition (shared by both OSes)
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}1")  /boot/efi  vfat  umask=0077  0  2

# ===== UBUNTU PARTITIONS =====
# Ubuntu root (NVMe)
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}2")  /  ext4  defaults,noatime,nodiratime,data=writeback,barrier=0  0  1

# Ubuntu home (SATA SSD)
UUID=$(blkid -s UUID -o value "/dev/${sata_disk}1")  /home  ext4  defaults,noatime,nodiratime  0  2

# ===== CACHYOS PARTITIONS =====
# CachyOS root (NVMe) - Btrfs with subvolumes
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}3")  /  btrfs  defaults,noatime,compress=zstd:1,space_cache=v2,subvol=@  0  1
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}3")  /home  btrfs  defaults,noatime,compress=zstd:1,space_cache=v2,subvol=@home  0  2
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}3")  /.snapshots  btrfs  defaults,noatime,compress=zstd:1,space_cache=v2,subvol=@snapshots  0  2

# CachyOS home (SATA SSD) - if not using Btrfs subvolume
# UUID=$(blkid -s UUID -o value "/dev/${sata_disk}2")  /home  ext4  defaults,noatime,nodiratime  0  2

# ===== SHARED PARTITIONS =====
# Swap (shared)
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}4")  none  swap  sw,pri=10  0  0

# Cache partition (shared)
UUID=$(blkid -s UUID -o value "/dev/${nvme_disk}${nvme_p}5")  /var/cache  xfs  defaults,noatime,nodiratime,logbufs=8,logbsize=256k,largeio,swalloc  0  2

# Workspace (shared, optimized for parallel I/O)
UUID=$(blkid -s UUID -o value "/dev/${sata_disk}3")  /workspace  xfs  defaults,noatime,nodiratime,logbufs=8,logbsize=256k,largeio,swalloc,allocsize=256k,inode64  0  2

# ===== NOTES =====
# 1. For CachyOS, you'll need to create Btrfs subvolumes:
#    mount /dev/${nvme_disk}${nvme_p}3 /mnt
#    btrfs subvolume create /mnt/@
#    btrfs subvolume create /mnt/@home
#    btrfs subvolume create /mnt/@snapshots
#    umount /mnt
#
# 2. The workspace partition is shared between both OSes with:
#    - XFS for parallel I/O performance
#    - Optimized for 1000+ concurrent AI agents
#    - 256k allocation size for large files
#
# 3. Mount options explained:
#    - noatime: Don't update access times (performance)
#    - nodiratime: Don't update directory access times
#    - logbufs=8: More log buffers for better performance
#    - logbsize=256k: Larger log buffer size
#    - largeio: Optimize for large I/O operations
#    - swalloc: Stripe-width aware allocation
#    - allocsize=256k: Allocation size hint
#    - inode64: Allow 64-bit inode numbers
#
# 4. For Ubuntu, add to /etc/fstab the Ubuntu-specific entries
# 5. For CachyOS, add to /etc/fstab the CachyOS-specific + shared entries
EOF

    log "fstab entries saved to: $fstab_file"
    cat "$fstab_file" | tee -a "$LOG_FILE"
}

# ===================================
# VERIFICATION
# ===================================

verify_partitions() {
    log_section "VERIFICATION"

    log "Verifying all partitions are properly formatted..."

    lsblk -f | tee -a "$LOG_FILE"

    log ""
    log "Checking filesystem labels..."
    blkid | grep -E "LABEL=" | tee -a "$LOG_FILE"

    log ""
    log "Partition summary:"
    local nvme_disk="$1"
    local sata_disk="$2"

    echo "NVMe partitions:" | tee -a "$LOG_FILE"
    parted "/dev/$nvme_disk" print | tee -a "$LOG_FILE"

    echo "" | tee -a "$LOG_FILE"
    echo "SATA SSD partitions:" | tee -a "$LOG_FILE"
    parted "/dev/$sata_disk" print | tee -a "$LOG_FILE"
}

# ===================================
# MAIN EXECUTION
# ===================================

main() {
    log "Starting disk partitioning process..."
    log "Log file: $LOG_FILE"

    # Detect available disks
    detect_disks

    # Select NVMe disk
    log_section "STEP 1: SELECT NVMe DISK"
    nvme_disk=$(select_disk "NVMe (OS roots + swap + cache)" "500GB")

    echo ""

    # Select SATA SSD
    log_section "STEP 2: SELECT SATA SSD"
    sata_disk=$(select_disk "SATA SSD (home directories + workspace)" "4TB")

    echo ""

    # Final confirmation
    log_section "FINAL CONFIRMATION"
    echo -e "${YELLOW}About to partition:${NC}"
    echo -e "  NVMe:     /dev/$nvme_disk"
    echo -e "  SATA SSD: /dev/$sata_disk"
    echo ""
    echo -e "${RED}⚠️  THIS IS YOUR LAST CHANCE TO ABORT!${NC}"
    echo -e "${RED}⚠️  ALL DATA ON BOTH DISKS WILL BE DESTROYED!${NC}"
    read -p "Type 'DESTROY ALL DATA' (exact phrase) to proceed: " final_confirmation

    if [[ "$final_confirmation" != "DESTROY ALL DATA" ]]; then
        error_exit "Operation cancelled by user"
    fi

    # Partition disks
    partition_nvme "$nvme_disk"
    partition_sata "$sata_disk"

    # Wait for kernel to recognize partitions
    log "Waiting for kernel to recognize new partitions..."
    sleep 3
    partprobe || log_warn "partprobe failed (may not be critical)"
    sleep 2

    # Format partitions
    format_nvme "$nvme_disk"
    format_sata "$sata_disk"

    # Generate fstab
    generate_fstab "$nvme_disk" "$sata_disk"

    # Verify
    verify_partitions "$nvme_disk" "$sata_disk"

    # Summary
    log_section "PARTITIONING COMPLETE"

    cat << EOF

${GREEN}✅ DISK PARTITIONING COMPLETED SUCCESSFULLY!${NC}

📍 Disks Partitioned:
  - NVMe:     /dev/$nvme_disk (EFI + Ubuntu / + CachyOS / + Swap + Cache)
  - SATA SSD: /dev/$sata_disk (Ubuntu /home + CachyOS /home + /workspace)

📝 Log File: $LOG_FILE
📋 fstab entries: $LOG_DIR/fstab-entries-$DATE.txt

⚠️  Important Next Steps:

1. BEFORE installing Ubuntu/CachyOS, review the fstab file:
   less $LOG_DIR/fstab-entries-$DATE.txt

2. For CachyOS, create Btrfs subvolumes after mounting:
   mount /dev/${nvme_disk}${nvme_p:-}3 /mnt
   btrfs subvolume create /mnt/@
   btrfs subvolume create /mnt/@home
   btrfs subvolume create /mnt/@snapshots
   umount /mnt

3. During Ubuntu installation:
   - Select "Something else" for partitioning
   - Assign /dev/${nvme_disk}${nvme_p:-}1 to /boot/efi (do NOT format)
   - Assign /dev/${nvme_disk}${nvme_p:-}2 to / (do NOT format again)
   - Assign /dev/${sata_disk}1 to /home (do NOT format again)

4. During CachyOS installation:
   - Use manual partitioning
   - Mount Btrfs subvolumes as shown in fstab
   - Share EFI partition (do NOT format)

5. After both OS installations:
   - Add shared partitions (workspace, cache) to both /etc/fstab files
   - Configure systemd-boot as described in partition-design.md

🎯 The disks are ready for OS installation!

EOF
}

# Check dependencies
for cmd in parted mkfs.ext4 mkfs.btrfs mkfs.xfs mkfs.fat mkswap blkid lsblk; do
    if ! command -v "$cmd" &> /dev/null; then
        error_exit "Required command not found: $cmd"
    fi
done

# Execute main function
main
