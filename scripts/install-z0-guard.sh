#!/usr/bin/env bash
set -euo pipefail

activate=false
case "${1:-}" in
  "") ;;
  --activate) activate=true ;;
  *) echo "Usage: $0 [--activate]" >&2; exit 2 ;;
esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
backend=${Z0INT_BACKEND_REPO:-/mnt/zer0models/z0-wt/bend-policy-laws}
current=$(dirname "$(readlink -f "$HOME/.local/bin/z0-guard" 2>/dev/null || echo /nonexistent/x)")
if backend_head=$(git -C "$backend" rev-parse HEAD 2>/dev/null); then
  pinned_src=
elif [[ -s "$current/backend-head" && -d "$current/src" ]]; then
  # Backend checkout reaped: ship script/unit updates on top of the already pinned backend copy.
  backend_head=$(<"$current/backend-head") pinned_src=$current/src
  echo "z0-guard: $backend missing; keeping installed backend $backend_head" >&2
else
  echo "z0-guard: backend $backend missing and no installed copy to keep (set Z0INT_BACKEND_REPO)" >&2
  exit 1
fi
# Content-stamped copies survive retirement of the source checkout.
read -r version _ < <({ cat "$repo/scripts/z0-guard" "$repo/scripts/worktree-reaper.py" "$repo/scripts/artifact-leases.py" \
  "$repo/config/systemd/user/worktree-reaper.service" \
  "$repo/config/systemd/user/worktree-reaper.timer"; printf '%s\n' "$backend_head"; } | sha256sum)
dest="$HOME/.local/lib/z0-guard/$version"
install -Dm755 "$repo/scripts/z0-guard" "$dest/z0-guard"
install -Dm755 "$repo/scripts/worktree-reaper.py" "$dest/worktree-reaper.py"
install -Dm755 "$repo/scripts/artifact-leases.py" "$dest/artifact-leases.py"
mkdir -p "$dest/src"
if [[ -z $pinned_src ]]; then
  git -C "$backend" archive "$backend_head" src | tar -x --strip-components=1 -C "$dest/src"
elif [[ $dest != "$current" ]]; then
  cp -a "$pinned_src/." "$dest/src/"
fi
printf '%s\n' "$backend_head" > "$dest/backend-head"
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
