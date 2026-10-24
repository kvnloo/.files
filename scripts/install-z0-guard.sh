#!/usr/bin/env bash
set -euo pipefail

activate=false
case "${1:-}" in
  "") ;;
  --activate) activate=true ;;
  *) echo "Usage: $0 [--activate]" >&2; exit 2 ;;
esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
# Content-stamped copies survive retirement of the source checkout.
read -r version _ < <(cat "$repo/scripts/z0-guard" "$repo/scripts/worktree-reaper.py" \
  "$repo/config/systemd/user/worktree-reaper.service" \
  "$repo/config/systemd/user/worktree-reaper.timer" | sha256sum)
dest="$HOME/.local/lib/z0-guard/$version"
install -Dm755 "$repo/scripts/z0-guard" "$dest/z0-guard"
install -Dm755 "$repo/scripts/worktree-reaper.py" "$dest/worktree-reaper.py"
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
ln -sfn "$dest/z0-guard" "$HOME/.local/bin/z0-guard"
ln -sfn "$dest/worktree-reaper.py" "$HOME/.local/bin/worktree-reaper"
for unit in worktree-reaper.service worktree-reaper.timer; do
  install -Dm644 "$repo/config/systemd/user/$unit" "$dest/$unit"
  ln -sfn "$dest/$unit" "$HOME/.config/systemd/user/$unit"
done
wants="$HOME/.config/systemd/user/timers.target.wants/worktree-reaper.timer"
if [[ -L "$wants" || -e "$wants" ]]; then
  ln -sfn "$dest/worktree-reaper.timer" "$wants"
fi
printf 'Installed z0-guard version %s at %s\n' "$version" "$dest"
if $activate; then
  systemctl --user daemon-reload
  systemctl --user enable --now worktree-reaper.timer
fi
