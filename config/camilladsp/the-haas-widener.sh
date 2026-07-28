#!/usr/bin/env bash
# the-haas-widener — precedence effect stereo enhancement
#
# Adds a short delay (1-15ms) to the cross-fed signal to exploit the
# Haas (precedence) effect. Widens perceived soundstage without changing
# tonal balance. The brain localizes sound based on the first-arriving
# signal, so the delay creates a convincing sense of width.
#
# Usage:
#   the-haas-widener.sh <delay_ms>     Set delay (1-15ms, default 8)
#   the-haas-widener.sh sweep          Demo delays from 1-15ms, 5s each
#   the-haas-widener.sh off            Restore base config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

apply_haas() {
    local delay_ms="$1"
    "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, rate = load_clean_config()

# Add crossfeed filters with Haas delay
config['filters']['xfeed_lowpass'] = {
    'type': 'Biquad',
    'parameters': {'type': 'Lowpass', 'freq': 700, 'q': 0.5}
}
config['filters']['xfeed_gain'] = {
    'type': 'Gain',
    'parameters': {'gain': -4.5, 'inverted': False}
}
config['filters']['haas_delay'] = {
    'type': 'Delay',
    'parameters': {'delay': $delay_ms, 'unit': 'ms', 'subsample': False}
}

if 'mixers' not in config:
    config['mixers'] = {}

# Split stereo to 4 channels for crossfeed
config['mixers']['haas_split'] = {
    'channels': {'in': 2, 'out': 4},
    'mapping': [
        {'dest': 0, 'sources': [{'channel': 0, 'gain': 0, 'inverted': False}]},
        {'dest': 1, 'sources': [{'channel': 1, 'gain': 0, 'inverted': False}]},
        {'dest': 2, 'sources': [{'channel': 1, 'gain': 0, 'inverted': False}]},
        {'dest': 3, 'sources': [{'channel': 0, 'gain': 0, 'inverted': False}]},
    ]
}

config['mixers']['haas_mix'] = {
    'channels': {'in': 4, 'out': 2},
    'mapping': [
        {'dest': 0, 'sources': [
            {'channel': 0, 'gain': 0, 'inverted': False},
            {'channel': 2, 'gain': 0, 'inverted': False},
        ]},
        {'dest': 1, 'sources': [
            {'channel': 1, 'gain': 0, 'inverted': False},
            {'channel': 3, 'gain': 0, 'inverted': False},
        ]},
    ]
}

# Rebuild pipeline: EQ -> split -> crossfeed+delay on ch2,3 -> mix -> compressor -> limiter
pipeline = [
    {'type': 'Filter', 'channels': [0], 'names': ['eq_l']},
    {'type': 'Filter', 'channels': [1], 'names': ['eq_r']},
    {'type': 'Mixer', 'name': 'haas_split'},
    {'type': 'Filter', 'channels': [2], 'names': ['xfeed_lowpass', 'xfeed_gain', 'haas_delay']},
    {'type': 'Filter', 'channels': [3], 'names': ['xfeed_lowpass', 'xfeed_gain', 'haas_delay']},
    {'type': 'Mixer', 'name': 'haas_mix'},
]

if 'processors' in config and 'compressor' in config.get('processors', {}):
    pipeline.append({'type': 'Processor', 'name': 'compressor'})

pipeline.append({'type': 'Filter', 'channels': [0], 'names': ['limiter']})
pipeline.append({'type': 'Filter', 'channels': [1], 'names': ['limiter']})

config['pipeline'] = pipeline

apply_config(config, f'Haas widener (${delay_ms}ms delay, clean @ {rate}Hz)')
"
}

case "${1:-8}" in
    sweep)
        echo "The Haas Widener: SWEEP"
        echo ""
        for ms in 1 3 5 8 10 15; do
            echo "$(date '+%H:%M:%S')  Delay: ${ms}ms"
            apply_haas "$ms"
            sleep 5
        done
        echo ""
        echo "Done — ended on: 15ms"
        ;;
    off)
        echo "The Haas Widener: OFF"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    [0-9]*)
        echo "The Haas Widener: ${1}ms delay"
        apply_haas "$1"
        ;;
    *)
        echo "Usage: the-haas-widener.sh <delay_ms>|sweep|off"
        ;;
esac
