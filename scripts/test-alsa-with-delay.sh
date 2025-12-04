#!/bin/bash
# Test if adding explicit delay before audio helps

echo "=== Testing ALSA with Explicit Pre-Delay ==="
echo ""
echo "This test adds a manual delay after rate switch to see if that helps."
echo ""

# Ensure test files exist
if [ ! -f /tmp/test-44100.wav ] || [ ! -f /tmp/test-48000.wav ]; then
    echo "Generating test files..."
    ffmpeg -f lavfi -i "sine=frequency=1000:duration=0.1" -ar 44100 /tmp/test-44100.wav -y 2>/dev/null
    ffmpeg -f lavfi -i "sine=frequency=2000:duration=0.1" -ar 48000 /tmp/test-48000.wav -y 2>/dev/null
fi

echo "Test files ready (100ms beeps)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 1: Standard playback (your previous test)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Playing 44.1kHz beep..."
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-44100.wav 2>/dev/null

sleep 1
echo ""
echo "Playing 48kHz beep (rate switch - expect NOTHING)..."
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-48000.wav 2>/dev/null

sleep 1
echo ""
echo "Replaying 48kHz beep (no rate switch - expect FULL beep)..."
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-48000.wav 2>/dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Test 1 complete. You should have heard:"
echo "  - Step 1 (44.1kHz): NOTHING or very faint"
echo "  - Step 2 (48kHz switch): NOTHING"
echo "  - Step 3 (48kHz replay): FULL beep"
echo ""
read -p "Press Enter to continue to Test 2 (with delay workaround)..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 2: With 500ms pre-delay after rate switch"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Playing 44.1kHz beep to reset rate..."
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-44100.wav 2>/dev/null

sleep 2
echo ""
echo "Triggering rate switch to 48kHz (opening device)..."
# Open the device and trigger rate switch but don't play yet
aplay -D plughw:CARD=DX5,DEV=0 --duration=0 /tmp/test-48000.wav 2>/dev/null &
APLAY_PID=$!

echo "Waiting 500ms for DAC to lock..."
sleep 0.5

# Kill the dummy aplay if still running
kill $APLAY_PID 2>/dev/null
wait $APLAY_PID 2>/dev/null

echo "Now playing 48kHz beep - do you hear it?"
aplay -D plughw:CARD=DX5,DEV=0 /tmp/test-48000.wav 2>/dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Analysis:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Test 1 shows the problem (nothing on rate switch)"
echo "Test 2 tries to work around it by waiting 500ms after triggering switch"
echo ""
echo "Did you hear the beep in Test 2 after the 500ms delay?"
echo ""
echo "  YES → Delay workaround might work (but impractical for music)"
echo "  NO → This is a fundamental ALSA/DX5 firmware limitation"
echo ""
