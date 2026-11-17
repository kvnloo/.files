#!/usr/bin/env bash
# frequency-spotlight — isolate frequency bands
#
# A "flashlight" that sweeps across the frequency spectrum, letting you
# hear what lives in each band. Great for ear training and comparing
# headphones.
#
# Usage:
#   frequency-spotlight.sh sub          20-60 Hz
#   frequency-spotlight.sh bass         60-250 Hz
#   frequency-spotlight.sh lowmid       250-500 Hz
#   frequency-spotlight.sh mid          500-2000 Hz
#   frequency-spotlight.sh uppermid     2000-4000 Hz
#   frequency-spotlight.sh presence     4000-8000 Hz
#   frequency-spotlight.sh air          8000-20000 Hz
#   frequency-spotlight.sh sweep [sec]  All bands in sequence (default 5s each)
#   frequency-spotlight.sh off          Restore full spectrum

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

BAND_ORDER=(sub bass lowmid mid uppermid presence air)

apply_band() {
    local band="$1" lo hi
    case "$band" in
        sub)      lo=20;   hi=60 ;;
        bass)     lo=60;   hi=250 ;;
        lowmid)   lo=250;  hi=500 ;;
        mid)      lo=500;  hi=2000 ;;
        uppermid) lo=2000; hi=4000 ;;
        presence) lo=4000; hi=8000 ;;
        air)      lo=8000; hi=20000 ;;
    esac

    echo "Frequency Spotlight: $band (${lo}-${hi} Hz)"
    "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

# Highpass at the low edge, lowpass at the high edge
# Use 2nd order Butterworth (q=0.707) for clean slopes
config['filters']['spotlight_hp'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Highpass', 'freq': $lo, 'q': 0.707}
}
config['filters']['spotlight_lp'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Lowpass', 'freq': $hi, 'q': 0.707}
}

# Add a gain boost to compensate for narrowband level drop
config['filters']['spotlight_gain'] = {
    'type': 'Gain',
    'parameters': {'gain': 6.0, 'inverted': False}
}

add_stereo_filter_before_limiter(config, 'spotlight_hp')
add_stereo_filter_before_limiter(config, 'spotlight_lp')
add_stereo_filter_before_limiter(config, 'spotlight_gain')

apply_config(config, '$band ($lo-${hi} Hz)')
"
}

case "${1:-sweep}" in
    sub|bass|lowmid|mid|uppermid|presence|air)
        apply_band "$1"
        ;;
    sweep)
        interval="${2:-5}"
        echo "Frequency Spotlight: SWEEP (${interval}s per band)"
        echo ""
        for band in "${BAND_ORDER[@]}"; do
            apply_band "$band"
            sleep "$interval"
        done
        echo ""
        echo "Done — restoring full spectrum"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    off)
        echo "Frequency Spotlight: OFF (full spectrum)"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    *)
        echo "Usage: frequency-spotlight.sh sub|bass|lowmid|mid|uppermid|presence|air|sweep|off"
        ;;
esac
