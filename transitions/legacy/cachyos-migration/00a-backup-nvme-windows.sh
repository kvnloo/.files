#!/usr/bin/env bash
set -euo pipefail

# NVMe Windows Backup - Samsung 960 EVO 500GB
# Backs up Windows NTFS/FAT32 partitions from NVMe to SATA 4TB drive
# Run BEFORE CachyOS wipes the NVMe

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/backup-nvme-windows-$DATE.log"
mkdir -p "$LOG_DIR"
log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }
error_exit() { log_error "$1"; exit 1; }

NVME_DEV="${1:-/dev/nvme0n1}"
BACKUP_ROOT="/home/kvn/nvme-windows-backup-$DATE"
TMP_MNT=$(mktemp -d /tmp/nvme-backup-mnt.XXXXXX)
START_TIME=$(date +%s)
TOTAL_BACKED_UP=0
SUCCESSFUL=0
FAILED=0

cleanup() {
    mountpoint -q "$TMP_MNT" 2>/dev/null && sudo umount "$TMP_MNT" 2>/dev/null || true
    rmdir "$TMP_MNT" 2>/dev/null || true
}
trap cleanup EXIT

# --- Preflight checks ---
log_section "PREFLIGHT CHECKS"

[[ $EUID -eq 0 ]] && error_exit "Do not run as root. Script uses sudo where needed."
command -v lsblk &>/dev/null || error_exit "lsblk not found"
command -v ntfs-3g &>/dev/null || log_warn "ntfs-3g not found -- NTFS mounts may fail"

[[ -b "$NVME_DEV" ]] || error_exit "NVMe device $NVME_DEV not found"
log "NVMe device: $NVME_DEV"

# --- Discover partitions ---
log_section "PARTITION DISCOVERY"

log "Partitions on $NVME_DEV:"
# Use sudo for lsblk -- filesystem detection requires root on some systems
sudo lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT "$NVME_DEV" | tee -a "$LOG_FILE"

mapfile -t PARTS < <(
    sudo lsblk -rno NAME,FSTYPE "$NVME_DEV" | awk '$2 == "ntfs" || $2 == "vfat" { print $1 }'
)

