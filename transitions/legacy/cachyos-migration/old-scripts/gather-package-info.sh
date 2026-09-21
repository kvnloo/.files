#!/bin/bash
# Package Information Gathering Script (no sudo required)
# Run this script: bash gather-package-info.sh

# Get script directory and set output path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_DIR="$SCRIPT_DIR/../docs/package-lists"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "=== Gathering Package Information ==="
echo "Output directory: $OUTPUT_DIR"
echo ""

# APT packages
echo "Gathering APT packages..."
dpkg --get-selections > "$OUTPUT_DIR/apt-packages.txt" 2>&1
apt list --installed > "$OUTPUT_DIR/apt-installed.txt" 2>&1
apt-mark showmanual > "$OUTPUT_DIR/apt-manual.txt" 2>&1

# Snap packages
if command -v snap &> /dev/null; then
    echo "Gathering Snap packages..."
    snap list > "$OUTPUT_DIR/snap-packages.txt" 2>&1
fi

# Flatpak packages
if command -v flatpak &> /dev/null; then
    echo "Gathering Flatpak packages..."
    flatpak list > "$OUTPUT_DIR/flatpak-packages.txt" 2>&1
fi

# Homebrew packages
if command -v brew &> /dev/null; then
    echo "Gathering Homebrew packages..."
    brew list > "$OUTPUT_DIR/brew-packages.txt" 2>&1
    brew list --cask > "$OUTPUT_DIR/brew-casks.txt" 2>&1
fi

# NPM global packages
if command -v npm &> /dev/null; then
    echo "Gathering NPM global packages..."
    npm list -g --depth=0 > "$OUTPUT_DIR/npm-global.txt" 2>&1
fi

# Pip packages
if command -v pip &> /dev/null; then
    echo "Gathering Pip packages..."
    pip list > "$OUTPUT_DIR/pip-packages.txt" 2>&1
    pip freeze > "$OUTPUT_DIR/pip-freeze.txt" 2>&1
fi

# Pip3 packages
if command -v pip3 &> /dev/null; then
    echo "Gathering Pip3 packages..."
    pip3 list > "$OUTPUT_DIR/pip3-packages.txt" 2>&1
    pip3 freeze > "$OUTPUT_DIR/pip3-freeze.txt" 2>&1
fi

# Pipx packages
if command -v pipx &> /dev/null; then
    echo "Gathering Pipx packages..."
    pipx list > "$OUTPUT_DIR/pipx-packages.txt" 2>&1
fi

# Cargo packages
if command -v cargo &> /dev/null; then
    echo "Gathering Cargo packages..."
    cargo install --list > "$OUTPUT_DIR/cargo-packages.txt" 2>&1
fi

# Gem packages
if command -v gem &> /dev/null; then
    echo "Gathering Gem packages..."
    gem list > "$OUTPUT_DIR/gem-packages.txt" 2>&1
fi

# Go packages
if command -v go &> /dev/null; then
    echo "Gathering Go packages..."
    go list -m all > "$OUTPUT_DIR/go-packages.txt" 2>&1
fi

echo ""
echo "✅ Package information gathered successfully!"
echo "Files created in: $OUTPUT_DIR/"
ls -lh "$OUTPUT_DIR/"
