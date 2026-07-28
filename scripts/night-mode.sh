#!/usr/bin/env bash
# night-mode.sh — turn screens off and keep them off until explicitly woken.
# Usage: night-mode.sh on [--test]  |  off

STATE_FILE="/tmp/hypr-night-mode"
TEST_SECS=15

case "${1:-}" in
  on)
    [ -f "$STATE_FILE" ] && exit 0  # already in night mode
    touch "$STATE_FILE"

    # Stop hypridle so its on-resume handler won't auto-wake screens
    systemctl --user stop hypridle.service 2>/dev/null || pkill -x hypridle 2>/dev/null

    hyprctl dispatch dpms off

    # --test: auto-wake after $TEST_SECS seconds (for verifying screens stay off)
    if [ "${2:-}" = "--test" ]; then
      ( sleep "$TEST_SECS" && "$0" off ) &
    fi
    ;;
  off)
    hyprctl dispatch dpms on

    if [ -f "$STATE_FILE" ]; then
      rm -f "$STATE_FILE"
      # Restart hypridle for normal idle management
      systemctl --user start hypridle.service 2>/dev/null || hypridle &
    fi
    ;;
  *)
    echo "Usage: night-mode.sh on|off" >&2
    exit 1
    ;;
esac
