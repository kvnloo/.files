#!/bin/bash
# PulseEffects IR Auto-Switcher Daemon
# Monitors sample rate changes and switches to matching IR file
#
# Usage:
#   pulseeffects-ir-switcher.sh [headphone]
#   headphone: "hd800s" or "monarch" (default: monarch)
#
# Config file: ~/.config/pulseeffects-ir-switcher/config
#   HEADPHONE=monarch  (or hd800s)

set -euo pipefail

# Paths
PE_IRS_DIR="$HOME/.var/app/com.github.wwmm.pulseeffects/config/PulseEffects/irs"
KEYFILE="$HOME/.var/app/com.github.wwmm.pulseeffects/config/glib-2.0/settings/keyfile"
CONFIG_DIR="$HOME/.config/pulseeffects-ir-switcher"
CONFIG_FILE="$CONFIG_DIR/config"
SINK_NAME="alsa_output.usb-Topping_DX5-00.analog-stereo"

# IR file patterns (without sample rate)
declare -A IR_PATTERNS
IR_PATTERNS[hd800s]="Sennheiser HD800 minimum phase"
IR_PATTERNS[monarch]="ThieAudio Monarch MKII minimum phase"

# Sample rate suffixes (PulseAudio alternate rates)
declare -A RATE_SUFFIXES
RATE_SUFFIXES[44100]="44100 Hz"
RATE_SUFFIXES[48000]="48000 Hz"
RATE_SUFFIXES[96000]="96000 Hz"
RATE_SUFFIXES[192000]="192000 Hz"

# Monarch files have different naming (no space before Hz)
declare -A RATE_SUFFIXES_MONARCH
RATE_SUFFIXES_MONARCH[44100]="44100Hz"
RATE_SUFFIXES_MONARCH[48000]="48000Hz"

# Load config
load_config() {
    mkdir -p "$CONFIG_DIR"
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
    fi
    HEADPHONE="${HEADPHONE:-monarch}"
}

# Save config
save_config() {
    echo "HEADPHONE=$HEADPHONE" > "$CONFIG_FILE"
}

# Get current sample rate
get_sample_rate() {
    pactl list sinks | grep -A5 "Name: $SINK_NAME" | grep "Sample Specification" | grep -oE '[0-9]+Hz' | grep -oE '[0-9]+'
}

# Get IR file path for headphone and sample rate
get_ir_path() {
    local headphone="$1"
    local rate="$2"
    local pattern="${IR_PATTERNS[$headphone]}"
    local suffix

    if [[ "$headphone" == "monarch" ]]; then
        suffix="${RATE_SUFFIXES_MONARCH[$rate]:-${RATE_SUFFIXES[$rate]}}"
    else
        suffix="${RATE_SUFFIXES[$rate]}"
    fi

    local ir_file="$PE_IRS_DIR/${pattern} ${suffix}.irs"

    if [[ -f "$ir_file" ]]; then
        echo "$ir_file"
    else
        # Fallback to 44100 or 48000
        for fallback in 44100 48000; do
            if [[ "$headphone" == "monarch" ]]; then
                suffix="${RATE_SUFFIXES_MONARCH[$fallback]}"
            else
                suffix="${RATE_SUFFIXES[$fallback]}"
            fi
            ir_file="$PE_IRS_DIR/${pattern} ${suffix}.irs"
            if [[ -f "$ir_file" ]]; then
                echo "$ir_file"
                return
            fi
        done
    fi
}

# Update PulseEffects convolver IR
set_ir() {
    local ir_path="$1"
    local skip_restart="${2:-false}"

    if [[ ! -f "$ir_path" ]]; then
        echo "ERROR: IR file not found: $ir_path" >&2
        return 1
    fi

    # Update keyfile
    sed -i "s|^kernel-path=.*|kernel-path='$ir_path'|" "$KEYFILE"

    echo "$(date '+%H:%M:%S') Set IR: $(basename "$ir_path")"

    # Restart PulseEffects to pick up change (unless skip_restart)
    if [[ "$skip_restart" != "true" ]]; then
        # Gracefully restart PulseEffects
        pkill -15 -f "pulseeffects --gapplication-service" 2>/dev/null || true
        sleep 1
        nohup flatpak run com.github.wwmm.pulseeffects --gapplication-service &>/dev/null &
        disown
        sleep 2
    fi
}

# Switch headphone profile
switch_headphone() {
    local new_headphone="$1"

    if [[ -z "${IR_PATTERNS[$new_headphone]:-}" ]]; then
        echo "Unknown headphone: $new_headphone"
        echo "Available: ${!IR_PATTERNS[*]}"
        return 1
    fi

    HEADPHONE="$new_headphone"
    save_config

    local rate=$(get_sample_rate)
    local ir_path=$(get_ir_path "$HEADPHONE" "$rate")

    echo "Switched to $HEADPHONE at ${rate}Hz"
    set_ir "$ir_path"
}

# Monitor mode - watch for sample rate changes
monitor() {
    echo "PulseEffects IR Switcher - Monitoring mode"
    echo "Headphone: $HEADPHONE"
    echo "Sink: $SINK_NAME"
    echo "---"

    local last_rate=""
    local first_run=true

    while true; do
        local current_rate=$(get_sample_rate)

        if [[ "$current_rate" != "$last_rate" && -n "$current_rate" ]]; then
            echo "$(date '+%H:%M:%S') Sample rate changed: ${last_rate:-none} -> ${current_rate}Hz"
            local ir_path=$(get_ir_path "$HEADPHONE" "$current_rate")
            if [[ -n "$ir_path" ]]; then
                # Skip restart on first run (initial detection)
                if [[ "$first_run" == "true" ]]; then
                    set_ir "$ir_path" "true"
                    first_run=false
                else
                    set_ir "$ir_path"
                fi
            fi
            last_rate="$current_rate"
        fi

        sleep 2
    done
}

# Show status
status() {
    load_config
    echo "Current headphone: $HEADPHONE"
    echo "Current sample rate: $(get_sample_rate)Hz"
    echo "Current IR: $(grep kernel-path "$KEYFILE" | cut -d= -f2)"
    echo ""
    echo "Available IRs:"
    ls -1 "$PE_IRS_DIR"/*.irs 2>/dev/null | xargs -I{} basename {} | sed 's/^/  /'
}

# Main
load_config

case "${1:-monitor}" in
    monitor|--monitor|-m)
        monitor
        ;;
    switch|--switch|-s)
        switch_headphone "${2:-}"
        ;;
    hd800s|monarch)
        switch_headphone "$1"
        ;;
    status|--status)
        status
        ;;
    *)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  monitor        Watch for sample rate changes (default)"
        echo "  status         Show current configuration"
        echo "  hd800s         Switch to HD 800 S profile"
        echo "  monarch        Switch to Monarch MKII profile"
        echo "  switch <name>  Switch to named headphone profile"
        ;;
esac
