#!/usr/bin/env bash
# CamillaDSP profile and headphone switching script (macOS)
#
# Equivalent of the PipeWire headphone-switch.sh but using
# CamillaDSP's websocket API for live config reloading.
#
# Usage:
#   headphone-switch.sh clean|crossfeed|room    Switch DSP profile
#   headphone-switch.sh eq hd800s|monarch       Switch headphone EQ
#   headphone-switch.sh rate <samplerate>        Switch sample rate
#   headphone-switch.sh status                   Show current state
#
# Requires: CamillaDSP running with websocket on port 1234

set -euo pipefail

CDSP_PORT="${CDSP_PORT:-1234}"
CDSP_ADDR="${CDSP_ADDR:-127.0.0.1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/configs"
COEFFS_DIR="$SCRIPT_DIR/coeffs"
AUTOEQ_DIR="$SCRIPT_DIR/../autoeq"

# State file to track current profile and rate
STATE_FILE="$SCRIPT_DIR/.state"

# Load or initialize state
if [[ -f "$STATE_FILE" ]]; then
    source "$STATE_FILE"
else
    CURRENT_PROFILE="clean"
    CURRENT_RATE="96000"
fi

profile_to_file() {
    local profile="$1"
    local rate="${2:-$CURRENT_RATE}"
    case "$profile" in
        clean)     echo "camilladsp-${rate}.yml" ;;
        crossfeed) echo "camilladsp-crossfeed-${rate}.yml" ;;
        room)      echo "camilladsp-room-${rate}.yml" ;;
        *)         echo "ERROR: Unknown profile: $profile" >&2; return 1 ;;
    esac
}

save_state() {
    cat > "$STATE_FILE" <<EOF
CURRENT_PROFILE="$CURRENT_PROFILE"
CURRENT_RATE="$CURRENT_RATE"
EOF
}

# Send config to CamillaDSP via websocket using the Python helper
cdsp_set_config() {
    local config_file="$1"
    local full_path="$CONFIG_DIR/$config_file"

    if [[ ! -f "$full_path" ]]; then
        echo "ERROR: Config not found: $full_path" >&2
        echo "Run generate-rate-configs.sh first." >&2
        return 1
    fi

    # Use Python to send websocket command (CamillaDSP v4 API)
    python3 -c "
import json, socket, sys

config_path = '$full_path'
with open(config_path) as f:
    config_content = f.read()

msg = json.dumps({'SetConfig': config_content})
header = f'GET /ws HTTP/1.1\r\nHost: ${CDSP_ADDR}:${CDSP_PORT}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n'

# Simple approach: use curl to POST the config reload
import subprocess
result = subprocess.run(
    ['curl', '-s', '-X', 'POST',
     f'http://${CDSP_ADDR}:${CDSP_PORT}/api/setconfigfile',
     '-H', 'Content-Type: text/plain',
     '-d', config_path],
    capture_output=True, text=True, timeout=5
)
if result.returncode == 0:
    print(f'Loaded: {config_path}')
else:
    # Fallback: restart CamillaDSP with new config
    print(f'Websocket unavailable, restart CamillaDSP with: camilladsp -p 1234 {config_path}', file=sys.stderr)
    sys.exit(1)
" 2>&1
}

case "${1:-status}" in
    clean|crossfeed|room)
        CURRENT_PROFILE="$1"
        config_file=$(profile_to_file "$CURRENT_PROFILE" "$CURRENT_RATE")
        echo "Switching to: $CURRENT_PROFILE (${CURRENT_RATE}Hz)"
        cdsp_set_config "$config_file" || true
        save_state
        echo "Active: $CURRENT_PROFILE @ ${CURRENT_RATE}Hz"
        ;;

    eq)
        headphone="${2:?Usage: headphone-switch.sh eq hd800s|monarch}"
        case "$headphone" in
            hd800s|hd800)
                echo "Switching EQ to: Sennheiser HD800S"
                for rate in 44100 48000 96000 192000 384000; do
                    ln -sf "$AUTOEQ_DIR/Sennheiser HD800 minimum phase ${rate} Hz.wav" \
                           "$AUTOEQ_DIR/active_${rate}Hz.wav"
                done
                ;;
            monarch|mkii)
                echo "Switching EQ to: ThieAudio Monarch MKII"
                for rate in 44100 48000 96000 192000 384000; do
                    ln -sf "$AUTOEQ_DIR/ThieAudio Monarch MKII minimum phase ${rate}Hz.wav" \
                           "$AUTOEQ_DIR/active_${rate}Hz.wav"
                done
                ;;
            *)
                echo "ERROR: Unknown headphone: $headphone" >&2
                echo "Available: hd800s, monarch" >&2
                exit 1
                ;;
        esac
        # Reload current config to pick up new symlinks
        config_file=$(profile_to_file "$CURRENT_PROFILE" "$CURRENT_RATE")
        cdsp_set_config "$config_file" || true
        save_state
        echo "EQ active: $headphone"
        ;;

    rate)
        new_rate="${2:?Usage: headphone-switch.sh rate <samplerate>}"
        case "$new_rate" in
            44100|48000|96000|192000|384000)
                CURRENT_RATE="$new_rate"
                config_file=$(profile_to_file "$CURRENT_PROFILE" "$CURRENT_RATE")
                echo "Switching rate to: ${CURRENT_RATE}Hz"
                cdsp_set_config "$config_file" || true
                save_state
                echo "Active: $CURRENT_PROFILE @ ${CURRENT_RATE}Hz"
                ;;
            *)
                echo "ERROR: Unsupported rate: $new_rate" >&2
                echo "Available: 44100, 48000, 96000, 192000, 384000" >&2
                exit 1
                ;;
        esac
        ;;

    status)
        echo "CamillaDSP Headphone DSP Status"
        echo "================================"
        echo "Profile:     $CURRENT_PROFILE"
        echo "Sample Rate: ${CURRENT_RATE}Hz"
        echo "Config Dir:  $CONFIG_DIR"
        echo ""
        echo "Active EQ IRs:"
        for f in "$AUTOEQ_DIR"/active_*.wav; do
            target=$(readlink "$f" 2>/dev/null || echo "(not a symlink)")
            echo "  $(basename "$f") → $(basename "$target")"
        done
        echo ""
        echo "DAC Output:"
        SwitchAudioSource -c 2>/dev/null || echo "(SwitchAudioSource not found)"
        ;;

    *)
        echo "Usage: headphone-switch.sh <command>"
        echo ""
        echo "Commands:"
        echo "  clean|crossfeed|room    Switch DSP profile"
        echo "  eq hd800s|monarch       Switch headphone EQ"
        echo "  rate <samplerate>       Switch sample rate"
        echo "  status                  Show current state"
        ;;
esac