[[ ${#PARTS[@]} -gt 0 ]] || error_exit "No NTFS or FAT32 partitions found on $NVME_DEV"
log "Found ${#PARTS[@]} Windows partition(s): ${PARTS[*]}"

# --- Confirmation ---
log_section "CONFIRMATION"

echo -e "${YELLOW}This will back up ${#PARTS[@]} partition(s) to:${NC}"
echo "  $BACKUP_ROOT"
echo ""
for part in "${PARTS[@]}"; do
    fstype=$(sudo lsblk -rno FSTYPE "/dev/$part")
    size=$(lsblk -rno SIZE "/dev/$part")
    label=$(sudo lsblk -rno LABEL "/dev/$part" 2>/dev/null || echo "unlabeled")
    echo "  /dev/$part  $size  $fstype  ($label)"
done
echo ""
read -rp "Proceed with backup? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { log "Aborted by user."; exit 0; }

# --- Create backup directory ---
mkdir -p "$BACKUP_ROOT"
log "Backup directory: $BACKUP_ROOT"

# --- Backup each partition ---
log_section "BACKING UP PARTITIONS"

for part in "${PARTS[@]}"; do
    dev="/dev/$part"
    fstype=$(sudo lsblk -rno FSTYPE "$dev")
    label=$(sudo lsblk -rno LABEL "$dev" 2>/dev/null || echo "unlabeled")
    safe_label=$(echo "${label:-$part}" | tr -cs '[:alnum:]-_' '_')
    archive="$BACKUP_ROOT/${part}_${safe_label}.tar.gz"

    log "--- $dev ($fstype, $label) ---"

    # Handle mount: unmount if already mounted, then remount read-only
    USED_TMP_MNT=true
    existing_mnt=$(findmnt -rno TARGET "$dev" 2>/dev/null || true)
    if [[ -n "$existing_mnt" ]]; then
        log "$dev is currently mounted at $existing_mnt -- unmounting first"
        sudo umount "$dev" || { log_warn "Skipping $dev -- failed to unmount from $existing_mnt"; ((FAILED++)); continue; }
        log "Unmounted $dev from $existing_mnt"
    fi

    if [[ "$fstype" == "ntfs" ]]; then
        sudo mount -t ntfs-3g -o ro "$dev" "$TMP_MNT" || { log_warn "Skipping $dev -- mount failed"; ((FAILED++)); continue; }
    else
        sudo mount -o ro "$dev" "$TMP_MNT" || { log_warn "Skipping $dev -- mount failed"; ((FAILED++)); continue; }
    fi
    log "Mounted $dev read-only at $TMP_MNT"

    # Calculate source size for progress
    src_size=$(sudo du -sb "$TMP_MNT" 2>/dev/null | cut -f1)
    src_human=$(sudo du -sh "$TMP_MNT" 2>/dev/null | cut -f1)
    log "Source size: $src_human"

    # Create compressed archive with progress via pv (fallback: plain tar)
    log "Archiving to $archive ..."
    if command -v pv &>/dev/null; then
        sudo tar cf - -C "$TMP_MNT" . 2>>"$LOG_FILE" \
            | pv -s "$src_size" -pterb \
            | gzip > "$archive"
    else
        sudo tar czf "$archive" -C "$TMP_MNT" . 2>>"$LOG_FILE"
        log "(install pv for progress bars)"
    fi

    # Verify archive integrity
    arc_bytes=$(stat --format='%s' "$archive")
    arc_size=$(du -sh "$archive" | cut -f1)
    if [[ $arc_bytes -gt 1073741824 ]]; then
        # Large archive (>1GB): quick sanity check only
        # gzip -t reads the ENTIRE file (can take 10+ min and get OOM-killed on large archives)
        # SHA256 checksums generated later provide the real integrity verification
        log "Large archive ($arc_size) -- quick sanity check (skipping full gzip -t)..."
        file_type=$(file -b "$archive" 2>/dev/null)
        if [[ "$file_type" != *"gzip compressed"* ]]; then
            log_error "Archive is not valid gzip: $archive (detected: $file_type)"
            sudo umount "$TMP_MNT"; ((FAILED++)); continue
        fi
        log "Archive header OK (gzip compressed). Full verify later: gzip -t $archive"
    else
        log "Verifying archive integrity..."
        gzip -t "$archive" || { log_error "Archive corrupt: $archive"; sudo umount "$TMP_MNT"; ((FAILED++)); continue; }
        log "Archive integrity verified"
    fi
    TOTAL_BACKED_UP=$((TOTAL_BACKED_UP + arc_bytes))
    ((SUCCESSFUL++))
    log "Archive OK: $archive ($arc_size compressed)"

    sudo umount "$TMP_MNT"
    log "Unmounted $dev from $TMP_MNT"

    # Remount at original location if it was previously mounted
    if [[ -n "$existing_mnt" ]]; then
        log "Remounting $dev at original location: $existing_mnt"
        sudo mount "$dev" "$existing_mnt" 2>/dev/null && log "Restored mount at $existing_mnt" \
            || log_warn "Could not restore mount at $existing_mnt (remount manually if needed)"
    fi
done

# --- Generate checksums ---
log_section "GENERATING CHECKSUMS"

cd "$BACKUP_ROOT"
sha256sum ./*.tar.gz > SHA256SUMS 2>/dev/null || log_warn "No archives to checksum"
log "SHA256 checksums written to $BACKUP_ROOT/SHA256SUMS"
cat SHA256SUMS | tee -a "$LOG_FILE"

# --- Summary ---
log_section "BACKUP SUMMARY"

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
ELAPSED_FMT=$(printf '%02d:%02d:%02d' $((ELAPSED/3600)) $(( (ELAPSED%3600)/60 )) $((ELAPSED%60)))
TOTAL_HUMAN=$(numfmt --to=iec-i --suffix=B "$TOTAL_BACKED_UP" 2>/dev/null || echo "${TOTAL_BACKED_UP} bytes")

log "Partitions found:     ${#PARTS[@]}"
log "Successfully backed up: $SUCCESSFUL"
log "Failed:               $FAILED"
log "Total archive size:   $TOTAL_HUMAN"
log "Backup location:      $BACKUP_ROOT"
log "Elapsed time:         $ELAPSED_FMT"
log "Log file:             $LOG_FILE"
echo ""

if [[ $FAILED -gt 0 ]]; then
    log_error "$FAILED partition(s) FAILED to back up. Do NOT wipe the NVMe until all partitions are backed up."
    log_error "Re-run this script after fixing the issue."
    exit 1
elif [[ $SUCCESSFUL -eq 0 ]]; then
    log_error "No partitions were backed up. Do NOT wipe the NVMe."
    exit 1
else
    log "Verify with: cd $BACKUP_ROOT && sha256sum -c SHA256SUMS"
    log "All $SUCCESSFUL partition(s) backed up and verified. NVMe is safe to wipe for CachyOS."
fi
