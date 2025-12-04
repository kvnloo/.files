# Audio Dropout During Sample Rate Switch - Analysis

## Problem Confirmed

**Symptoms:**
- First notes of song are LOST when DAC switches sample rates
- Replaying same song (no rate switch) → first notes play correctly
- Happens with ALSA, PipeWire, and Automatic backends in High Tide
- Doesn't happen in Spotify (all 44.1kHz, no switching)

**This is NOT:**
- Clicks/pops/crackles (audio quality issue)
- Stuttering (intermittent dropouts)
- This is: **Initial audio loss at start of rate switch**

---

## Why start-delay Isn't Fixing It

### What start-delay Should Do

```
Rate switch occurs
    ↓
start-delay = 16384 samples of SILENCE buffered
    ↓
DAC locks to new rate during silence
    ↓
Real audio starts AFTER delay
    ↓
All notes play correctly
```

### What's Actually Happening

```
Rate switch occurs
    ↓
Audio starts IMMEDIATELY (or too soon)
    ↓
DAC not ready yet
    ↓
First 16384 samples DROPPED
    ↓
Audio continues after DAC locks
    ↓
Missing first notes
```

---

## Potential Root Causes

### 1. start-delay Not Being Applied

**Check:**
```bash
pw-cli info <sink-id> | grep start-delay
```

**If not present:** WirePlumber rule not matching or applying correctly

### 2. High Tide Bypassing PipeWire Buffering

**Possible:** High Tide might be using direct ALSA access even in "PipeWire" mode, bypassing PipeWire's buffering layer.

**Evidence:** Problem occurs in ALSA mode too (same behavior)

### 3. ALSA Driver Ignoring start-delay

**Possible:** The DX5's ASYNC endpoint mode might not respect start-delay parameter correctly.

**Technical:** DX5 uses async endpoint with separate sync endpoint (from `/proc/asound/card0/stream0`)

### 4. Quantum Too Small

**Current:** PipeWire quantum = 1024 samples
- At 48kHz: 1024 samples = 21ms
- At 44.1kHz: 1024 samples = 23ms

**Problem:** Even if start-delay buffers silence, PipeWire might send the FIRST quantum (1024 samples with real audio) before the DAC is ready, causing dropout.

---

## Solutions to Try

### Solution 1: Verify Parameters Applied

```bash
# Check if our WirePlumber config is loaded
systemctl --user status wireplumber | grep -i dx5

# Check sink properties
pw-dump | grep -A 50 "alsa_output.usb-Topping_DX5" | grep -E "start-delay|period-size|headroom"
```

**If not applied:** WirePlumber configuration issue

### Solution 2: Force PipeWire to Insert Silence

Instead of relying on ALSA's start-delay, we can try forcing PipeWire to actually generate and send silence before audio.

**Create `/etc/pipewire/pipewire.conf.d/99-dx5-pre-roll.conf`:**
```
# Not implemented yet - need to research PipeWire filter module
```

### Solution 3: Increase PipeWire Quantum

Force larger processing chunks so first audio chunk arrives later:

```bash
# Set global quantum higher
pw-metadata -n settings 0 clock.force-quantum 2048
```

**Effect:** 2048 samples @ 48kHz = 42ms per chunk (vs 21ms)

**Trade-off:** Higher latency, but might give DAC more time

### Solution 4: Add Pre-Roll Filter

Use PipeWire's filter-chain to insert actual silence before streams:

```lua
-- filter.chain configuration
-- Insert 1 second of silence at stream start
```

### Solution 5: High Tide Configuration

Check if High Tide has any relevant settings:
- Buffer size
- Pre-buffer amount
- Device initialization delay
- Gapless playback (disable if present)

---

## Testing Plan

### Test 1: Verify Parameters

```bash
# Check what parameters are actually applied
pw-dump | jq '.[] | select(.info.props["node.name"] | contains("Topping_DX5"))'
```

### Test 2: Increase Quantum

```bash
# Force larger quantum globally
pw-metadata -n settings 0 clock.force-quantum 2048

# Restart High Tide and test
```

### Test 3: Different App

```bash
# Test with different application to isolate High Tide
# Use Firefox → YouTube (48kHz) → Spotify web (44.1kHz)
# Does same dropout occur?
```

### Test 4: ALSA Exclusive Mode Deep Dive

Since problem occurs even in ALSA mode, try:
```bash
# Use aplay directly to test if it's ALSA-level issue
aplay -D hw:CARD=DX5,DEV=0 test-44100.wav
# Then immediately
aplay -D hw:CARD=DX5,DEV=0 test-48000.wav
# Does first note of 48kHz file play?
```

---

## Alternative Hypothesis

**What if the "dropout" IS the silence buffer?**

With `start-delay = 16384`:
- @ 44.1kHz: 371ms of silence
- @ 48kHz: 341ms of silence

**Question:** Is the "dropout" actually this silence period, and you're just not hearing the music start during that time?

**Test:**
1. Play 44.1kHz song
2. Switch to 48kHz song
3. **Count how long** before you hear audio (should be ~340ms)
4. Check if that timing matches start-delay

**If yes:** The "dropout" is actually working as intended - it's the prebuffer silence. The audio starts cleanly after the delay, you just don't hear the first 340ms (which is silence anyway).

**If no:** The dropout is longer or different, indicating actual audio loss.

---

## Expected Behavior vs Actual

### Expected (with start-delay = 16384)

```
Song A @ 44.1kHz playing
    ↓
User plays Song B @ 48kHz
    ↓
[341ms of SILENCE - you hear nothing]
    ↓
Song B starts playing from 00:00.341
    ↓
First notes AFTER 341ms delay
```

**Result:** You'd perceive this as "missing first 341ms of song"

### If This Is The Case

**The problem isn't dropout - it's that we're buffering TOO MUCH silence.**

**Solution:** Reduce start-delay until you find minimum that prevents actual stutter:

```lua
["api.alsa.start-delay"] = 4096,  -- ~85ms @ 48kHz
```

Then test if first notes play but you get clicks/stutter back.

---

## Next Diagnostic Step

**Please run this test:**

1. Play a 44.1kHz song in High Tide
2. Switch to a 48kHz song
3. **Use a stopwatch** - start it when you hit play
4. Stop it when you hear the first sound
5. Report the time

**Expected times:**
- With 16384 start-delay @ 48kHz: ~340ms
- With 12288 start-delay @ 48kHz: ~256ms
- With 8192 start-delay @ 48kHz: ~171ms

**If measured time matches start-delay:** The "dropout" is the working-as-intended silence buffer. We need to reduce it.

**If measured time is MUCH longer:** There's an additional problem beyond just the buffer delay.

---

## Summary

**Two possibilities:**

1. **start-delay is working** - The "dropout" you're experiencing IS the silence buffer (340ms). This is expected behavior. We can reduce it, but then clicks/stutter might return.

2. **start-delay NOT working** - Audio is being sent immediately, DAC drops it, THEN silence, THEN audio works. This would be a WirePlumber configuration issue.

**The stopwatch test will tell us which one it is.**
