#!/usr/bin/env bash
# the-tilt-shifter — tonal balance explorer
#
# Smoothly shifts the overall tonal balance from warm (bass-heavy) to
# bright (treble-forward) using CamillaDSP's Tilt filter.
#
# Usage:
#   the-tilt-shifter.sh warm          -3 dB tilt (warmer)
#   the-tilt-shifter.sh neutral        0 dB tilt (flat)
#   the-tilt-shifter.sh analytical    +3 dB tilt (brighter)
#   the-tilt-shifter.sh <number>      custom tilt in dB (e.g. -1.5)
#   the-tilt-shifter.sh off           restore base config
#   the-tilt-shifter.sh sweep         demo all presets, 5s each

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

apply_tilt() {
    local gain="$1"
    local label="$2"
    "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

config['filters']['tilt'] = {
    'type': 'Biquad',
    'parameters': {
        'type': 'Tilt',
        'gain': $gain,
    }
}

add_stereo_filter_before_limiter(config, 'tilt')

apply_config(config, '$label')
"
}

case "${1:-warm}" in
    warm)
        echo "Tilt Shifter: WARM (-3 dB)"
        apply_tilt "-3.0" "Tilt: warm (-3 dB)"
        ;;
    neutral)
        echo "Tilt Shifter: NEUTRAL (0 dB)"
        echo "  (this is your base config)"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    analytical)
        echo "Tilt Shifter: ANALYTICAL (+3 dB)"
        apply_tilt "3.0" "Tilt: analytical (+3 dB)"
        ;;
    off)
        echo "Tilt Shifter: OFF"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    sweep)
        echo "Tilt Shifter: SWEEP"
        echo ""
        for preset in warm neutral analytical; do
            bash "$0" "$preset"
            sleep 5
        done
        echo ""
        echo "Done — ended on: analytical"
        ;;
    -[0-9]*|[0-9]*)
        echo "Tilt Shifter: ${1} dB"
        apply_tilt "$1" "Tilt: ${1} dB"
        ;;
    *)
        echo "Usage: the-tilt-shifter.sh warm|neutral|analytical|<dB>|off|sweep"
        ;;
esac
