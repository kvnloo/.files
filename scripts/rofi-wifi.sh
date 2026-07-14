#!/usr/bin/env bash
set -euo pipefail

command -v nmcli >/dev/null 2>&1 || exit 1
command -v rofi >/dev/null 2>&1 || exit 1

[[ $(nmcli radio wifi) == enabled ]] || nmcli radio wifi on

# Use NetworkManager's cached scan so the menu opens immediately. Collapse
# repeated access points for the same SSID, retaining the active or strongest.
declare -A best_signal=()
declare -A best_security=()
declare -A is_active=()
while IFS=: read -r active signal security ssid; do
  [[ -n $ssid ]] || continue
  if [[ -z ${best_signal[$ssid]+x} || $active == '*' || $signal -gt ${best_signal[$ssid]} ]]; then
    best_signal[$ssid]=$signal
    best_security[$ssid]=$security
  fi
  [[ $active == '*' ]] && is_active[$ssid]=1
done < <(nmcli -t --escape no -f IN-USE,SIGNAL,SECURITY,SSID device wifi list --rescan no)

ranked=''
for ssid in "${!best_signal[@]}"; do
  printf -v row '%03d\t%s\n' "${best_signal[$ssid]}" "$ssid"
  ranked+=$row
done

rows=''
while IFS=$'\t' read -r signal ssid; do
  [[ -n $ssid ]] || continue
  marker='  '
  [[ -n ${is_active[$ssid]+x} ]] && marker='● '
  lock=''
  [[ ${best_security[$ssid]} != '--' && -n ${best_security[$ssid]} ]] && lock='  󰌾'
  printf -v row '%s%s  ·  %d%%%s\t%s\n' "$marker" "$ssid" "$((10#$signal))" "$lock" "$ssid"
  rows+=$row
done < <(printf '%s' "$ranked" | sort -t $'\t' -k1,1nr)

[[ -n $rows ]] || {
  notify-send -u normal 'Wi-Fi' 'No cached networks found'
  exit 0
}

selection=$(printf '%s' "$rows" | rofi -dmenu -i -monitor -1 -p 'Wi-Fi networks' -display-columns 1) || exit 0
ssid=${selection#*$'\t'}
[[ -n $ssid ]] || exit 0

if nmcli device wifi connect "$ssid" >/dev/null 2>&1; then
  notify-send -u low 'Wi-Fi connected' "$ssid"
  exit 0
fi

password=$(printf '' | rofi -dmenu -password -p "Password for $ssid") || exit 0
if nmcli device wifi connect "$ssid" password "$password" >/dev/null 2>&1; then
  notify-send -u low 'Wi-Fi connected' "$ssid"
else
  notify-send -u critical 'Wi-Fi connection failed' "$ssid"
  exit 1
fi
