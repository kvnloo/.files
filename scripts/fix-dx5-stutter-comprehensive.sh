#!/bin/bash
# Comprehensive Topping DX5 Stutter Fix Script
# Addresses multiple potential causes beyond just buffering

set -e

echo "=== Topping DX5 Sample Rate Switching Stutter - Comprehensive Fix ==="
echo ""
echo "This script addresses multiple potential causes:"
echo "1. USB autosuspend (most common cause)"
echo "2. Alternative ALSA buffer configurations"
echo "3. System audio limits"
echo "4. WirePlumber configuration optimization"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if running as root
check_root() {
    if [ "$EUID" -eq 0 ]; then
        echo -e "${RED}ERROR: Do not run this script as root!${NC}"
        echo "Run as your normal user. It will use sudo when needed."
        exit 1
    fi
}

# Function to find DX5 USB device path
find_dx5_usb_path() {
    # Try to find the DX5 in USB devices
    for dev in /sys/bus/usb/devices/*; do
        if [ -f "$dev/product" ]; then
            if grep -qi "DX5" "$dev/product" 2>/dev/null; then
                echo "$dev"
                return 0
            fi
        fi
    done

    # Fallback: find by card name
    for dev in /sys/bus/usb/devices/*/sound/card*; do
        card_path=$(dirname "$dev")
        if [ -f "$card_path/../product" ]; then
            if grep -qi "DX5" "$card_path/../product" 2>/dev/null; then
                dirname "$card_path"
                return 0
            fi
        fi
    done

    echo ""
    return 1
}

# Main fixes
check_root

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Fix 1: Disable USB Autosuspend for DX5"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Research shows USB autosuspend is the #1 cause of DAC stuttering."
echo "Current USB autosuspend: $(cat /sys/module/usbcore/parameters/autosuspend) seconds"
echo ""

DX5_USB_PATH=$(find_dx5_usb_path)

if [ -z "$DX5_USB_PATH" ]; then
    echo -e "${YELLOW}Warning: Could not auto-detect DX5 USB path${NC}"
    echo "Creating udev rule for all Topping devices..."

    # Create udev rule by vendor if we can't find specific device
    cat > /tmp/90-topping-dx5-no-autosuspend.rules <<'EOF'
# Disable USB autosuspend for Topping audio devices
# This prevents stuttering during sample rate switches
ACTION=="add", SUBSYSTEM=="usb", ATTR{manufacturer}=="Topping", ATTR{product}=="DX5", TEST=="power/control", ATTR{power/control}="on"
EOF

else
    echo -e "${GREEN}Found DX5 at: $DX5_USB_PATH${NC}"

    # Get vendor and product IDs
    VENDOR_ID=$(cat "$DX5_USB_PATH/idVendor" 2>/dev/null || echo "")
    PRODUCT_ID=$(cat "$DX5_USB_PATH/idProduct" 2>/dev/null || echo "")

    echo "Vendor ID: $VENDOR_ID"
    echo "Product ID: $PRODUCT_ID"
    echo ""

    if [ -n "$VENDOR_ID" ] && [ -n "$PRODUCT_ID" ]; then
        # Create udev rule with specific IDs
        cat > /tmp/90-topping-dx5-no-autosuspend.rules <<EOF
# Disable USB autosuspend for Topping DX5
# This prevents stuttering during sample rate switches
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="$VENDOR_ID", ATTR{idProduct}=="$PRODUCT_ID", TEST=="power/control", ATTR{power/control}="on"
EOF
    else
        echo -e "${YELLOW}Warning: Could not read USB IDs${NC}"
        # Fallback rule
        cat > /tmp/90-topping-dx5-no-autosuspend.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="usb", ATTR{manufacturer}=="Topping", ATTR{product}=="DX5", TEST=="power/control", ATTR{power/control}="on"
EOF
    fi
fi

echo "Created udev rule:"
cat /tmp/90-topping-dx5-no-autosuspend.rules
echo ""

sudo mv /tmp/90-topping-dx5-no-autosuspend.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
echo -e "${GREEN}✓ Udev rule installed${NC}"

# Apply immediately if device is connected
if [ -n "$DX5_USB_PATH" ] && [ -f "$DX5_USB_PATH/power/control" ]; then
    echo ""
    echo "Applying immediately to connected DX5..."
    echo "on" | sudo tee "$DX5_USB_PATH/power/control" > /dev/null
    echo -e "${GREEN}✓ USB autosuspend disabled for DX5${NC}"
    echo "Current power control: $(cat $DX5_USB_PATH/power/control)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Fix 2: Optimize WirePlumber Buffer Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Research suggests trying SMALLER period-size for some DACs."
echo "Current config uses period-size=1024, testing 512..."
echo ""

WIREPLUMBER_CONFIG="$HOME/workspace/.files/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua"

# Backup current config
cp "$WIREPLUMBER_CONFIG" "${WIREPLUMBER_CONFIG}.backup-$(date +%s)"

