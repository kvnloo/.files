#!/usr/bin/env bash
# Install CamillaDSP configuration on macOS
#
# This script:
# 1. Symlinks config files to ~/.config/camilladsp/
# 2. Generates per-rate config variants
# 3. Creates state/log directories
# 4. Installs launchd service (optional)
# 5. Sets BlackHole 2ch as system output
#
# Prerequisites:
#   - BlackHole 2ch installed: brew install --cask blackhole-2ch
#   - CamillaDSP binary at ~/.local/bin/camilladsp
#   - SwitchAudioSource: brew install switchaudio-osx

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CDSP_CONFIG="$CONFIG_HOME/camilladsp"

echo "=== CamillaDSP macOS Installer ==="
echo ""

# Step 1: Create config directory and symlinks
echo "[1/5] Symlinking configuration..."
mkdir -p "$CDSP_CONFIG"

# Symlink the entire config directory contents
for f in "$SCRIPT_DIR"/*.yml "$SCRIPT_DIR"/*.sh; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f")"
    ln -sf "$f" "$CDSP_CONFIG/$name"
    echo "  → $name"
done

# Symlink coefficients directory
ln -sfn "$SCRIPT_DIR/coeffs" "$CDSP_CONFIG/coeffs"
echo "  → coeffs/"

# Step 2: Generate per-rate configs
echo ""
echo "[2/5] Generating per-rate configs..."
chmod +x "$SCRIPT_DIR/generate-rate-configs.sh"
"$SCRIPT_DIR/generate-rate-configs.sh"

# Symlink generated configs
ln -sfn "$SCRIPT_DIR/configs" "$CDSP_CONFIG/configs"

# Step 3: Create state/log directories
echo ""
echo "[3/5] Creating state/log directories..."
mkdir -p "$HOME/.local/share/camilladsp"
echo "  → ~/.local/share/camilladsp/"

# Step 4: Make scripts executable
echo ""
echo "[4/5] Setting permissions..."
chmod +x "$SCRIPT_DIR/headphone-switch.sh"
echo "  → headphone-switch.sh"

# Step 5: Verify prerequisites
echo ""
echo "[5/5] Checking prerequisites..."

if command -v camilladsp &>/dev/null; then
    echo "  ✓ CamillaDSP $(camilladsp --version 2>&1)"
else
    echo "  ✗ CamillaDSP not found in PATH"
fi

if SwitchAudioSource -a 2>/dev/null | grep -q "BlackHole"; then
    echo "  ✓ BlackHole 2ch detected"
else
    echo "  ✗ BlackHole 2ch not detected — install with: brew install --cask blackhole-2ch"
fi

if command -v SwitchAudioSource &>/dev/null; then
    echo "  ✓ SwitchAudioSource installed"
else
    echo "  ✗ SwitchAudioSource not found"
fi

# Validate a config
echo ""
echo "Validating config..."
if camilladsp -c "$CDSP_CONFIG/configs/camilladsp-96000.yml" 2>&1; then
    echo "  ✓ Config validation passed"
else
    echo "  ✗ Config validation failed (expected if BlackHole not yet installed)"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "  1. Install BlackHole (requires sudo):"
echo "     brew install --cask blackhole-2ch"
echo "  2. Reboot (required for BlackHole audio driver)"
echo "  3. Set system output to BlackHole 2ch:"
echo "     SwitchAudioSource -s 'BlackHole 2ch'"
echo "  4. Start CamillaDSP:"
echo "     camilladsp -p 1234 ~/.config/camilladsp/configs/camilladsp-96000.yml"
echo "  5. (Optional) Install launchd service for auto-start:"
echo "     cp $SCRIPT_DIR/com.camilladsp.daemon.plist ~/Library/LaunchAgents/"
echo "     launchctl load ~/Library/LaunchAgents/com.camilladsp.daemon.plist"
echo ""
echo "Profile switching:"
echo "  ~/.config/camilladsp/headphone-switch.sh clean      # EQ only"
echo "  ~/.config/camilladsp/headphone-switch.sh crossfeed  # EQ + crossfeed"
echo "  ~/.config/camilladsp/headphone-switch.sh room       # EQ + BRIR room"
echo "  ~/.config/camilladsp/headphone-switch.sh eq hd800s  # Switch headphone EQ"
echo "  ~/.config/camilladsp/headphone-switch.sh status     # Show current state"
