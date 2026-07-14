#!/usr/bin/env bash
set -euo pipefail

step=2
default_inner=18
default_outer=8
line=$(hyprctl getoption general:gaps_in | { IFS= read -r first; printf '%s' "$first"; })
current=${line#custom type: }
current=${current%% *}
[[ $current =~ ^[0-9]+$ ]] || current=$default_inner

case "${1:-}" in
  increase) inner=$((current + step)) ;;
  decrease) inner=$((current > step ? current - step : 0)) ;;
  reset) inner=$default_inner ;;
  *) printf 'usage: %s {increase|decrease|reset}\n' "${0##*/}" >&2; exit 2 ;;
esac

if (( inner == default_inner )); then
  outer=$default_outer
else
  outer=$((inner / 2))
fi

hyprctl keyword general:gaps_in "$inner" >/dev/null
hyprctl keyword general:gaps_out "$outer" >/dev/null
command -v notify-send >/dev/null 2>&1 && \
  notify-send -a hypr-gaps -h string:x-dunst-stack-tag:hypr-gaps \
    "Window gaps" "inner ${inner}px · outer ${outer}px"