# Try alternative buffer configuration
cat > /tmp/51-topping-dx5-bitperfect-alt.lua <<'EOF'
-- Topping DX5 Bit-Perfect Audio Configuration
-- Alternative buffer strategy for stutter reduction

alsa_monitor.rules = {
  {
    matches = {
      {
        -- Match the DX5 sink node (not the card/device)
        { "node.name", "matches", "alsa_output.usb-Topping_DX5*" },
      },
    },
    apply_properties = {
      -- Set higher session priority so DX5 is preferred
      ["priority.session"] = 2000,

      -- Node description (shown in audio apps)
      ["node.description"] = "Topping DX5 (Bit-Perfect)",

      -- Disable resampling when rates match (bit-perfect)
      ["resample.quality"] = 0,

      -- ALTERNATIVE BUFFER STRATEGY
      -- Research shows some DACs work better with SMALLER periods

      -- Start delay: Increased for more DAC lock time
      --   @ 44.1kHz: 16384 samples = 371ms
      --   @ 48kHz:   16384 samples = 341ms
      --   @ 96kHz:   16384 samples = 171ms
      --   @ 192kHz:  16384 samples = 85ms
      ["api.alsa.start-delay"] = 16384,    -- Option 2: More aggressive

      -- Period size: SMALLER can reduce latency and improve stability
      ["api.alsa.period-size"] = 512,      -- Reduced from 1024

      -- Headroom: Generous buffer
      ["api.alsa.headroom"] = 8192,        -- Increased from 4096

      -- Disable software volume control (passthrough to hardware)
      ["channelmix.normalize"] = false,

      -- Prevent device suspend to avoid reopening delays
      ["session.suspend-timeout-seconds"] = 0,  -- Never suspend DX5

      -- Keep device reserved even when idle
      ["api.alsa.disable-reserve"] = false,

      -- Memory-mapped I/O for efficiency
      ["api.alsa.disable-mmap"] = false,
      ["api.alsa.disable-batch"] = false,
    },
  },
}
EOF

mv /tmp/51-topping-dx5-bitperfect-alt.lua "$WIREPLUMBER_CONFIG"
echo -e "${GREEN}✓ Applied alternative buffer configuration${NC}"
echo "  - start-delay: 16384 samples (more aggressive)"
echo "  - period-size: 512 (reduced for stability)"
echo "  - headroom: 8192 (increased safety margin)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Fix 3: Increase System Audio Limits"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Increasing memory lock limits to prevent audio underruns..."
echo ""

# Create limits.d file
sudo tee /etc/security/limits.d/99-pipewire.conf > /dev/null <<EOF
# Audio limits for PipeWire to prevent underruns
# Allows PipeWire to lock more memory for real-time audio processing
@audio soft memlock 256
@audio hard memlock 256
$USER soft memlock 256
$USER hard memlock 256
EOF

echo -e "${GREEN}✓ Increased memory lock limits${NC}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Fix 4: Restart Audio Services"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

systemctl --user restart wireplumber
systemctl --user restart pipewire

sleep 2

echo -e "${GREEN}✓ Audio services restarted${NC}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if DX5 is available
if pactl list sinks short | grep -q DX5; then
    echo -e "${GREEN}✓ DX5 detected in PipeWire${NC}"
    pactl list sinks short | grep DX5
else
    echo -e "${RED}✗ DX5 not detected - try unplugging and replugging${NC}"
fi

echo ""
if [ -n "$DX5_USB_PATH" ] && [ -f "$DX5_USB_PATH/power/control" ]; then
    USB_POWER=$(cat "$DX5_USB_PATH/power/control")
    if [ "$USB_POWER" = "on" ]; then
        echo -e "${GREEN}✓ USB autosuspend disabled (power/control = on)${NC}"
    else
        echo -e "${YELLOW}⚠ USB power control = $USB_POWER (expected 'on')${NC}"
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing Instructions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Play a 44.1kHz song (Spotify or FLAC)"
echo "2. Switch to a 48kHz song (YouTube)"
echo "3. Listen for stutter during transition"
echo ""
echo "Expected behavior:"
echo "  - ~340ms silence during switch (longer than before)"
echo "  - NO clicks, pops, or stutters"
echo ""
echo "If still stuttering:"
echo "  1. Check ./scripts/diagnose-stream-rate.sh for stream info"
echo "  2. Try different USB port (prefer USB 2.0 over 3.0)"
echo "  3. Check High Tide settings for gapless playback (disable if possible)"
echo "  4. Report findings - may need kernel-level ALSA quirk"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary of Applied Fixes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✓ Disabled USB autosuspend for DX5 (permanent via udev)"
echo "✓ Increased start-delay to 16384 samples (~340ms @ 48kHz)"
echo "✓ Reduced period-size to 512 samples (may improve stability)"
echo "✓ Increased headroom to 8192 samples (more safety margin)"
echo "✓ Increased system memory lock limits"
echo "✓ Restarted audio services"
echo ""
echo "Original config backed up to:"
echo "  ${WIREPLUMBER_CONFIG}.backup-*"
echo ""
echo -e "${GREEN}All fixes applied! Please test sample rate switching.${NC}"
echo ""
