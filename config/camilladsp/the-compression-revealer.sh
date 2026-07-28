#!/usr/bin/env bash
# the-compression-revealer — dynamic range awareness tool
#
# Toggle between 3 compression presets to hear what dynamics processing
# does to your music. Makes the loudness war audible.
#
# Usage:
#   the-compression-revealer.sh none       No compression (raw dynamics)
#   the-compression-revealer.sh gentle     Your default (3:1 @ -20dB)
#   the-compression-revealer.sh hyper      Loudness war mode (10:1 @ -30dB)
#   the-compression-revealer.sh sweep      Demo all 3 presets, 10s each
#   the-compression-revealer.sh off        Restore base config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

apply_compression() {
    local mode="$1"
    "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

mode = '$mode'

if mode == 'none':
    # Remove compressor from pipeline
    if 'processors' in config:
        config['processors'].pop('compressor', None)
    config['pipeline'] = [
        step for step in config['pipeline']
        if not (step.get('type') == 'Processor' and step.get('name') == 'compressor')
    ]
    label = 'No compression (raw dynamics)'

elif mode == 'gentle':
    # Default compressor — should already be in base config
    label = 'Gentle (3:1 @ -20dB)'

elif mode == 'hyper':
    # Aggressive loudness-war compression
    if 'processors' not in config:
        config['processors'] = {}
    config['processors']['compressor'] = {
        'type': 'Compressor',
        'parameters': {
            'channels': 2,
            'attack': 0.01,
            'release': 0.3,
            'threshold': -30.0,
            'factor': 10.0,
            'makeup_gain': 6.0,
            'soft_clip': True,
        }
    }
    # Ensure compressor is in pipeline
    has_compressor = any(
        s.get('type') == 'Processor' and s.get('name') == 'compressor'
        for s in config['pipeline']
    )
    if not has_compressor:
        # Insert before limiter
        for i, step in enumerate(config['pipeline']):
            if step.get('type') == 'Filter' and 'limiter' in step.get('names', []):
                config['pipeline'].insert(i, {'type': 'Processor', 'name': 'compressor'})
                break
    label = 'Hyper-compressed (10:1 @ -30dB, +6dB makeup)'

apply_config(config, label)
"
}

case "${1:-gentle}" in
    none)
        echo "Compression Revealer: NONE (raw dynamics)"
        apply_compression "none"
        ;;
    gentle)
        echo "Compression Revealer: GENTLE (3:1 @ -20dB)"
        apply_compression "gentle"
        ;;
    hyper)
        echo "Compression Revealer: HYPER (10:1 @ -30dB)"
        apply_compression "hyper"
        ;;
    sweep)
        echo "Compression Revealer: SWEEP (10s per preset)"
        echo ""
        for mode in none gentle hyper; do
            label="$mode"
            echo "$(date '+%H:%M:%S')  ${label^^}"
            apply_compression "$mode"
            sleep 10
        done
        echo ""
        echo "Done — ended on: hyper"
        ;;
    off)
        echo "Compression Revealer: OFF"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    *)
        echo "Usage: the-compression-revealer.sh none|gentle|hyper|sweep|off"
        ;;
esac
