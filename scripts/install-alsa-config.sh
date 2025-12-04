#!/bin/bash
# Install ALSA module configuration for USB audio optimization

set -e

echo "=== Installing ALSA USB Audio Configuration ==="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "ERROR: Do not run this script as root!"
    echo "Run as your normal user. It will use sudo when needed."
    exit 1
fi

CONFIG_FILE="/home/kvn/workspace/.files/config/modprobe.d/snd-usb-audio.conf"
DEST="/etc/modprobe.d/snd-usb-audio.conf"

echo "Source: $CONFIG_FILE"
echo "Destination: $DEST"
echo ""

# Create symlink
if [ -f "$DEST" ]; then
    echo "Backing up existing configuration..."
    sudo mv "$DEST" "${DEST}.backup-$(date +%s)"
fi

echo "Creating symlink..."
sudo ln -sf "$CONFIG_FILE" "$DEST"

echo "✓ Configuration installed"
echo ""

# Show current loaded module parameters
echo "Current snd-usb-audio module parameters:"
if lsmod | grep -q snd_usb_audio; then
    echo "  Module is loaded"
    if [ -d /sys/module/snd_usb_audio/parameters ]; then
        for param in /sys/module/snd_usb_audio/parameters/*; do
            param_name=$(basename "$param")
            param_value=$(cat "$param" 2>/dev/null || echo "N/A")
            echo "  $param_name = $param_value"
        done
    fi
else
    echo "  Module is NOT loaded (will apply on next modprobe)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "To apply the new configuration, you have two options:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Option 1: Reload the module (requires closing all audio apps first)"
echo "  1. Close High Tide, browsers, and any apps using audio"
echo "  2. Run: sudo rmmod snd_usb_audio && sudo modprobe snd_usb_audio"
echo "  3. Reconnect to DX5 if needed"
echo ""
echo "Option 2: Reboot (easier, applies cleanly)"
echo "  1. Save your work"
echo "  2. Run: sudo reboot"
echo ""
echo "After applying, verify the parameters loaded correctly by running:"
echo "  cat /sys/module/snd_usb_audio/parameters/use_vmalloc"
echo "  cat /sys/module/snd_usb_audio/parameters/delayed_register"
echo ""
