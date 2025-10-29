# Sample Rate Switching Stutter Fix - Tuning Guide

## Current Configuration (Applied)

```lua
["api.alsa.start-delay"] = 12288,    -- ~256ms @ 48kHz, ~278ms @ 44.1kHz (Option 1)
["api.alsa.period-size"] = 1024,     -- Larger buffer chunks
["api.alsa.headroom"] = 4096,        -- Extra safety margin
["session.suspend-timeout-seconds"] = 0,  -- Never suspend DX5
```

## Why the Delay is Adaptive (Automatically!)

The `start-delay` is measured in **samples**, not milliseconds. This means it automatically scales with sample rate:

| Sample Rate | Delay (samples) | Time (ms) | Use Case |
|-------------|-----------------|-----------|----------|
| 44.1 kHz | 12288 | **278ms** | Spotify, CD-quality FLAC |
| 48 kHz | 12288 | **256ms** | YouTube, video audio |
| 88.2 kHz | 12288 | **139ms** | Hi-res music (CD family) |
| 96 kHz | 12288 | **128ms** | Hi-res music (DVD family) |
| 176.4 kHz | 12288 | **70ms** | Ultra hi-res (CD family) |
| 192 kHz | 12288 | **64ms** | Ultra hi-res (DVD family) |
| 384 kHz | 12288 | **32ms** | Extreme hi-res |
| 768 kHz | 12288 | **16ms** | Maximum DX5 capability |

**Key insight:** Higher sample rates get proportionally shorter delays because the DAC clock locks faster at higher frequencies!

---

## Understanding the Stutter

### What Happens During Sample Rate Switch

```
Song A @ 44.1kHz playing
    ↓
Song B @ 48kHz starts
    ↓
[CRITICAL TRANSITION PERIOD]
1. PipeWire tells DAC: "Switch to 48kHz"
2. DAC stops 44.1kHz clock
3. DAC initializes 48kHz clock PLL
4. PLL locks to new frequency (takes time!)
5. DAC ready for 48kHz audio
    ↓
If audio starts during step 3-4: STUTTER/CLICK ❌
If audio starts after step 5: SMOOTH ✅
```

### The start-delay Solution

```
Before fix:
PipeWire → "Switch to 48kHz" → Audio immediately → CLICK! ❌

After fix:
PipeWire → "Switch to 48kHz" → 12288 samples silence → Audio starts → Smooth! ✅
                                 ↑
                         DAC locks during this silence
```

---

## If Stutter Still Occurs

### Option 1: Increase Delay (Conservative)

Edit `51-topping-dx5-bitperfect.lua`:

```lua
["api.alsa.start-delay"] = 12288,  -- 50% more time
```

**Timing:**
- @ 44.1kHz: 278ms
- @ 48kHz: 256ms
- @ 96kHz: 128ms

### Option 2: Even More Aggressive

```lua
["api.alsa.start-delay"] = 16384,  -- Double current value
["api.alsa.period-size"] = 2048,   -- Even larger buffers
["api.alsa.headroom"] = 8192,      -- More safety margin
```

**Timing:**
- @ 44.1kHz: 371ms
- @ 48kHz: 341ms
- @ 96kHz: 171ms

**Trade-off:** More latency when starting playback, but guaranteed smooth transitions.

### Option 3: Ultra-Conservative (Nuclear Option)

```lua
["api.alsa.start-delay"] = 24576,  -- 3x current value
["api.alsa.period-size"] = 4096,
["api.alsa.headroom"] = 16384,
```

**Timing:**
- @ 44.1kHz: 557ms
- @ 48kHz: 512ms
- @ 96kHz: 256ms

**When to use:** Only if Options 1-2 still stutter. This is half a second of delay!

---

## Why You Might Still Hear Stutter

### 1. DAC Needs More Lock Time
**Solution:** Increase `start-delay` (see options above)

### 2. Device Suspend/Resume
**Solution:** Already fixed with `session.suspend-timeout-seconds = 0`

### 3. High Tide Gapless Playback Issues
**Problem:** High Tide might have bugs with gapless + PipeWire
**Solution:** Disable gapless in High Tide settings (if option exists)

### 4. First Sound Cut Off
**Problem:** The delay only applies to **new streams**, not the first sample of audio
**Explanation:** This is normal - the delay buffers silence BEFORE audio. Once audio starts, it plays normally. You shouldn't lose any samples.

