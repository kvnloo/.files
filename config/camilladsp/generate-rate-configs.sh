#!/usr/bin/env bash
# Generate per-sample-rate CamillaDSP configs from the base templates.
# Each rate gets its own copy of each profile (clean, crossfeed, room)
# with the correct sample rate and matching FIR coefficient file.
#
# Usage: ./generate-rate-configs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/configs"

mkdir -p "$CONFIG_DIR"

RATES=(44100 48000 96000 192000 384000)
PROFILES=(camilladsp camilladsp-crossfeed camilladsp-room)

for rate in "${RATES[@]}"; do
    for profile in "${PROFILES[@]}"; do
        src="$SCRIPT_DIR/${profile}.yml"
        dst="$CONFIG_DIR/${profile}-${rate}.yml"

        sed \
            -e "s/samplerate: 96000/samplerate: ${rate}/" \
            -e "s|coeffs/active_96000Hz.wav|coeffs/active_${rate}Hz.wav|g" \
            "$src" > "$dst"

        echo "Generated: ${profile}-${rate}.yml"
    done
done

echo ""
echo "All rate-specific configs written to: $CONFIG_DIR/"
