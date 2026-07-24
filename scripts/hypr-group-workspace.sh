#!/usr/bin/env bash
set -euo pipefail

command -v hyprctl >/dev/null 2>&1 || exit 1
command -v jq >/dev/null 2>&1 || exit 1

workspace=$(hyprctl -j activeworkspace | jq -r '.id')
monitor=$(hyprctl -j monitors | jq -r '.[] | select(.focused) | .id')
active=$(hyprctl -j activewindow | jq -r '.address')

clients() {
  hyprctl -j clients | jq --argjson workspace "$workspace" --argjson monitor "$monitor" '
    [.[] | select(
      .workspace.id == $workspace and
      .monitor == $monitor and
      .mapped == true and
      .floating == false
    ) | {address, grouped, at, size}]'
}

snapshot=$(clients)
count=$(jq 'length' <<<"$snapshot")
(( count > 1 )) || {
  notify-send -a hyprland "Window groups" "Only one tiled window is on this workspace" 2>/dev/null || true
  exit 0
}

anchor=$(jq -r 'sort_by(.grouped | length) | last.address' <<<"$snapshot")
if (( $(jq --arg anchor "$anchor" '[.[] | select(.address == $anchor)][0].grouped | length' <<<"$snapshot") == 0 )); then
  anchor=$active
  hyprctl dispatch focuswindow "address:$anchor" >/dev/null
  hyprctl dispatch togglegroup >/dev/null
fi

# Always absorb the nearest remaining tiled window. That keeps the target
# group adjacent as the layout collapses after every successful move.
for ((attempt = 0; attempt < count * 2; attempt++)); do
  snapshot=$(clients)
  anchor=$(jq -r 'sort_by(.grouped | length) | last.address' <<<"$snapshot")
  anchor_group=$(jq --arg anchor "$anchor" '
    ([.[] | select(.address == $anchor)][0]) as $g |
    if ($g.grouped | length) > 0 then $g.grouped else [$anchor] end' <<<"$snapshot")
  remaining=$(jq --argjson group "$anchor_group" '
    [.[] | select(.address as $a | ($group | index($a) | not))]' <<<"$snapshot")
  (( $(jq 'length' <<<"$remaining") > 0 )) || break

  target=$(jq --arg anchor "$anchor" --argjson group "$anchor_group" '
    ([.[] | select(.address == $anchor)][0]) as $g |
    ($g.at[0] + $g.size[0] / 2) as $gx |
    ($g.at[1] + $g.size[1] / 2) as $gy |
    [.[] | select(.address as $a | ($group | index($a) | not)) |
      . + {distance: (((.at[0] + .size[0] / 2) - $gx) | fabs) + (((.at[1] + .size[1] / 2) - $gy) | fabs)}] |
    sort_by(.distance) | .[0]' <<<"$snapshot")

  address=$(jq -r '.address' <<<"$target")
  direction=$(jq -r --arg anchor "$anchor" --arg address "$address" '
    ([.[] | select(.address == $anchor)][0]) as $g |
    ([.[] | select(.address == $address)][0]) as $w |
    (($g.at[0] + $g.size[0] / 2) - ($w.at[0] + $w.size[0] / 2)) as $dx |
    (($g.at[1] + $g.size[1] / 2) - ($w.at[1] + $w.size[1] / 2)) as $dy |
    if (($dx | fabs) >= ($dy | fabs)) then (if $dx < 0 then "l" else "r" end)
    else (if $dy < 0 then "u" else "d" end) end' <<<"$snapshot")

  hyprctl dispatch focuswindow "address:$address" >/dev/null
  hyprctl dispatch moveintogroup "$direction" >/dev/null
done

hyprctl dispatch focuswindow "address:$active" >/dev/null
final=$(clients)
grouped=$(jq --arg anchor "$anchor" '[.[] | select(.address == $anchor)][0].grouped | length' <<<"$final")
if (( grouped == count )); then
  notify-send -a hyprland "Window groups" "Grouped $count tiled windows on workspace $workspace" 2>/dev/null || true
  exit 0
fi

notify-send -u critical -a hyprland "Window groups" "Grouped $grouped of $count tiled windows" 2>/dev/null || true
exit 1
