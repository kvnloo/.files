#!/usr/bin/env bash
#
# Check if PipeWire has control of Topping DX5
#

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   Topping DX5 Device Status Check${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check ALSA device status
echo -e "${CYAN}[1] ALSA Device Status:${NC}"
if [ -f /proc/asound/card0/pcm0p/sub0/status ]; then
    STATUS=$(cat /proc/asound/card0/pcm0p/sub0/status)
    echo -e "  Device state: ${YELLOW}$STATUS${NC}"

    if [ "$STATUS" = "closed" ]; then
        echo -e "  ${GREEN}✓${NC} Device is available (not in use)"
    else
        echo -e "  ${YELLOW}→${NC} Device is currently: $STATUS"
    fi
else
    echo -e "  ${RED}✗${NC} Cannot read device status"
fi
echo ""

# Check which process has the device
echo -e "${CYAN}[2] Process Using Device:${NC}"
PROCESSES=$(fuser /dev/snd/pcmC0D0p 2>&1 || echo "none")
if [ "$PROCESSES" = "none" ]; then
    echo -e "  ${YELLOW}→${NC} No process currently has exclusive lock"
else
    echo -e "  Process IDs: ${YELLOW}$PROCESSES${NC}"
    # Get process names
    for pid in $PROCESSES; do
        if [ -d "/proc/$pid" ]; then
            PNAME=$(cat /proc/$pid/comm 2>/dev/null || echo "unknown")
            echo -e "    • PID $pid: ${CYAN}$PNAME${NC}"
        fi
    done
fi
echo ""

# Check PipeWire node status
echo -e "${CYAN}[3] PipeWire Node Status:${NC}"
NODE_INFO=$(pw-cli list-objects | grep -A 15 "usb-Topping_DX5" || echo "")
if [ -n "$NODE_INFO" ]; then
    echo -e "  ${GREEN}✓${NC} DX5 registered with PipeWire"

    # Extract node ID
    NODE_ID=$(echo "$NODE_INFO" | grep "id " | head -1 | awk '{print $2}' | tr -d ',')
    echo -e "  Node ID: ${CYAN}$NODE_ID${NC}"

    # Get node state
    NODE_STATE=$(pw-cli info "$NODE_ID" 2>/dev/null | grep "state" | head -1 | awk '{print $3}' | tr -d '"' || echo "unknown")
    echo -e "  Node state: ${CYAN}$NODE_STATE${NC}"

    # Check if it's the default sink
    DEFAULT_SINK=$(pactl info | grep "Default Sink" | awk '{print $3}')
    if echo "$DEFAULT_SINK" | grep -q "DX5"; then
        echo -e "  ${GREEN}✓${NC} DX5 is the default audio output"
    else
        echo -e "  ${YELLOW}→${NC} Default sink: $DEFAULT_SINK"
    fi
else
    echo -e "  ${RED}✗${NC} DX5 not found in PipeWire"
fi
echo ""

# Check if audio is currently playing
echo -e "${CYAN}[4] Active Audio Streams:${NC}"
STREAMS=$(pw-cli list-objects Node | grep -B 3 "media.class.*Stream" | grep "node.name" | wc -l)
if [ "$STREAMS" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} $STREAMS active stream(s)"
    pw-cli list-objects Node | grep -A 5 "media.class.*Stream" | grep "node.name" | sed 's/.*node.name = /  • /' | tr -d '"'
else
    echo -e "  ${YELLOW}→${NC} No active streams (nothing playing)"
fi
echo ""

# Summary
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Summary:${NC}"
echo ""

if [ "$STATUS" = "closed" ] && [ -n "$NODE_INFO" ]; then
    echo -e "${GREEN}✓ PipeWire has control available${NC}"
    echo -e "  • Device is registered with PipeWire"
    echo -e "  • No exclusive ALSA lock"
    echo -e "  • Ready for audio playback"
elif [ "$STATUS" = "running" ]; then
    echo -e "${YELLOW}⚡ Device is currently active${NC}"
    echo -e "  • Audio is being played or device is open"
    echo -e "  • This is normal during playback"
else
    echo -e "${RED}⚠ Unexpected state${NC}"
    echo -e "  • Check if High Tide is in ALSA exclusive mode"
    echo -e "  • Restart PipeWire services if needed"
fi
echo ""
