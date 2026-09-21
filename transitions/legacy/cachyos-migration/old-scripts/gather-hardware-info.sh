#!/bin/bash
# Hardware Information Gathering Script (requires sudo)
# Run this script separately: sudo bash gather-hardware-info.sh

# Get script directory and set output path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_FILE="$SCRIPT_DIR/../docs/hardware-info.txt"

# Create docs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/../docs"

echo "=== SYSTEM HARDWARE INFORMATION ===" > "$OUTPUT_FILE"
echo "Generated: $(date)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "=== CPU Information ===" >> "$OUTPUT_FILE"
lscpu >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== Memory Information ===" >> "$OUTPUT_FILE"
free -h >> "$OUTPUT_FILE" 2>&1
cat /proc/meminfo >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== Disk Information ===" >> "$OUTPUT_FILE"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,UUID >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== Detailed Disk Info ===" >> "$OUTPUT_FILE"
fdisk -l >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== ZFS Pool Status ===" >> "$OUTPUT_FILE"
zpool status >> "$OUTPUT_FILE" 2>&1
zpool list >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== ZFS Dataset Info ===" >> "$OUTPUT_FILE"
zfs list >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== Disk I/O Stats ===" >> "$OUTPUT_FILE"
iostat -x 1 5 >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== PCI Devices ===" >> "$OUTPUT_FILE"
lspci >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== Storage Controllers ===" >> "$OUTPUT_FILE"
lspci | grep -i storage >> "$OUTPUT_FILE" 2>&1
lspci | grep -i raid >> "$OUTPUT_FILE" 2>&1
lspci | grep -i sata >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "=== SMART Disk Health ===" >> "$OUTPUT_FILE"
for disk in /dev/sd?; do
    echo "--- $disk ---" >> "$OUTPUT_FILE"
    smartctl -a "$disk" >> "$OUTPUT_FILE" 2>&1
    echo "" >> "$OUTPUT_FILE"
done

echo "=== NVMe Devices ===" >> "$OUTPUT_FILE"
nvme list >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo ""
echo "✅ Hardware information saved to: $OUTPUT_FILE"
