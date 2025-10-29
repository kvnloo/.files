#!/usr/bin/env bash
#
# PipeWire Audio Configuration Installation Script
# Symlinks PipeWire and WirePlumber configurations from dotfiles
#

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Get script directory (dotfiles root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"

echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   PipeWire Bit-Perfect Audio Configuration Installer${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Create config directories
echo -e "${CYAN}Creating configuration directories...${NC}"
mkdir -p ~/.config/pipewire
mkdir -p ~/.config/wireplumber/main.lua.d
echo -e "  ${GREEN}✓${NC} Directories created"
echo ""

# Backup existing configs
echo -e "${CYAN}Backing up existing configurations...${NC}"
if [ -f ~/.config/pipewire/pipewire.conf ] && [ ! -L ~/.config/pipewire/pipewire.conf ]; then
    mv ~/.config/pipewire/pipewire.conf ~/.config/pipewire/pipewire.conf.backup
    echo -e "  ${YELLOW}→${NC} Backed up existing pipewire.conf"
fi

if [ -f ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua ] && [ ! -L ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua ]; then
    mv ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua \
       ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua.backup
    echo -e "  ${YELLOW}→${NC} Backed up existing DX5 config"
fi

if [ ! -f ~/.config/pipewire/pipewire.conf.backup ] && [ ! -f ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua.backup ]; then
    echo -e "  ${GREEN}✓${NC} No backups needed"
fi
echo ""

# Create symlinks
echo -e "${CYAN}Creating symlinks...${NC}"

# PipeWire config
if [ -L ~/.config/pipewire/pipewire.conf ]; then
    rm ~/.config/pipewire/pipewire.conf
fi
ln -sf "$CONFIG_DIR/pipewire/pipewire.conf" ~/.config/pipewire/pipewire.conf
echo -e "  ${GREEN}✓${NC} Linked pipewire.conf"
echo -e "    ${CYAN}→${NC} $CONFIG_DIR/pipewire/pipewire.conf"
echo -e "    ${CYAN}→${NC} ~/.config/pipewire/pipewire.conf"

# WirePlumber DX5 config
if [ -L ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua ]; then
    rm ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua
fi
ln -sf "$CONFIG_DIR/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua" \
       ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua
echo -e "  ${GREEN}✓${NC} Linked DX5 WirePlumber config"
echo -e "    ${CYAN}→${NC} $CONFIG_DIR/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua"
echo -e "    ${CYAN}→${NC} ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua"

echo ""

# Restart services
echo -e "${CYAN}Restarting PipeWire services...${NC}"
systemctl --user restart pipewire pipewire-pulse wireplumber
sleep 2

# Check status
if systemctl --user is-active --quiet pipewire && \
   systemctl --user is-active --quiet wireplumber; then
    echo -e "  ${GREEN}✓${NC} Services restarted successfully"
else
    echo -e "  ${YELLOW}⚠${NC} Some services may not be running. Check with:"
    echo -e "      systemctl --user status pipewire wireplumber"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   Installation Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo -e "1. Configure High Tide:"
echo -e "   • Settings → Audio Backend → Change from ${YELLOW}ALSA${NC} to ${GREEN}PipeWire/Automatic${NC}"
echo ""
echo -e "2. Verify bit-perfect playback:"
echo -e "   • Run: ${CYAN}$SCRIPT_DIR/scripts/verify-bitperfect-audio.sh${NC}"
echo -e "   • Or: ${CYAN}pw-top${NC} (check RATE column matches source)"
echo ""
echo -e "3. Test with different sources:"
echo -e "   • High Tide (44.1kHz FLAC)"
echo -e "   • Spotify (44.1kHz)"
echo -e "   • YouTube (48kHz)"
echo ""
echo -e "${CYAN}Documentation: $CONFIG_DIR/pipewire/README.md${NC}"
echo ""
