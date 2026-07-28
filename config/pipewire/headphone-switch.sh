#!/bin/bash
# Switch between Headphone DSP sinks and EQ profiles
#
# Spatial mode (instant, no restart needed — just pause/unpause player):
#   headphone-switch.sh clean        # no spatial processing
#   headphone-switch.sh crossfeed    # bs2b crossfeed
#   headphone-switch.sh room         # BRIR room simulation
#   headphone-switch.sh movie        # 7.1/5.1 movie fold-down + EQ
#
# EQ profile (requires PipeWire restart):
#   headphone-switch.sh eq monarch   # Monarch MKII IRs
#   headphone-switch.sh eq hd800s    # HD800S IRs
#
# Show status:
#   headphone-switch.sh              # show current config

AUTOEQ_DIR="/home/kvn/workspace/.files/config/autoeq"

set_sink() {
    local pattern="$1" label="$2"
    id=$(pw-cli ls Node 2>/dev/null | grep -B5 "$pattern" | grep -oP 'id \K\d+' | head -1)
    if [ -n "$id" ]; then
        wpctl set-default "$id"
        echo "Switched to: $label (sink $id)"
    else
        echo "Error: $label sink not found"
        exit 1
    fi
}

set_eq() {
    local profile="$1"
    case "$profile" in
        monarch|mkii)
            for rate in 44100 48000 96000 192000 384000; do
                ln -sf "ThieAudio Monarch MKII minimum phase ${rate}Hz.wav" "$AUTOEQ_DIR/active_${rate}Hz.wav"
            done
            echo "EQ profile: Monarch MKII (IEF Preference 2025 + Harman IE 2019)"
            ;;
        hd800s|hd800)
            for rate in 44100 48000 96000 192000 384000; do
                ln -sf "Sennheiser HD800 minimum phase ${rate} Hz.wav" "$AUTOEQ_DIR/active_${rate}Hz.wav"
            done
            echo "EQ profile: Sennheiser HD800S (IEF Preference 2025 + Harman OE 2018)"
            ;;
        *)
            echo "Unknown EQ profile: $profile"
            echo "Available: monarch, hd800s"
            exit 1
            ;;
    esac
    echo "Restarting PipeWire..."
    systemctl --user restart pipewire
    sleep 1
    echo "Done. Pause/unpause your player to reconnect."
}

case "$1" in
    clean)
        set_sink 'effect_input.headphone_dsp' "Headphone DSP (clean)"
        ;;
    crossfeed|xfeed|bs2b)
        set_sink 'effect_input.headphone_dsp_crossfeed' "Headphone DSP + Crossfeed (bs2b)"
        ;;
    room|brir)
        set_sink 'effect_input.headphone_dsp_room' "Headphone DSP + Room (BRIR)"
        ;;
    movie|film|cinema)
        set_sink 'effect_input.headphone_dsp_movie' "Headphone DSP Movie (7.1/5.1 fold-down)"
        ;;
    eq)
        if [ -z "$2" ]; then
            echo "Usage: $0 eq [monarch|hd800s]"
            exit 1
        fi
        set_eq "$2"
        ;;
    *)
        echo "Headphone DSP Status"
        echo "===================="
        echo ""
        echo "Sinks:"
        wpctl status 2>/dev/null | grep -E "effect_input\.headphone"
        echo ""
        echo "Active EQ profile:"
        target=$(readlink "$AUTOEQ_DIR/active_44100Hz.wav" 2>/dev/null)
        case "$target" in
            *Monarch*) echo "  Monarch MKII" ;;
            *HD800*)   echo "  Sennheiser HD800S" ;;
            *)         echo "  Unknown ($target)" ;;
        esac
        echo ""
        echo "Commands:"
        echo "  $0 clean      → EQ only (no spatial)"
        echo "  $0 crossfeed  → EQ + bs2b crossfeed"
        echo "  $0 room       → EQ + BRIR room sim"
        echo "  $0 movie      → 7.1/5.1 fold-down + EQ for Plex/movies"
        echo "  $0 eq monarch → Switch to Monarch MKII EQ"
        echo "  $0 eq hd800s  → Switch to HD800S EQ"
        ;;
esac
