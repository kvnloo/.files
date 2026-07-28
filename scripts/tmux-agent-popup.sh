#!/usr/bin/env bash
set -euo pipefail

mode=${1:-fleet}
working_directory=${2:-$HOME}
client_tty=${3:-}
export TMUX_AGENT_FLEET_CLIENT=$client_tty

# tmux is a user service and can outlive the current Hyprland session. Import
# only the display variables needed by a fresh graphical client.
while IFS='=' read -r name value; do
  case "$name" in
    DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|HYPRLAND_INSTANCE_SIGNATURE)
      export "$name=$value"
      ;;
  esac
done < <(systemctl --user show-environment)

# The popup is a separate terminal, not a nested tmux client. Plain tmux calls
# inside the fleet selector still connect to the user's default server.
unset TMUX TMUX_PANE

selector=${AGENT_FLEET_SCRIPT:-$HOME/.tmux/plugins/tmux-agent-fleet/scripts/fleet.sh}
[[ -x $selector ]] || selector=$HOME/workspace/.files/scripts/tmux-fleet-switcher.sh

case "$mode" in
  fleet)
    exec alacritty \
      --class agent-fleet-popup,agent-fleet-popup \
      --option window.dimensions.columns=170 \
      --option window.dimensions.lines=39 \
      --working-directory "$working_directory" \
      -e "$selector"
    ;;
  deck)
    exec alacritty \
      --class agent-deck-popup,agent-deck-popup \
      --option window.dimensions.columns=170 \
      --option window.dimensions.lines=39 \
      --working-directory "$working_directory" \
      -e agent-deck
    ;;
  *)
    printf 'usage: %s {fleet|deck} [working-directory]\n' "${0##*/}" >&2
    exit 2
    ;;
esac
