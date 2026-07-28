#!/usr/bin/env bash
# the-mono-truth — Mid/Side deconstruction
#
# Solo the center (mid) or stereo difference (side) signal to hear
# what lives where in a mix. Vocals, bass, kick live in mid;
# reverb, panned instruments live in side.
#
# Usage:
#   the-mono-truth.sh mid       Solo center/mono signal
#   the-mono-truth.sh side      Solo stereo difference signal
#   the-mono-truth.sh off       Restore normal stereo

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

case "${1:-mid}" in
    mid)
        echo "The Mono Truth: MID (center signal only)"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

# Replace the pipeline with: EQ -> mid extraction mixer -> compressor -> limiter
# Mid = (L+R)/2 to both channels
if 'mixers' not in config:
    config['mixers'] = {}

config['mixers']['mid_extract'] = {
    'channels': {'in': 2, 'out': 2},
    'mapping': [
        {
            'dest': 0,
            'sources': [
                {'channel': 0, 'gain': -6, 'inverted': False},
                {'channel': 1, 'gain': -6, 'inverted': False},
            ]
        },
        {
            'dest': 1,
            'sources': [
                {'channel': 0, 'gain': -6, 'inverted': False},
                {'channel': 1, 'gain': -6, 'inverted': False},
            ]
        },
    ]
}

# Insert mixer after EQ, before compressor/limiter
pipeline = config['pipeline']
# Find where EQ ends (after eq_r)
insert_idx = 0
for i, step in enumerate(pipeline):
    if step.get('type') == 'Filter' and 'eq_r' in step.get('names', []):
        insert_idx = i + 1
        break
pipeline.insert(insert_idx, {'type': 'Mixer', 'name': 'mid_extract'})

apply_config(config, f'Mid only ({profile} @ {rate}Hz)')
"
        ;;
    side)
        echo "The Mono Truth: SIDE (stereo difference only)"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import *

config, profile, rate = load_base_config()

if 'mixers' not in config:
    config['mixers'] = {}

# Side = (L-R)/2 to both channels
config['mixers']['side_extract'] = {
    'channels': {'in': 2, 'out': 2},
    'mapping': [
        {
            'dest': 0,
            'sources': [
                {'channel': 0, 'gain': -6, 'inverted': False},
                {'channel': 1, 'gain': -6, 'inverted': True},
            ]
        },
        {
            'dest': 1,
            'sources': [
                {'channel': 0, 'gain': -6, 'inverted': True},
                {'channel': 1, 'gain': -6, 'inverted': False},
            ]
        },
    ]
}

pipeline = config['pipeline']
insert_idx = 0
for i, step in enumerate(pipeline):
    if step.get('type') == 'Filter' and 'eq_r' in step.get('names', []):
        insert_idx = i + 1
        break
pipeline.insert(insert_idx, {'type': 'Mixer', 'name': 'side_extract'})

apply_config(config, f'Side only ({profile} @ {rate}Hz)')
"
        ;;
    off)
        echo "The Mono Truth: OFF (normal stereo)"
        "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from experience_helper import restore_base
restore_base()
"
        ;;
    *)
        echo "Usage: the-mono-truth.sh mid|side|off"
        ;;
esac
