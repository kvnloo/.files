#!/bin/bash
# Set each connected monitor to the maximum available refresh rate
# at its preferred/current resolution

xrandr | grep " connected" | awk '{print $1}' | while read -r display; do
    # Extract just the block for this display
    block=$(xrandr | sed -n "/^${display} connected/,/^[^ ]/p")

    # Get the current/preferred mode (second line in the block)
    mode=$(printf "%s\n" "$block" | sed -n '2p' | awk '{print $1}')

    # Extract all refresh rates for this mode within this block and find the maximum
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
    fi
done

