# AutoEQ Convolution EQ Setup Guide for Sennheiser HD 800S

## Executive Summary

**Quick Recommendations:**
- **Sample Rates:** Download 44.1kHz, 48kHz, and 96kHz .wav files
- **Bit Depth:** 32-bit float
- **Phase:** Minimum phase (avoid linear phase pre-ringing)
- **Frequency Resolution:** 1Hz (your 10900K can handle it, provides better bass accuracy)
- **Integration:** Use EasyEffects with PipeWire
- **Profile:** `Sennheiser HD 800 S` by Crinacle (Ears-711)

---

## Understanding Bit-Perfect vs EQ Processing

### Important Reality Check

❌ **Convolution EQ is NOT bit-perfect** - EQ processing fundamentally modifies the audio signal

✅ **But you can maintain sample-rate-accurate processing** - Use the correct filter for each rate

**What This Means:**
- Your audio will be EQ'd (modified by the filter)
- The sample rate can still match the source (44.1kHz source → 44.1kHz filter → 44.1kHz output)
- No resampling occurs, but the frequency response is altered (that's the point of EQ!)

**Philosophy:** If you're using EQ, you've already decided to modify the audio for better subjective quality. The goal now is to do it cleanly without adding resampling artifacts.

---

## AutoEQ Configuration Decisions

### 1. Sample Rates - Multi-File Strategy

**Recommendation:** Download .wav files for **44.1kHz, 48kHz, and 96kHz**

**Rationale:**
- 44.1kHz: Spotify, CD-quality FLAC, most music
- 48kHz: YouTube, video audio, many streaming sources
- 96kHz: Hi-res FLAC, audiophile content

**Why not more rates?**
- 192kHz+: Extremely rare in practice, and if you're using EQ, the ultra-hi-res purity argument is moot
- EasyEffects can be configured to select the appropriate filter based on stream rate

**Implementation:**
```
HD800S_44100Hz_32bit_minimum.wav  (for 44.1kHz sources)
HD800S_48000Hz_32bit_minimum.wav  (for 48kHz sources)
HD800S_96000Hz_32bit_minimum.wav  (for 96kHz sources)
```

### 2. Bit Depth - 32-bit Float

**Recommendation:** **32-bit float**

**Rationale:**
- Higher dynamic range prevents rounding errors in convolution math
- Matches PipeWire's internal processing (32-bit float anyway)
- No audible difference in file size vs quality trade-off
- Industry standard for audio processing chains

**Comparison:**
| Bit Depth | Dynamic Range | Use Case |
|-----------|---------------|----------|
| 16-bit | 96 dB | Final output, CD format |
| 24-bit | 144 dB | Recording, mastering |
| 32-bit float | ~1500 dB | Processing, convolution |

**Verdict:** 32-bit float for convolution filters

### 3. Phase - Minimum Phase

**Recommendation:** **Minimum phase**

**Rationale:**

**Minimum Phase:**
- Natural-sounding transient response
- No pre-ringing artifacts
- How analog EQs and most digital EQs work
- Headphone EQ community standard

**Linear Phase:**
- Phase coherent (all frequencies delayed equally)
- **Creates audible pre-ringing** before transients
- Makes drum hits and percussive sounds lose punch
- Higher latency
- Useful for mastering, NOT headphone listening

**Technical Detail:**
Linear phase filters distribute ringing both before and after the signal. This "pre-echo" is particularly problematic for headphones because:
- You're listening in a controlled environment (headphones) where these artifacts are audible
- Transient attack is critical to perceived quality
- Pre-ringing precedes the sound that caused it (physically impossible in nature, sounds "wrong")

**Head-Fi Community Consensus:** Minimum phase for headphone EQ, linear phase for speaker room correction

**Verdict:** Minimum phase

### 4. Frequency Resolution - 1Hz

**Recommendation:** **1Hz** (given your 10900K CPU)

**Rationale:**

**The Math:**
- 1Hz resolution at 48kHz sample rate requires ~48,000 filter taps
- 16Hz resolution requires ~3,000 filter taps
- **16x more CPU usage** for 1Hz vs 16Hz

**CPU Impact:**
- Your i9-10900K: 10 cores, 20 threads, 5.3GHz boost
- Modern CPUs handle convolution via FFT (Fast Fourier Transform)
- **For a single stereo stream, even 1Hz is <5% CPU on your hardware**

**Audio Quality Impact:**
- **Bass accuracy:** 1Hz resolution = 1Hz precision in bass EQ (critical for HD 800S bass shelf)
- **HD 800S specific:** The 6kHz and 11kHz peaks require precise correction
- **AutoEQ note:** "Smaller values give more accurate bass but require more CPU power"

**HD 800S Context:**
The HD 800S is known for:
- Extended bass response (but lean)
- Prominent 6kHz peak (can be fatiguing)
- 11kHz treble peak

Precise bass EQ matters more for these high-end headphones than for consumer models.

**Verdict:** 1Hz resolution - your CPU can handle it, and the HD 800S deserves the precision

### 5. Preamp

**Recommendation:** Use AutoEQ's automatic preamp calculation

**Rationale:**
- AutoEQ automatically calculates the required preamp to prevent clipping
- Convolution filters can increase signal level at certain frequencies
- Preamp attenuation prevents digital clipping (>0dBFS)

**Typical Values:** -5dB to -8dB for most headphone profiles

**Don't Change Unless:** You experience clipping (distortion) or excessive volume loss

### 6. Stereo Processing

**Recommendation:** Enabled (use stereo .wav file)

**Rationale:**
- HD 800S has wide soundstage with specific L/R channel characteristics
- Stereo convolution allows independent left/right channel EQ if needed
- No downside vs mono (file size negligible)

---

## HD 800S Specific Recommendations

### AutoEQ Profile Selection

**Recommended Profile:**
```
Sennheiser HD 800 S (by Crinacle, Ears-711)
```

**Why this one?**
- Crinacle's measurements are highly regarded in the audiophile community
- Ears-711 rig is industry-standard for headphone measurement
- Targets Harman over-ear 2018 curve (balanced reference)

**Alternative Profiles:**
- `Sennheiser HD 800 S (by oratory1990)` - Also excellent, slightly different target
- `Sennheiser HD 800 S (by Rtings)` - Consumer-focused measurement

### What the EQ Corrects

The HD 800S stock frequency response has:
1. **6kHz peak** (~5dB) - Can cause listening fatigue, sibilance
2. **11kHz peak** (~3dB) - Brightness, treble emphasis
3. **Bass shelf** (subtle lean) - Slightly less bass quantity than Harman target

AutoEQ will:
- Reduce the 6kHz peak for less fatigue
- Tame the 11kHz treble
- Gently boost sub-bass for more weight
- Smooth overall frequency response to match Harman target

---

## PipeWire Integration via EasyEffects

### Installation

```bash
# Install EasyEffects (includes convolution plugin)
sudo apt install easyeffects

# Or via Flatpak (recommended, includes all plugins)
flatpak install flathub com.github.wwmm.easyeffects
```

### Configuration Strategy

**Challenge:** PipeWire sample rate switching + Convolution EQ

**Problem:** If you load a single 48kHz .wav filter, but play 44.1kHz audio, EasyEffects will either:
1. Resample the audio to 48kHz (defeats bit-perfect goal)
2. Resample the filter to 44.1kHz (suboptimal)

**Solution:** Use multiple convolution presets and switch based on content

#### Option A: Multiple Presets (Recommended)

Create three EasyEffects presets:
1. `HD800S_44.1kHz` → Loads HD800S_44100Hz_32bit_minimum.wav
2. `HD800S_48kHz` → Loads HD800S_48000Hz_32bit_minimum.wav
3. `HD800S_96kHz` → Loads HD800S_96000Hz_32bit_minimum.wav

**Usage:** Manually switch preset based on what you're listening to:
- Spotify session → `HD800S_44.1kHz` preset
- YouTube session → `HD800S_48kHz` preset
- Hi-res FLAC session → `HD800S_96kHz` preset

**Pros:**
- No resampling of audio OR filter
- True sample-rate-accurate processing
- Explicit control

**Cons:**
- Manual preset switching required
- Forgetfulness = wrong filter = slight degradation

#### Option B: Single 48kHz Filter (Acceptable Compromise)

Use only the 48kHz filter for everything.

**How PipeWire Handles This:**
1. 44.1kHz source plays
2. EasyEffects sees 44.1kHz stream
3. EasyEffects resamples 48kHz filter to 44.1kHz for processing
4. Output remains 44.1kHz

**Pros:**
- Simpler setup (one preset)
- No user intervention

**Cons:**
- Filter resampling introduces minor artifacts (usually inaudible)
- Not optimal for audiophile purity

**Verdict:** If you can't be bothered to switch presets, this is acceptable. The EQ correction benefit far outweighs the minor filter resampling artifacts.

#### Option C: PipeWire Fixed Rate (NOT Recommended)

Force PipeWire to always run at 48kHz and resample all sources.

**Why NOT:**
- Defeats the entire bit-perfect PipeWire setup we just built
- Resamples 44.1kHz content (Spotify) unnecessarily
- You already solved sample-rate switching!

**Verdict:** Don't do this.

### EasyEffects Setup Steps

1. **Install EasyEffects**
   ```bash
   flatpak install flathub com.github.wwmm.easyeffects
   ```

2. **Download AutoEQ .wav files**
   - Visit: https://autoeq.app/
   - Select: `Sennheiser HD 800 S` (Crinacle, Ears-711)
   - Configure:
     - Sample rate: 44.1kHz
     - Bit depth: 32-bit float
     - Phase: Minimum
     - Frequency resolution: 1Hz
     - Stereo: Enabled
   - Download: `Sennheiser HD 800 S (Crinacle).wav`
   - Rename: `HD800S_44100Hz_32bit_minimum.wav`

3. **Repeat for 48kHz and 96kHz**

4. **Create directory for filters**
   ```bash
   mkdir -p ~/.config/easyeffects/irs
   mv HD800S_*.wav ~/.config/easyeffects/irs/
   ```

5. **Open EasyEffects**
   ```bash
   flatpak run com.github.wwmm.easyeffects
   ```

6. **Add Convolver Effect**
   - Click "Effects" tab
   - Enable "Convolver"
   - Load impulse response: Browse to `~/.config/easyeffects/irs/HD800S_44100Hz_32bit_minimum.wav`

7. **Save Preset**
   - Click "Presets" menu
   - Save as: `HD800S_44.1kHz`

8. **Repeat for 48kHz and 96kHz presets**

9. **Auto-start EasyEffects**
   - Settings → Enable "Start Service at Login"

---

## Performance Expectations

### CPU Usage (i9-10900K)

| Resolution | Filter Taps | Expected CPU (Single Stream) |
|------------|-------------|------------------------------|
| 1Hz @ 44.1kHz | ~44,100 | 2-4% |
| 1Hz @ 48kHz | ~48,000 | 2-4% |
| 1Hz @ 96kHz | ~96,000 | 4-7% |
| 16Hz @ 48kHz | ~3,000 | <1% |

**Verdict:** Your 10900K will barely notice even 1Hz @ 96kHz.

### Latency

Convolution introduces latency proportional to filter length:
- 1Hz @ 48kHz: ~1 second of latency (not real-time, buffered)
- Perceived latency in EasyEffects: ~50-100ms (due to buffering optimization)

**Impact:**
- Music playback: No noticeable impact
- Gaming: Not recommended (use bypass)
- Video: Might need A/V sync adjustment

---

## Quality Verification

### How to Test Your Setup

1. **Play a familiar track** (44.1kHz FLAC)

2. **Monitor PipeWire rate:**
   ```bash
   watch -n 0.5 'cat /proc/asound/card0/stream0 | grep "Momentary freq"'
   ```

3. **Toggle Convolver on/off** in EasyEffects

4. **Listen for:**
   - Before: HD 800S stock signature (bright 6kHz, lean bass)
   - After: Smoother treble, fuller bass, more balanced

5. **Check CPU usage:**
   ```bash
   htop
   ```
   Look for easyeffects process ~2-4% usage

### Red Flags

❌ **Sample rate changes when EasyEffects is enabled**
- Indicates unwanted resampling
- Check preset uses correct filter for current rate

❌ **Crackling or distortion**
- Reduce preamp (digital clipping)
- Check CPU isn't pegged (unlikely on 10900K)

❌ **Excessive latency (>200ms)**
- Check EasyEffects buffer settings
- Consider reducing resolution to 16Hz if needed

---

## Maintenance and Updates

### When to Re-download Filters

- AutoEQ updates measurement database periodically
- Check GitHub: https://github.com/jaakkopasanen/AutoEq
- Re-download if:
  - New HD 800S measurements published
  - You want to try different target curve (e.g., Harman vs diffuse-field)
  - AutoEQ algorithm improves

### Backup Your Presets

```bash
# EasyEffects presets location
~/.var/app/com.github.wwmm.easyeffects/config/easyeffects/output/

# Back up
cp -r ~/.var/app/com.github.wwmm.easyeffects/config/easyeffects ~/backup/
```

---

## Alternative Approaches

### A. Parametric EQ Instead of Convolution

**Pros:**
- Lower CPU usage
- No latency
- Easier to tweak manually

**Cons:**
- Less precise than convolution
- More complex to configure (10+ bands for HD 800S)
- Can't achieve arbitrary frequency responses

**Verdict:** Convolution is superior for full AutoEQ implementation. Parametric EQ is fine for minor tweaks.

### B. ALSA Exclusive Mode + Convolution

**Possibility:** Run convolution in ALSA exclusive mode to bypass PipeWire entirely.

**Verdict:** This defeats multi-app support. Not worth it.

### C. Bypass EQ for Critical Listening

**Option:** Create a "Bypass" preset with no effects for A/B comparison.

**Usage:**
- Casual listening: EQ enabled
- Critical listening / mixing: EQ bypassed

---

## Summary Configuration

**Your Optimal Setup:**

```yaml
AutoEQ_Configuration:
  headphones: "Sennheiser HD 800 S"
  profile: "Crinacle (Ears-711)"

  download_settings:
    sample_rates: [44100, 48000, 96000]
    bit_depth: 32-bit float
    phase: minimum
    frequency_resolution: 1Hz
    stereo: true

  files:
    - HD800S_44100Hz_32bit_minimum.wav
    - HD800S_48000Hz_32bit_minimum.wav
    - HD800S_96000Hz_32bit_minimum.wav

  integration:
    tool: EasyEffects
    presets:
      - name: "HD800S_44.1kHz"
        filter: HD800S_44100Hz_32bit_minimum.wav
      - name: "HD800S_48kHz"
        filter: HD800S_48000Hz_32bit_minimum.wav
      - name: "HD800S_96kHz"
        filter: HD800S_96000Hz_32bit_minimum.wav

  usage:
    spotify: "HD800S_44.1kHz preset"
    youtube: "HD800S_48kHz preset"
    hires_flac: "HD800S_96kHz preset"

  performance:
    expected_cpu: 2-4% per stream
    expected_latency: 50-100ms
```

---

## Quick Start Checklist

- [ ] Install EasyEffects: `flatpak install flathub com.github.wwmm.easyeffects`
- [ ] Visit AutoEQ: https://autoeq.app/
- [ ] Select: Sennheiser HD 800 S (Crinacle)
- [ ] Download 44.1kHz, 48kHz, 96kHz .wav files (32-bit float, minimum phase, 1Hz)
- [ ] Move files to: `~/.config/easyeffects/irs/`
- [ ] Open EasyEffects, enable Convolver
- [ ] Load 44.1kHz filter, save preset as "HD800S_44.1kHz"
- [ ] Repeat for 48kHz and 96kHz
- [ ] Test with music, verify sample rate doesn't change
- [ ] Enable "Start Service at Login"
- [ ] Enjoy improved HD 800S frequency response!

---

## Further Reading

- AutoEQ GitHub: https://github.com/jaakkopasanen/AutoEq
- AutoEQ Web App: https://autoeq.app/
- EasyEffects Documentation: https://github.com/wwmm/easyeffects
- HD 800S Measurements: https://crinacle.com/graphs/headphones/sennheiser-hd800s/
- Minimum vs Linear Phase Discussion: https://www.head-fi.org/threads/equalization-further-exploration-minimal-phase-vs-linear-phase.571762/
