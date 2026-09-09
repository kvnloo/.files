#!/usr/bin/env bash
# NVIDIA Personal AI Router (PAIR) setup script for dotfiles
# Source: https://github.com/NVIDIA/Personal-AI-Router
set -euo pipefail

REPO="https://github.com/NVIDIA/Personal-AI-Router"

echo "PAIR: NVIDIA Personal AI Router (AI inference router, not Wi-Fi mesh)"
echo "Requires: RTX 20-series+, DGX Spark (GB10), Apple M4+, same LAN."
echo "Repo: $REPO"

if command -v pacman >/dev/null 2>&1; then
    echo "Arch/CachyOS detected (pacman)."
    echo "1) Check AUR: yay -S nvpair-bin  (if available)"
    echo "2) Otherwise build from source: git clone $REPO"
    echo "   cd Personal-AI-Router/desktop && npm install && npm start"
    echo "3) Or use the Linux binary from $REPO/releases"
fi

if command -v yay >/dev/null 2>&1; then
    echo "yay found — try: yay -S nvpair-bin"
fi

# Interactive: ask and run
read -rp "Do u want me to run the command? (y/N): " reply
if [[ "$reply" =~ ^[Yy]$ ]]; then
    echo "Running PAIR setup..."
    if command -v yay >/dev/null 2>&1; then
        yay -S nvpair-bin 2>/dev/null || echo "No AUR pkg (expected beta); using source/build fallback."
    fi
    if [[ ! -d "/tmp/PAIR" ]]; then
        echo "Cloning NVIDIA PAIR repo to /tmp/PAIR..."
        git clone https://github.com/NVIDIA/Personal-AI-Router /tmp/PAIR || echo "Clone failed (network/GitHub)."
    fi
    if [[ -f "/tmp/PAIR/README.md" ]]; then
        echo "Source at /tmp/PAIR. Build: cd /tmp/PAIR/desktop && npm install && npm start"
        echo "Also check GitHub releases for Linux .deb binary."
    fi
else
    echo "Skipped. Manual: yay -S nvpair-bin (if available) or build from source / download .deb from GitHub releases."
fi
