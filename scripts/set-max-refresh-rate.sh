#!/bin/bash
# Set a monitor to its maximum available refresh rate
# Usage: set-max-refresh-rate.sh <display>
# Example: set-max-refresh-rate.sh DP-0

display="$1"

if [ -z "$display" ]; then
    echo "Usage: $0 <display>"
    echo "Example: $0 DP-0"
    exit 1
fi

# Check if display is connected
if ! xrandr | grep -q "^${display} connected"; then
    echo "Error: Display '$display' not found or not connected"
    exit 1
fi

# Extract just the block for this display
block=$(xrandr | sed -n "/^${display} connected/,/^[^ ]/p")

# Get the current/preferred mode (second line in the block)
mode=$(printf "%s\n" "$block" | sed -n '2p' | awk '{print $1}')

# Extract all refresh rates for this mode and find the maximum
rate=$(printf "%s\n" "$block" \
    | grep "^   ${mode}" \
    | head -n1 \
    | tr -s ' ' \
    | cut -d' ' -f2- \
    | tr ' ' '\n' \
    | sed 's/[+*]//g' \
    | grep -E '^[0-9]+(\.[0-9]+)?$' \
    | sort -rn \
    | head -n1)

# Apply the maximum refresh rate if found
if [ -n "$mode" ] && [ -n "$rate" ]; then
    xrandr --output "$display" --mode "$mode" --rate "$rate"
    echo "Set $display to ${mode}@${rate}Hz"
else
    echo "Error: Could not determine mode/rate for $display"
    exit 1
fi

