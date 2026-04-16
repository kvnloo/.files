#!/usr/bin/env bash
# late-night-mode — Fletcher-Munson loudness compensation
#
# Boosts bass and treble at low volumes to compensate for how human hearing
# loses sensitivity to those frequencies at quiet levels.
#
# Usage:
#   late-night-mode.sh on       Enable loudness compensation
#   late-night-mode.sh off      Restore base config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

case "${1:-on}" in
    on)
        echo "Late Night Mode: ON"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

config['filters']['loudness'] = {
    'type': 'Loudness',
    'parameters': {
        'reference_level': -20.0,
        'high_boost': 10.0,
        'low_boost': 10.0,
    }
}

add_stereo_filter_before_limiter(config, 'loudness')

apply_config(config, f'Late Night Mode ({profile} @ {rate}Hz)')
"
        ;;
    off)
        echo "Late Night Mode: OFF"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    *)
        echo "Usage: late-night-mode.sh on|off"
        ;;
esac