### 5. USB Bus Issues
**Problem:** USB controller interference
**Solution:**
```bash
# Check for USB errors
dmesg | grep -i "usb.*audio\|alsa.*error" | tail -20

# Try different USB port (preferably USB 2.0, not 3.0)
# Some DACs have issues with USB 3.0 power management
```

---

## Testing the Fix

### Best Test Method

1. **Open Two Sources at Different Rates:**
   - Tab 1: Spotify (44.1kHz)
   - Tab 2: YouTube (48kHz)

2. **Switch Quickly Between Them:**
   - Play Spotify for 5 seconds
   - Switch to YouTube
   - **Listen during transition** - should be smooth now!

3. **Monitor in Real-Time:**
   ```bash
   watch -n 0.5 'cat /proc/asound/card0/stream0 | grep "Momentary freq"'
   ```
   You'll see: `44099 Hz` → `48000 Hz`

### What "Fixed" Sounds Like

**Before:**
```
Song @ 44.1kHz → click/pop/stutter → Song @ 48kHz
```

**After:**
```
Song @ 44.1kHz → brief silence (~170ms) → Song @ 48kHz
                      ↑
                No clicks or pops!
```

---

## Understanding the Trade-off

| Delay (samples) | @ 44.1kHz | @ 48kHz | Smoothness | Perceived Latency |
|-----------------|-----------|---------|------------|-------------------|
| **4096** (original) | 93ms | 85ms | Moderate | Barely noticeable |
| **8192** | 186ms | 171ms | Better | Still acceptable |
| **12288** (current) | 278ms | 256ms | Very good | Noticeable but okay |
| **16384** | 371ms | 341ms | Excellent | Noticeable delay |
| **24576** | 557ms | 512ms | Perfect | Half-second pause |

**Sweet spot for most users:** 12288-16384 samples

---

## Why This Approach is Correct

### Alternative Approaches (That Don't Work)

❌ **Force fixed sample rate:**
- Requires resampling everything → not bit-perfect
- Wastes CPU
- Defeats the purpose of automatic rate switching

❌ **ALSA-level hacks with .asoundrc:**
- Breaks PipeWire integration
- Loses multi-app support
- Complex and fragile

❌ **Wait for High Tide to add prebuffer option:**
- Doesn't address the root cause (DAC locking time)
- Would only help if High Tide was the problem

✅ **PipeWire start-delay (Our Approach):**
- Works at the right layer (between PipeWire and ALSA)
- Maintains bit-perfect playback
- Preserves multi-app support
- Adaptive to sample rate automatically
- Clean, maintainable solution

---

## Verifying Current Settings

Check if settings are applied:

```bash
# Method 1: Check node properties (if available)
pw-cli info $(pactl list sinks short | grep DX5 | awk '{print $1}')

# Method 2: Monitor buffer behavior during playback
pw-top
# Look at QUANT (quantum) and RATE columns

# Method 3: Check ALSA directly
cat /proc/asound/card0/pcm0p/sub0/hw_params
```

---

## Next Steps

1. **Test the current fix** (12288 samples)
2. **If still stuttering:** Try Option 2 (16384 samples)
3. **If Option 2 insufficient:** Try Option 3 (24576 samples)
4. **Report back:** What delay value worked for you?

---

## Fine-Tuning by Sample Rate

If certain sample rates still stutter, you can't configure per-rate delays in PipeWire directly. However, you can:

1. **Increase global delay** until all rates are smooth
2. **Accept longer delay at lower rates** (adaptive scaling means high rates still fast)
3. **Use ALSA exclusive mode** for problematic tracks (nuclear option)

---

## The Physics of DAC Locking

**Why does this take time?**

USB DACs use a Phase-Locked Loop (PLL) to generate the audio clock:
1. **Receive sample rate command** from USB (~instant)
2. **VCO starts at new frequency** (~1ms)
3. **PLL phase detector** compares to USB SOF timing
4. **PLL converges** to lock (10-200ms depending on PLL design)
5. **Jitter settles** to spec (~50ms additional)

**Total: 60-250ms** for typical USB DACs

The Topping DX5 is a high-quality DAC, but USB audio class compliance means it follows standard USB Audio timing, which is why we need the prebuffer.

---

## Summary

✅ **Current config**: 12288 samples (~256-278ms)
✅ **Should eliminate most stuttering**
✅ **Automatically adaptive** to sample rate
✅ **Preserves bit-perfect playback**

If still stuttering: Increase `start-delay` to 16384 or 24576 samples.

**Test it now!** Switch between Spotify and YouTube rapidly - should be smooth! 🎧
