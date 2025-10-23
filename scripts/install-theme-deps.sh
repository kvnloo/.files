#!/usr/bin/env bash
# Install dependencies for pywal theming system

echo "Installing theme dependencies..."

# Install feh (wallpaper setter)
sudo apt-get update
sudo apt-get install -y feh

# Re-generate pywal theme with wallpaper setting enabled
wal -i ~/workspace/UX/background/2800x1800/xerus.png --backend colorthief

echo "✅ Theme dependencies installed!"
echo "Run 'i3-msg reload' to apply changes"
