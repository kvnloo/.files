#!/usr/bin/env bash
# Show current sample rate of the Topping DX5 DAC

node_info=$(pw-cli info $(pw-cli ls Node 2>/dev/null | grep -B1 "Topping_DX5" | head -1 | awk '{print $2}') 2>/dev/null)

if [[ -z "$node_info" ]]; then
    echo "DAC off"
    exit 0
fi

rate=$(echo "$node_info" | grep -oP 'format\.dsp.*?rate:\s*\K[0-9]+' 2>/dev/null)

if [[ -z "$rate" ]]; then
    # Fallback: read from the ALSA device directly
    rate=$(cat /proc/asound/DX5/stream0 2>/dev/null | grep -oP 'Rate: \K[0-9]+' | tail -1)
fi

if [[ -z "$rate" ]]; then
    echo "--"
    exit 0
fi

# Format: 44.1k, 48k, 96k, 192k, etc.
if (( rate >= 1000 )); then
    if (( rate % 1000 == 0 )); then
        echo "$(( rate / 1000 ))k"
    else
        printf "%.1fk\n" "$(echo "scale=1; $rate / 1000" | bc)"
    fi
else
    echo "${rate}Hz"
fi
