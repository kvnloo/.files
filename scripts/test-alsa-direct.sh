#!/bin/bash
# Test if the audio dropout is High Tide specific or ALSA-level issue
# Uses very short, distinctive sounds to detect if beginning is cut off

echo "=== Testing ALSA Direct Playback (bypassing High Tide) ==="
echo ""
echo "This will play VERY SHORT clicks/beeps to test if beginning is cut off."
echo ""

# Generate test files - very short and distinctive
if [ ! -f /tmp/test-44100.wav ]; then
    echo "Generating 44.1kHz test file (100ms beep)..."
    # Create 100ms beep at 1000Hz
    ffmpeg -f lavfi -i "sine=frequency=1000:duration=0.1" -ar 44100 /tmp/test-44100.wav -y 2>/dev/null
fi

if [ ! -f /tmp/test-48000.wav ]; then
    echo "Generating 48kHz test file (100ms beep)..."
    # Create 100ms beep at 2000Hz (one octave higher, more distinctive)
    ffmpeg -f lavfi -i "sine=frequency=2000:duration=0.1" -ar 48000 /tmp/test-48000.wav -y 2>/dev/null
fi

echo ""
echo "Test files ready:"
echo "  - 44.1kHz: 100ms beep at 1000Hz (low pitch)"
echo "  - 48kHz:   100ms beep at 2000Hz (high pitch)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test Procedure:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Playing 44.1kHz beep (low pitch)..."
echo "   Listen: Should hear FULL 100ms beep starting immediately"
echo ""

sleep 1
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-44100.wav

echo ""
echo "2. Now playing 48kHz beep (HIGH pitch - requires rate switch)..."
echo "   Listen: Is the beep SHORTER or does it start with a click/pop?"
echo "   This is the critical test!"
echo ""

sleep 1
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-48000.wav

echo ""
echo "3. Replaying 48kHz beep (no rate switch)..."
echo "   Listen: Should hear FULL beep now (compare to step 2)"
echo ""

sleep 1
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-48000.wav

echo ""
echo "4. One more 48kHz beep for comparison..."
echo ""

sleep 1
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-48000.wav

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Analysis:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Compare step 2 (first 48kHz) vs step 3 & 4 (replayed 48kHz):"
echo ""
echo "  A) Step 2 sounds SHORTER/QUIETER → Beginning was cut off (ALSA-level issue)"
echo "  B) Step 2 sounds SAME as step 3 & 4 → No dropout (High Tide issue only)"
echo "  C) Step 2 has click/pop but full length → Stutter not dropout"
echo ""
echo "The 100ms beeps should be very short and distinctive."
echo "If step 2 is cut off, you'll clearly hear it's shorter than step 3 & 4."
echo ""
echo "Please report what you heard!"
echo ""
