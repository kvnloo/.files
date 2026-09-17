#!/usr/bin/env bash
set -euo pipefail
repo="${DOTFILES_REPO:-$HOME/workspace/.files}"
overlay="$repo/config/noctalia/overlays/codexbar-meter"
dest_dir="${NOCTALIA_CODEXBAR_METER_DIR:-$HOME/.local/state/noctalia/plugins/materialized/community/codexbar-meter}"
mkdir -p "$dest_dir"
install -m 0644 "$overlay/bar_widget.luau" "$dest_dir/bar_widget.luau"
if [[ -f "$overlay/panel.luau" ]]; then
  install -m 0644 "$overlay/panel.luau" "$dest_dir/panel.luau"
fi
if [[ -f "$overlay/plugin.toml" ]]; then
  install -m 0644 "$overlay/plugin.toml" "$dest_dir/plugin.toml"
fi
echo "Installed CodexBar meter overlay -> $dest_dir"
# Community plugin rematerialize can restore upstream bar_widget.luau on fetch.
# Re-run this script after `noctalia msg plugins update` or a plugin source sync.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
noctalia msg config-reload 2>/dev/null || echo "Run: noctalia msg config-reload"
