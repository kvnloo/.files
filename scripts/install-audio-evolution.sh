#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dropin="$HOME/.config/pipewire/pipewire.conf.d/11-aural-evolution.conf"
command="$HOME/.local/bin/audio-evolve"
validator="$HOME/.local/bin/audio-evolve-validate"

mkdir -p "${dropin%/*}" "${command%/*}"
ln -sfn "$root/config/pipewire/pipewire.conf.d/11-aural-evolution.conf" "$dropin"
ln -sfn "$root/scripts/audio-evolve" "$command"
ln -sfn "$root/scripts/audio-evolve-validate" "$validator"
chmod +x "$root/scripts/audio-evolve" "$root/scripts/audio-evolve-validate"
notify-send -u critical -t 5000 "Audio restart in 3 seconds" \
  "PipeWire will briefly interrupt Spotify, Plex, and other audio apps."
sleep 3
systemctl --user restart pipewire pipewire-pulse
sleep 1
"$command" doctor
"$command" activate
hyprctl reload >/dev/null 2>&1 || true
printf 'Installed Aural Evolution. Click the waveform bar button or run: audio-evolve\n'
