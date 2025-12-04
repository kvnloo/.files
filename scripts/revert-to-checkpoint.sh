#!/bin/bash
# Revert all audio configuration to checkpoint b5c4dc4

set -euo pipefail

echo "=== Reverting All Audio Configuration to Checkpoint ==="
echo ""

# Remove system-level files created by comprehensive fix script
echo "1. Removing system-level configuration files..."

if [ -f /etc/udev/rules.d/90-topping-dx5-no-autosuspend.rules ]; then
    echo "  - Removing USB autosuspend udev rule..."
    sudo rm /etc/udev/rules.d/90-topping-dx5-no-autosuspend.rules
    sudo udevadm control --reload-rules
    echo "    ✓ Removed"
fi

if [ -L /etc/modprobe.d/snd-usb-audio.conf ]; then
    echo "  - Removing ALSA module config..."
    sudo rm /etc/modprobe.d/snd-usb-audio.conf
    echo "    ✓ Removed (will take effect after reboot)"
fi

if [ -f /etc/security/limits.d/99-pipewire.conf ]; then
    echo "  - Removing PipeWire memory limits..."
    sudo rm /etc/security/limits.d/99-pipewire.conf
    echo "    ✓ Removed"
fi

echo ""
echo "2. Removing untracked files from dotfiles..."
cd /home/kvn/workspace/.files

trash-put config/wireplumber/main.lua.d/52-dx5-force-quantum.lua 2>/dev/null || true
trash-put config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua.backup-* 2>/dev/null || true
trash-put config/modprobe.d/ 2>/dev/null || true

echo "  ✓ Cleaned up untracked config files"

echo ""
echo "3. Reverting modified files to checkpoint..."
git checkout HEAD -- config/zsh/aliases.zsh
git checkout HEAD -- scripts/install-audio-config.sh

echo "  ✓ Reverted git-tracked files"

echo ""
echo "4. Restarting audio services..."
systemctl --user restart wireplumber pipewire pipewire-pulse

echo ""
echo "✓ All configurations reverted to checkpoint b5c4dc4"
echo ""
echo "System is now in the same state as when everything was working."
echo ""
echo "NOTE: ALSA module changes require reboot to take effect."
echo "      USB autosuspend changes are effective immediately."
