#!/bin/bash
# EasyEffects IR Auto-Switcher Daemon (PipeWire version)
# Monitors sample rate changes and switches to matching IR file
#
# Usage:
#   easyeffects-ir-switcher.sh [command]
#   Commands: monitor, status, hd800s, monarch
#
# Config file: ~/.config/easyeffects-ir-switcher/config

set -euo pipefail

# Paths
EE_IRS_DIR="$HOME/.config/easyeffects/irs"
EE_OUTPUT_DIR="$HOME/.config/easyeffects/output"
CONFIG_DIR="$HOME/.config/easyeffects-ir-switcher"
CONFIG_FILE="$CONFIG_DIR/config"

# IR file patterns (without sample rate)
declare -A IR_PATTERNS
IR_PATTERNS[hd800s]="Sennheiser HD800 minimum phase"
IR_PATTERNS[monarch]="ThieAudio Monarch MKII minimum phase"

# Sample rate suffixes
declare -A RATE_SUFFIXES
RATE_SUFFIXES[44100]="44100 Hz"
RATE_SUFFIXES[48000]="48000 Hz"
RATE_SUFFIXES[96000]="96000 Hz"
RATE_SUFFIXES[192000]="192000 Hz"
RATE_SUFFIXES[384000]="384000 Hz"

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

# Get current sample rate from PipeWire
get_sample_rate() {
    pw-cli info all 2>/dev/null | grep -A20 "node.name.*DX5" | grep "audio.rate" | head -1 | grep -oE '[0-9]+' || \
    pactl list sinks 2>/dev/null | grep -A10 "DX5" | grep "Sample Specification" | grep -oE '[0-9]+Hz' | grep -oE '[0-9]+' || \
    echo "48000"
}

# Get IR file path for headphone and sample rate
get_ir_path() {
    local headphone="$1"
    local rate="$2"
    local pattern="${IR_PATTERNS[$headphone]}"
    local suffix

    if [[ "$headphone" == "monarch" ]]; then
        suffix="${RATE_SUFFIXES_MONARCH[$rate]:-${RATE_SUFFIXES[$rate]:-48000 Hz}}"
    else
        suffix="${RATE_SUFFIXES[$rate]:-48000 Hz}"
    fi

    local ir_file="$EE_IRS_DIR/${pattern} ${suffix}.irs"

    if [[ -f "$ir_file" ]]; then
        echo "$ir_file"
    else
        # Fallback to 48000 or 44100
        for fallback in 48000 44100; do
            if [[ "$headphone" == "monarch" ]]; then
                suffix="${RATE_SUFFIXES_MONARCH[$fallback]}"
            else
                suffix="${RATE_SUFFIXES[$fallback]}"
            fi
            ir_file="$EE_IRS_DIR/${pattern} ${suffix}.irs"
            if [[ -f "$ir_file" ]]; then
                echo "$ir_file"
                return
            fi
        done
        # Last resort - return first matching IR
        find "$EE_IRS_DIR" -name "${pattern}*.irs" 2>/dev/null | head -1
    fi
}

# Update EasyEffects convolver IR via gsettings
set_ir() {
    local ir_path="$1"
    local skip_restart="${2:-false}"

    if [[ ! -f "$ir_path" ]]; then
        echo "ERROR: IR file not found: $ir_path" >&2
        return 1
    fi

    echo "$(date '+%H:%M:%S') Set IR: $(basename "$ir_path")"

    # Update via gsettings (EasyEffects native method)
    gsettings set com.github.wwmm.easyeffects.convolver kernel-path "$ir_path" 2>/dev/null || true

    # Also update the preset files for persistence
    local preset_file
    if [[ "$HEADPHONE" == "hd800s" ]]; then
        preset_file="$EE_OUTPUT_DIR/audiophile-hd800s.json"
    else
        preset_file="$EE_OUTPUT_DIR/audiophile-monarch.json"
    fi

    if [[ -f "$preset_file" ]]; then
        # Update kernel-path in preset JSON
        sed -i "s|\"kernel-path\": \"[^\"]*\"|\"kernel-path\": \"$ir_path\"|" "$preset_file"
    fi

    # Signal EasyEffects to reload (if running)
    if pgrep -x easyeffects >/dev/null 2>&1; then
        if [[ "$skip_restart" != "true" ]]; then
            # Send SIGHUP to reload config, or restart if needed
            pkill -HUP easyeffects 2>/dev/null || true
        fi
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

    # Load the corresponding preset
    local preset_name
    if [[ "$HEADPHONE" == "hd800s" ]]; then
        preset_name="audiophile-hd800s"
    else
        preset_name="audiophile-monarch"
    fi

    easyeffects --load-preset "$preset_name" 2>/dev/null || true
}

# Monitor mode - watch for sample rate changes
monitor() {
    echo "EasyEffects IR Switcher - Monitoring mode (PipeWire)"
    echo "Headphone: $HEADPHONE"
    echo "---"

    local last_rate=""
    local first_run=true

    while true; do
        local current_rate=$(get_sample_rate)

        if [[ "$current_rate" != "$last_rate" && -n "$current_rate" ]]; then
            echo "$(date '+%H:%M:%S') Sample rate changed: ${last_rate:-none} -> ${current_rate}Hz"
            local ir_path=$(get_ir_path "$HEADPHONE" "$current_rate")
            if [[ -n "$ir_path" ]]; then
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
    echo "=== EasyEffects IR Switcher Status ==="
    echo "Current headphone: $HEADPHONE"
    echo "Current sample rate: $(get_sample_rate)Hz"
    echo ""
    echo "EasyEffects running: $(pgrep -x easyeffects >/dev/null && echo "YES" || echo "NO")"
    echo ""
    echo "Available IRs:"
    ls -1 "$EE_IRS_DIR"/*.irs 2>/dev/null | xargs -I{} basename {} | sed 's/^/  /'
    echo ""
    echo "Available presets:"
    ls -1 "$EE_OUTPUT_DIR"/*.json 2>/dev/null | xargs -I{} basename {} .json | sed 's/^/  /'
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
