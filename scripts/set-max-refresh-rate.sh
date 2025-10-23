#!/bin/bash
# Automatically detect connected monitors and set each to maximum available refresh rate

xrandr | grep " connected" | awk '{print $1}' | while read display; do
    # Get the current/preferred mode (resolution)
    mode=$(xrandr | grep -A1 "^${display} connected" | tail -n1 | awk '{print $1}')

    # Extract all refresh rates for this mode and find the maximum
    rate=$(xrandr | grep "^   ${mode}" | head -n1 | tr -s ' ' | cut -d' ' -f2- | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+$' | sort -rn | head -n1)

    # Apply the maximum refresh rate if found
    if [ -n "$rate" ]; then
        xrandr --output "$display" --mode "$mode" --rate "$rate"
    fi
done
