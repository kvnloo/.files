#!/bin/bash
# Disk Usage Information Gathering Script (no sudo required)
# Run this script: bash gather-disk-usage.sh

# Get script directory and set output path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_DIR="$SCRIPT_DIR/../docs"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "=== Gathering Disk Usage Information ==="
echo ""

echo "Gathering overall disk usage..."
df -h > "$OUTPUT_DIR/disk-usage.txt"

echo "Gathering home directory size..."
du -sh $HOME > "$OUTPUT_DIR/home-size.txt" 2>&1

echo "Gathering workspace size..."
du -sh $HOME/workspace > "$OUTPUT_DIR/workspace-size.txt" 2>&1 || echo "No workspace directory found" > "$OUTPUT_DIR/workspace-size.txt"

echo "Gathering detailed directory sizes in home..."
du -h --max-depth=1 $HOME 2>/dev/null | sort -hr > "$OUTPUT_DIR/home-breakdown.txt"

echo ""
echo "✅ Disk usage information saved to:"
echo "   - $OUTPUT_DIR/disk-usage.txt"
echo "   - $OUTPUT_DIR/home-size.txt"
echo "   - $OUTPUT_DIR/workspace-size.txt"
echo "   - $OUTPUT_DIR/home-breakdown.txt"
