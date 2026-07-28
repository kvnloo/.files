#!/usr/bin/env bash
# the-vinyl-experience — analog warmth simulation
#
# Simulates the frequency response characteristics of vinyl playback:
#   - Gentle HF rolloff above 15 kHz (worn stylus character)
#   - Subtle low-frequency rise below 100 Hz (turntable resonance)
#   - Warm tonal tilt (-1.5 dB)
#   - Rumble filter at 20 Hz
#
# Usage:
#   the-vinyl-experience.sh on     Enable vinyl simulation
#   the-vinyl-experience.sh off    Restore base config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

case "${1:-on}" in
    on)
        echo "The Vinyl Experience: ON"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

# HF rolloff — gentle lowpass simulating worn stylus
config['filters']['vinyl_hf_rolloff'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Lowpass', 'freq': 15000, 'q': 0.5}
}

# Low-frequency rise — turntable resonance character
config['filters']['vinyl_lf_rise'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Lowshelf', 'freq': 100, 'gain': 2.0, 'slope': 6.0}
}

# Warm tonal tilt
config['filters']['vinyl_tilt'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Tilt', 'gain': -1.5}
}

# Rumble filter — subsonic protection
config['filters']['vinyl_rumble'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Highpass', 'freq': 20, 'q': 0.707}
}

add_stereo_filter_before_limiter(config, 'vinyl_rumble')
add_stereo_filter_before_limiter(config, 'vinyl_lf_rise')
add_stereo_filter_before_limiter(config, 'vinyl_hf_rolloff')
add_stereo_filter_before_limiter(config, 'vinyl_tilt')

apply_config(config, f'Vinyl simulation ({profile} @ {rate}Hz)')
"
        ;;
    off)
        echo "The Vinyl Experience: OFF"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    *)
        echo "Usage: the-vinyl-experience.sh on|off"
        ;;
esac
