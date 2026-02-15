#!/usr/bin/env bash
set -euo pipefail

# Ubuntu -> CachyOS Pre-Migration Backup
# Run this ON UBUNTU before wiping the drive

BACKUP_DIR="${1:-/media/kvn/fast/cachyos-migration-backup}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_ROOT="$BACKUP_DIR/$TIMESTAMP"

echo "=== CachyOS Migration Backup ==="
echo "Backup destination: $BACKUP_ROOT"
echo ""

# Ensure backup drive is mounted and writable
if [[ ! -d "$(dirname "$BACKUP_DIR")" ]]; then
    echo "ERROR: Backup destination parent does not exist."
    echo "Mount your NVMe or external drive first."
    echo "Usage: $0 /path/to/backup/dir"
    exit 1
fi

mkdir -p "$BACKUP_ROOT"/{packages,configs,home-data,browser,app-data}

echo "[1/8] Exporting package lists..."
dpkg --get-selections > "$BACKUP_ROOT/packages/dpkg-selections.txt"
apt list --manual-installed 2>/dev/null | tail -n +2 > "$BACKUP_ROOT/packages/apt-manual.txt"
snap list 2>/dev/null > "$BACKUP_ROOT/packages/snap-list.txt" || true
flatpak list --app --columns=application,name,version 2>/dev/null > "$BACKUP_ROOT/packages/flatpak-list.txt" || true
pip list --user 2>/dev/null > "$BACKUP_ROOT/packages/pip-user.txt" || true
npm list -g --depth=0 2>/dev/null > "$BACKUP_ROOT/packages/npm-global.txt" || true
pipx list --json 2>/dev/null > "$BACKUP_ROOT/packages/pipx-list.json" || true
code --list-extensions 2>/dev/null > "$BACKUP_ROOT/packages/vscode-extensions.txt" || true

echo "[2/8] Backing up system configs..."
sudo cp -a /etc/sysctl.conf "$BACKUP_ROOT/configs/" 2>/dev/null || true
sudo cp -a /etc/sysctl.d/ "$BACKUP_ROOT/configs/sysctl.d/" 2>/dev/null || true
sudo cp -a /etc/security/limits.d/ "$BACKUP_ROOT/configs/limits.d/" 2>/dev/null || true
sudo cp -a /etc/modprobe.d/ "$BACKUP_ROOT/configs/modprobe.d/" 2>/dev/null || true
sudo cp -a /etc/fstab "$BACKUP_ROOT/configs/" 2>/dev/null || true
sudo cp -a /etc/hosts "$BACKUP_ROOT/configs/" 2>/dev/null || true
sudo cp -a /etc/default/grub "$BACKUP_ROOT/configs/" 2>/dev/null || true
sudo cp -a /etc/environment "$BACKUP_ROOT/configs/" 2>/dev/null || true
sudo cp -a /etc/NetworkManager/system-connections/ "$BACKUP_ROOT/configs/nm-connections/" 2>/dev/null || true

echo "[3/8] Backing up SSH and GPG keys..."
cp -a ~/.ssh "$BACKUP_ROOT/home-data/ssh/" 2>/dev/null || true
gpg --export-secret-keys --armor > "$BACKUP_ROOT/home-data/gpg-private-keys.asc" 2>/dev/null || true
gpg --export --armor > "$BACKUP_ROOT/home-data/gpg-public-keys.asc" 2>/dev/null || true
gpg --export-ownertrust > "$BACKUP_ROOT/home-data/gpg-ownertrust.txt" 2>/dev/null || true

echo "[4/8] Backing up browser profiles..."
# Firefox (snap stores profiles differently)
if [[ -d ~/snap/firefox/common/.mozilla/firefox ]]; then
    echo "  Firefox (snap)..."
    rsync -a --info=progress2 ~/snap/firefox/common/.mozilla/firefox/ "$BACKUP_ROOT/browser/firefox/" 2>/dev/null || true
