#!/usr/bin/env bash
# the-soundstage-experience — cycle through CamillaDSP spatial profiles
#
# Usage:
#   the-soundstage-experience.sh              # default: 5s interval, 30s duration
#   the-soundstage-experience.sh 3 60         # 3s interval, 60s duration

set -euo pipefail

INTERVAL="${1:-5}"
DURATION="${2:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWITCH="$SCRIPT_DIR/headphone-switch.sh"
PROFILES=(clean crossfeed room)
LABELS=("Clean" "Crossfeed (bs2b)" "BRIR Room")

elapsed=0
i=0

echo "🎧 the-soundstage-experience"
echo "   ${INTERVAL}s per profile · ${DURATION}s total"
echo ""

while (( elapsed < DURATION )); do
    idx=$(( i % ${#PROFILES[@]} ))
    profile="${PROFILES[$idx]}"
    label="${LABELS[$idx]}"

    echo "$(date '+%H:%M:%S')  ▸ ${label}"
    bash "$SWITCH" "$profile" > /dev/null 2>&1

    sleep "$INTERVAL"
    elapsed=$(( elapsed + INTERVAL ))
    i=$(( i + 1 ))
done

echo ""
echo "Done — ended on: ${LABELS[$(( (i - 1) % ${#PROFILES[@]} ))]}"
