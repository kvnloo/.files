#!/usr/bin/env bash
#
# Bit-Perfect Audio Verification Script
# Checks PipeWire configuration and sample rate matching for Topping DX5
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Device to monitor (Topping DX5)
DAC_NAME="alsa_output.usb-Topping_DX5"

echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   PipeWire Bit-Perfect Audio Verification${NC}"
echo -e "${CYAN}   Topping DX5 USB DAC${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check if PipeWire is running
echo -e "${BLUE}[1/5]${NC} Checking PipeWire services..."
if systemctl --user is-active --quiet pipewire; then
    echo -e "  ${GREEN}✓${NC} pipewire service is running"
else
    echo -e "  ${RED}✗${NC} pipewire service is NOT running"
    echo -e "  ${YELLOW}→${NC} Run: systemctl --user start pipewire"
    exit 1
fi

if systemctl --user is-active --quiet pipewire-pulse; then
    echo -e "  ${GREEN}✓${NC} pipewire-pulse service is running"
else
    echo -e "  ${RED}✗${NC} pipewire-pulse service is NOT running"
    echo -e "  ${YELLOW}→${NC} Run: systemctl --user start pipewire-pulse"
fi

if systemctl --user is-active --quiet wireplumber; then
    echo -e "  ${GREEN}✓${NC} wireplumber service is running"
else
    echo -e "  ${RED}✗${NC} wireplumber service is NOT running"
    echo -e "  ${YELLOW}→${NC} Run: systemctl --user start wireplumber"
    exit 1
fi

echo ""

# Check if configuration files are linked
echo -e "${BLUE}[2/5]${NC} Checking configuration files..."
if [ -f ~/.config/pipewire/pipewire.conf ]; then
    echo -e "  ${GREEN}✓${NC} pipewire.conf exists"
    if [ -L ~/.config/pipewire/pipewire.conf ]; then
        TARGET=$(readlink -f ~/.config/pipewire/pipewire.conf)
        echo -e "    ${CYAN}→${NC} Symlinked to: $TARGET"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} pipewire.conf not found in ~/.config/pipewire/"
fi

if [ -f ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua ]; then
    echo -e "  ${GREEN}✓${NC} DX5 WirePlumber config exists"
    if [ -L ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua ]; then
        TARGET=$(readlink -f ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua)
        echo -e "    ${CYAN}→${NC} Symlinked to: $TARGET"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} DX5 WirePlumber config not found"
fi

echo ""

# Check if DAC is detected
echo -e "${BLUE}[3/5]${NC} Detecting Topping DX5..."
if pw-cli list-objects | grep -q "$DAC_NAME"; then
    echo -e "  ${GREEN}✓${NC} Topping DX5 detected by PipeWire"

    # Get node ID
    NODE_ID=$(pw-cli list-objects | grep -B 5 "$DAC_NAME" | grep "id " | head -1 | awk '{print $2}' | tr -d ',')
    echo -e "    ${CYAN}→${NC} Node ID: $NODE_ID"
else
    echo -e "  ${RED}✗${NC} Topping DX5 NOT detected by PipeWire"
    echo -e "  ${YELLOW}→${NC} Check USB connection and run: aplay -l"
    exit 1
fi

echo ""

# Check supported sample rates
echo -e "${BLUE}[4/5]${NC} Checking supported sample rates..."
if [ -f /proc/asound/card0/stream0 ]; then
    SUPPORTED_RATES=$(grep "Rates:" /proc/asound/card0/stream0 | head -1 | sed 's/.*Rates: //')
    echo -e "  ${GREEN}✓${NC} Supported rates: ${CYAN}$SUPPORTED_RATES${NC}"
else
    echo -e "  ${YELLOW}⚠${NC} Could not read supported rates from ALSA"
fi

echo ""

# Check current playback state
echo -e "${BLUE}[5/5]${NC} Current playback status..."

# Get DAC info using pw-cli
DAC_INFO=$(pw-cli info "$NODE_ID" 2>/dev/null || echo "")

if [ -n "$DAC_INFO" ]; then
    # Extract current sample rate
    CURRENT_RATE=$(echo "$DAC_INFO" | grep "dsp.rate" | head -1 | awk '{print $3}')

    if [ -n "$CURRENT_RATE" ]; then
        echo -e "  ${GREEN}✓${NC} Current sample rate: ${CYAN}${CURRENT_RATE} Hz${NC}"

        # Provide interpretation
        case $CURRENT_RATE in
            44100)
                echo -e "    ${CYAN}→${NC} CD quality / Spotify / Most streaming music"
                ;;
            48000)
                echo -e "    ${CYAN}→${NC} DVD quality / YouTube / Video audio"
                ;;
            88200|176400)
                echo -e "    ${CYAN}→${NC} Hi-Res audio (CD family upsampled)"
                ;;
            96000|192000)
                echo -e "    ${CYAN}→${NC} Hi-Res audio (DVD family upsampled)"
                ;;
            352800|705600)
                echo -e "    ${CYAN}→${NC} Ultra Hi-Res PCM or DSD128/256 (CD family)"
                ;;
            384000|768000)
                echo -e "    ${CYAN}→${NC} Ultra Hi-Res PCM or DSD128/256 (DVD family)"
                ;;
        esac
    fi
fi

# Check for active streams
echo ""
echo -e "${CYAN}Active audio streams:${NC}"
pw-cli list-objects Node | grep -A 5 "media.class.*Stream" | grep "node.name" | sed 's/.*node.name = /  • /' | tr -d '"' || echo "  (no active streams)"

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Verification Complete!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Instructions
echo -e "${YELLOW}How to verify bit-perfect playback:${NC}"
echo ""
echo -e "1. ${CYAN}Run pw-top${NC} in another terminal"
echo -e "2. Find the row for ${CYAN}$DAC_NAME${NC}"
echo -e "3. Check the ${CYAN}RATE${NC} column:"
echo -e "   • Playing 44.1kHz file → Should show ${GREEN}44100${NC}"
echo -e "   • Playing 48kHz file → Should show ${GREEN}48000${NC}"
echo -e "   • Playing 96kHz file → Should show ${GREEN}96000${NC}"
echo -e "4. If RATE matches source = ${GREEN}BIT-PERFECT ✓${NC}"
echo ""
echo -e "${YELLOW}Test with different sources:${NC}"
echo -e "   • High Tide (44.1kHz FLAC)"
echo -e "   • Spotify (44.1kHz Ogg)"
echo -e "   • YouTube (48kHz AAC/Opus)"
echo -e "   • Hi-Res files (96/192/768kHz)"
echo ""
