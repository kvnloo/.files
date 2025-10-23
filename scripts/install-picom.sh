#!/bin/bash
# =====================================================
# Picom Installation Script for i3 Eye-Candy
# =====================================================

echo "🎨 Installing picom for enhanced i3 visuals..."

# Detect package manager and install picom
if command -v apt &> /dev/null; then
    echo "📦 Detected Debian/Ubuntu - installing via apt..."
    sudo apt update
    sudo apt install -y picom
elif command -v pacman &> /dev/null; then
    echo "📦 Detected Arch Linux - installing via pacman..."
    sudo pacman -S --noconfirm picom
elif command -v dnf &> /dev/null; then
    echo "📦 Detected Fedora - installing via dnf..."
    sudo dnf install -y picom
elif command -v yum &> /dev/null; then
    echo "📦 Detected RHEL/CentOS - installing via yum..."
    sudo yum install -y picom
else
    echo "❌ Could not detect package manager. Please install picom manually."
    exit 1
fi

# Verify installation
if command -v picom &> /dev/null; then
    echo "✅ Picom installed successfully!"
    picom --version

    echo ""
    echo "🔄 Restarting i3 to apply changes..."
    i3-msg restart

    echo ""
    echo "✨ All done! Your i3 setup now has:"
    echo "   • Visible bright borders on focused windows (blue)"
    echo "   • Smooth window animations (zoom, slide)"
    echo "   • Enhanced blur effects"
    echo "   • Rounded corners (12px)"
    echo "   • Subtle glow on focused windows"
    echo ""
    echo "💡 Tip: Press Mod+Shift+R to restart i3 if needed"
else
    echo "❌ Installation failed. Please install picom manually."
    exit 1
fi
