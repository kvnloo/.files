#!/bin/bash
# Real-time PipeWire stream rate diagnostic tool
# This helps diagnose why certain formats (like AAC) might not trigger proper sample rate switching

echo "=== PipeWire Stream Rate Diagnostic ==="
echo ""
echo "This will monitor PipeWire streams and DAC sample rate in real-time."
echo "Play your AAC 96kHz track and watch the output below."
echo ""
echo "Press Ctrl+C to stop monitoring."
echo ""
echo "========================================"
echo ""

# Function to get current DAC sample rate
get_dac_rate() {
    cat /proc/asound/card0/stream0 2>/dev/null | grep "Momentary freq" | awk '{print $4}' | head -1
}

# Function to get PipeWire sink rate
get_sink_rate() {
    pactl list sinks short | grep DX5 | awk '{print $5}'
}

# Function to get active stream information
get_stream_info() {
    pw-cli list-objects Node | grep -A 20 "media.class = \"Stream/Output/Audio\"" | grep -E "node.name|audio.rate|format.dsp"
}

# Main monitoring loop
while true; do
    clear
    echo "=== PipeWire Stream Rate Diagnostic ==="
    echo ""
    echo "Time: $(date +%H:%M:%S)"
    echo ""

    # DAC hardware rate
    dac_rate=$(get_dac_rate)
    if [ -n "$dac_rate" ]; then
        echo "📡 DAC Hardware Rate: $dac_rate"
    else
        echo "📡 DAC Hardware Rate: IDLE/NO PLAYBACK"
    fi

    # PipeWire sink rate
    sink_rate=$(get_sink_rate)
    echo "🔧 PipeWire Sink Configuration: $sink_rate"
    echo ""

    # Active streams
    echo "🎵 Active PipeWire Streams:"
    echo "----------------------------"
    pw-cli list-objects Node 2>/dev/null | awk '
        /media.class = "Stream\/Output\/Audio"/ { in_stream=1; stream_count++ }
        in_stream && /node.name/ {
            gsub(/"/, "", $3)
            printf "  Stream %d: %s\n", stream_count, $3
        }
        in_stream && /format.dsp/ {
            match($0, /F32.*Hz/)
            if (RSTART > 0) {
                rate = substr($0, RSTART, RLENGTH)
                printf "    Format: %s\n", rate
            }
        }
        in_stream && /media.name/ {
            gsub(/"/, "", $3)
            printf "    Playing: %s\n", $3
        }
        in_stream && /}/ { in_stream=0; printf "\n" }
    '

    # Analysis
    echo ""
    echo "🔍 Analysis:"
    if [ -n "$dac_rate" ]; then
        # Extract just the number from sink_rate (e.g., "96000Hz" -> "96000")
        sink_hz=$(echo "$sink_rate" | grep -o '[0-9]*Hz' | grep -o '[0-9]*')

        # Compare rates
        if [ "$dac_rate" == "$sink_hz" ]; then
            echo "  ✅ DAC and PipeWire rates MATCH - bit-perfect"
        else
            echo "  ⚠️  DAC rate ($dac_rate) != PipeWire rate ($sink_hz)"
            echo "      This indicates RESAMPLING is occurring!"
        fi
    fi

    echo ""
    echo "💡 Tips:"
    echo "  - If AAC 96kHz shows as 48kHz here, High Tide is decoding at 48kHz"
    echo "  - If stream shows 96kHz but DAC shows different, PipeWire is resampling"
    echo "  - Check 'format.dsp' line for the actual sample rate High Tide outputs"
    echo ""
    echo "Press Ctrl+C to stop monitoring..."

    sleep 1
done
