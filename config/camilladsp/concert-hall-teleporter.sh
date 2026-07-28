#!/usr/bin/env bash
# concert-hall-teleporter — swap between BRIRs from famous venues
#
# Place your music in different acoustic spaces by loading venue-specific
# impulse responses. Uses the same true-stereo convolution pipeline as
# the room profile.
#
# To add a venue, place a 4-channel true-stereo WAV IR in coeffs/ and add
# an entry to the VENUES array below.
#
# Usage:
#   concert-hall-teleporter.sh list               Show available venues
#   concert-hall-teleporter.sh <venue>             Switch to venue
#   concert-hall-teleporter.sh tour [seconds]      Cycle all venues (default 10s each)
#   concert-hall-teleporter.sh off                 Restore base config
#
# Free IR sources:
#   - OpenAIR: openair.hosted.york.ac.uk
#   - Voxengo: voxengo.com/impulses/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
COEFFS_DIR="$SCRIPT_DIR/coeffs"

# Venue registry: name|label|filename|gain_db
# Filename should be a 4-channel true-stereo WAV in coeffs/
# Channels: ch0=FL->L, ch1=FL->R, ch2=FR->L, ch3=FR->R
VENUES=(
    "wdr|WDR Broadcast Control Room (RT60 0.24s)|BRIR_R02_C1_True_Stereo.wav|-6.0"
)

get_venue_field() {
    local entry="$1" field="$2"
    echo "$entry" | cut -d'|' -f"$field"
}

load_venue() {
    local name="$1"
    local entry=""

    for v in "${VENUES[@]}"; do
        if [[ "$(get_venue_field "$v" 1)" == "$name" ]]; then
            entry="$v"
            break
        fi
    done

    if [[ -z "$entry" ]]; then
        echo "ERROR: Unknown venue: $name" >&2
        echo "Run: concert-hall-teleporter.sh list" >&2
        return 1
    fi

    local label=$(get_venue_field "$entry" 2)
    local filename=$(get_venue_field "$entry" 3)
    local gain=$(get_venue_field "$entry" 4)

    if [[ ! -f "$COEFFS_DIR/$filename" ]]; then
        echo "ERROR: IR file not found: $COEFFS_DIR/$filename" >&2
        return 1
    fi

    echo "Concert Hall Teleporter: $label"
    "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, rate = load_clean_config()

# Build a room-style config with the specified BRIR
config['filters']['brir_fl_l'] = {
    'type': 'Conv',
    'parameters': {'type': 'Wav', 'filename': 'coeffs/$filename', 'channel': 0}
}
config['filters']['brir_fl_r'] = {
    'type': 'Conv',
    'parameters': {'type': 'Wav', 'filename': 'coeffs/$filename', 'channel': 1}
}
config['filters']['brir_fr_l'] = {
    'type': 'Conv',
    'parameters': {'type': 'Wav', 'filename': 'coeffs/$filename', 'channel': 2}
}
config['filters']['brir_fr_r'] = {
    'type': 'Conv',
    'parameters': {'type': 'Wav', 'filename': 'coeffs/$filename', 'channel': 3}
}
config['filters']['brir_gain'] = {
    'type': 'Gain',
    'parameters': {'gain': $gain, 'inverted': False}
}

if 'mixers' not in config:
    config['mixers'] = {}

config['mixers']['stereo_to_quad'] = {
    'channels': {'in': 2, 'out': 4},
    'mapping': [
        {'dest': 0, 'sources': [{'channel': 0, 'gain': 0, 'inverted': False}]},
        {'dest': 1, 'sources': [{'channel': 1, 'gain': 0, 'inverted': False}]},
        {'dest': 2, 'sources': [{'channel': 0, 'gain': 0, 'inverted': False}]},
        {'dest': 3, 'sources': [{'channel': 1, 'gain': 0, 'inverted': False}]},
    ]
}
config['mixers']['quad_to_stereo'] = {
    'channels': {'in': 4, 'out': 2},
    'mapping': [
        {'dest': 0, 'sources': [
            {'channel': 0, 'gain': 0, 'inverted': False},
            {'channel': 1, 'gain': 0, 'inverted': False},
        ]},
        {'dest': 1, 'sources': [
            {'channel': 2, 'gain': 0, 'inverted': False},
            {'channel': 3, 'gain': 0, 'inverted': False},
        ]},
    ]
}

# Rebuild pipeline: EQ -> fan out -> BRIR convolve -> mix down -> gain -> compressor -> limiter
pipeline = [
    {'type': 'Filter', 'channels': [0], 'names': ['eq_l']},
    {'type': 'Filter', 'channels': [1], 'names': ['eq_r']},
    {'type': 'Mixer', 'name': 'stereo_to_quad'},
    {'type': 'Filter', 'channels': [0], 'names': ['brir_fl_l']},
    {'type': 'Filter', 'channels': [1], 'names': ['brir_fr_l']},
    {'type': 'Filter', 'channels': [2], 'names': ['brir_fl_r']},
    {'type': 'Filter', 'channels': [3], 'names': ['brir_fr_r']},
    {'type': 'Mixer', 'name': 'quad_to_stereo'},
    {'type': 'Filter', 'channels': [0], 'names': ['brir_gain']},
    {'type': 'Filter', 'channels': [1], 'names': ['brir_gain']},
]

# Add compressor if it exists in base
if 'processors' in config and 'compressor' in config.get('processors', {}):
    pipeline.append({'type': 'Processor', 'name': 'compressor'})

pipeline.append({'type': 'Filter', 'channels': [0], 'names': ['limiter']})
pipeline.append({'type': 'Filter', 'channels': [1], 'names': ['limiter']})

config['pipeline'] = pipeline

apply_config(config, f'$label (clean @ {rate}Hz)')
"
}

case "${1:-list}" in
    list)
        echo "Concert Hall Teleporter — Available Venues"
        echo "==========================================="
        for v in "${VENUES[@]}"; do
            name=$(get_venue_field "$v" 1)
            label=$(get_venue_field "$v" 2)
            file=$(get_venue_field "$v" 3)
            exists="[OK]"
            [[ ! -f "$COEFFS_DIR/$file" ]] && exists="[MISSING]"
            printf "  %-12s  %s  %s\n" "$name" "$exists" "$label"
        done
        echo ""
        echo "Add venues by placing 4-ch true-stereo WAV IRs in: $COEFFS_DIR"
        ;;

    tour)
        interval="${2:-10}"
        echo "Concert Hall Teleporter: TOUR (${interval}s per venue)"
        echo ""
        for v in "${VENUES[@]}"; do
            name=$(get_venue_field "$v" 1)
            load_venue "$name" || continue
            sleep "$interval"
        done
        echo ""
        echo "Tour complete."
        ;;

    off)
        echo "Concert Hall Teleporter: OFF"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;

    *)
        load_venue "$1"
        ;;
esac