elif [[ -d ~/.mozilla/firefox ]]; then
    echo "  Firefox (native)..."
    rsync -a --info=progress2 ~/.mozilla/firefox/ "$BACKUP_ROOT/browser/firefox/" 2>/dev/null || true
fi
# Chrome
if [[ -d ~/.config/google-chrome ]]; then
    echo "  Chrome..."
    rsync -a --info=progress2 \
        --exclude='Service Worker' --exclude='Cache' --exclude='Code Cache' \
        --exclude='GPUCache' --exclude='ShaderCache' --exclude='GrShaderCache' \
        ~/.config/google-chrome/ "$BACKUP_ROOT/browser/chrome/" 2>/dev/null || true
fi

echo "[5/8] Backing up application data..."
# Obsidian vaults
if [[ -d ~/snap/obsidian ]]; then
    echo "  Obsidian vault locations..."
    find ~/snap/obsidian -name ".obsidian" -type d 2>/dev/null | while read -r vault; do
        vault_dir=$(dirname "$vault")
        vault_name=$(basename "$vault_dir")
        echo "    Found vault: $vault_name"
        rsync -a --info=progress2 "$vault_dir/" "$BACKUP_ROOT/app-data/obsidian/$vault_name/" 2>/dev/null || true
    done
fi
# EasyEffects presets and IRs (legacy, but preserve)
if [[ -d ~/.config/easyeffects ]]; then
    echo "  EasyEffects..."
    cp -a ~/.config/easyeffects "$BACKUP_ROOT/app-data/easyeffects/" 2>/dev/null || true
fi
# Warp terminal prefs
if [[ -d ~/.config/warp-terminal ]]; then
    echo "  Warp Terminal..."
    cp -a ~/.config/warp-terminal "$BACKUP_ROOT/app-data/warp-terminal/" 2>/dev/null || true
fi
# Claude config
if [[ -d ~/.claude ]]; then
    echo "  Claude Code..."
    cp -a ~/.claude "$BACKUP_ROOT/app-data/claude/" 2>/dev/null || true
fi
# Tailscale state
echo "  Tailscale..."
sudo cp -a /var/lib/tailscale "$BACKUP_ROOT/app-data/tailscale/" 2>/dev/null || true

echo "[6/8] Backing up version managers..."
# NVM node versions list (don't copy binaries -- reinstall on CachyOS)
if [[ -d ~/.nvm ]]; then
    ls ~/.nvm/versions/node/ 2>/dev/null > "$BACKUP_ROOT/home-data/nvm-versions.txt" || true
fi
# Rustup toolchain list
rustup show 2>/dev/null > "$BACKUP_ROOT/home-data/rustup-show.txt" || true
# asdf plugins
if [[ -d ~/.asdf ]]; then
    asdf plugin list 2>/dev/null > "$BACKUP_ROOT/home-data/asdf-plugins.txt" || true
fi

echo "[7/8] Backing up user local data..."
# Local bin (Claude, uv, bun, etc.)
ls -la ~/.local/bin/ 2>/dev/null > "$BACKUP_ROOT/home-data/local-bin-listing.txt" || true
# Flatpak app data
flatpak list --app --columns=application 2>/dev/null | while read -r app; do
    echo "$app" >> "$BACKUP_ROOT/home-data/flatpak-apps.txt"
done 2>/dev/null || true

echo "[8/8] Computing backup size..."
du -sh "$BACKUP_ROOT" | cut -f1

echo ""
echo "=== Backup Complete ==="
echo "Location: $BACKUP_ROOT"
echo ""
echo "IMPORTANT: Verify backup before proceeding!"
echo "  ls -la $BACKUP_ROOT/"
echo "  ls -la $BACKUP_ROOT/home-data/ssh/"
echo "  wc -l $BACKUP_ROOT/packages/*.txt"
echo ""
echo "Next step: Commit dotfiles and push to remote"
echo "  cd ~/workspace/.files"
echo "  git add -A && git commit -m 'pre-cachyos migration' && git push origin dev"
