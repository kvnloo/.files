# Audiophile Optimization Guide

Comprehensive research on audio optimization for high-fidelity listening on Linux.

## Current Setup Summary

| Component | Value | Status |
|-----------|-------|--------|
| **DAC** | Topping DX5 (32-bit, up to 768kHz, async USB) | Excellent |
| **Headphones** | HD800S + ThieAudio Monarch MKII | Excellent |
| **Amp** | Topping A90 | Excellent |
| **Sound Server** | PipeWire 1.5.85 (built from source) | Excellent |
| **Session Manager** | WirePlumber 1.5.85 | Excellent |
| **Bit Depth** | 32-bit float (internal), native to DAC | Optimal |
| **Sample Rate** | 44.1-768kHz adaptive (allowed-rates) | Optimal |
| **Avoid Resampling** | Yes (resample.quality=0 for passthrough) | Enabled |
| **Bit-Perfect Rules** | WirePlumber DX5 rules applied | Active |
| **Convolver (AutoEQ)** | EasyEffects + auto IR switching | Active |
| **Crossfeed** | EasyEffects BS2B-style | Active |
| **Software Volume** | 100% (hardware volume via A90) | Bit-Perfect |

**Current Optimization Score: ~98%**

### What Changed (PulseAudio → PipeWire)

| Improvement | Before (PulseAudio) | After (PipeWire) |
|-------------|---------------------|------------------|
| Sample rate switching | 44.1/48kHz only | Full range 44.1-768kHz |
| Latency | ~20-40ms | ~5-10ms |
| Buffer management | Fixed | Adaptive quantum |
| Resampling quality | speex-float-10 | Native passthrough |
| Session management | Basic | WirePlumber rules |
| DSP integration | PulseEffects (legacy) | EasyEffects (native) |

---

## The Audiophile Optimization Iceberg

```
                         ABOVE WATER (Essential)
                    ┌─────────────────────────────────┐
                    │  LAYER 1: BIT-PERFECT CHAIN     │
                    │  - Avoid resampling             │
                    │  - Lossless source              │
                    │  - Native sample rate           │
                    │  - Bypass software volume       │
                    └─────────────────────────────────┘
═══════════════════════════════════════════════════════════════════
                         WATERLINE
═══════════════════════════════════════════════════════════════════
                    ┌─────────────────────────────────┐
                    │  LAYER 2: HEADPHONE CORRECTION  │
                    │  - AutoEQ / Harman target       │
                    │  - Convolution filters          │
                    └─────────────────────────────────┘
               ┌─────────────────────────────────────────┐
               │  LAYER 3: DSP & PSYCHOACOUSTICS        │
               │  - Crossfeed (BS2B-style)              │
               │  - Dynamic range management            │
               └─────────────────────────────────────────┘
          ┌───────────────────────────────────────────────────┐
          │  LAYER 4: SOFTWARE STACK TUNING                   │
          │  - Sound server (PulseAudio vs PipeWire)          │
          │  - RT scheduling                                  │
          │  - Buffer optimization                            │
          └───────────────────────────────────────────────────┘
     ┌─────────────────────────────────────────────────────────────┐
     │  LAYER 5: ADVANCED RECONSTRUCTION                           │
     │  - HQPlayer upsampling                                      │
     │  - Native DSD                                               │
     └─────────────────────────────────────────────────────────────┘
  ┌───────────────────────────────────────────────────────────────────┐
  │  LAYER 6: HARDWARE ENVIRONMENT                                    │
  │  - Async USB mode                                                 │
  │  - USB isolation (if needed)                                      │
  └───────────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────────────┐
│  LAYER 7: EXTREME DIMINISHING RETURNS                                 │
│  - RT kernel, memory playback, process isolation                      │
└───────────────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────────────┐
│  LAYER 8: PLACEBO / SNAKE OIL                                         │
│  - Audiophile USB cables, MQA, "quantum" anything                     │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Layer Details

### LAYER 1: BIT-PERFECT CHAIN (Essential - HIGH Impact)

These are foundational requirements. Without these, all other optimizations are meaningless.

#### 1.1 Avoid Resampling

| Aspect | Details |
|--------|---------|
| **What it does** | Ensures audio is sent to DAC at native sample rate without conversion |
| **Impact** | **HIGH** - Poor resampling is audibly detectable |
| **Linux implementation** | `avoid-resampling = yes` in PulseAudio, or direct ALSA `hw:x,y` |

#### 1.2 Bypass Software Volume

| Aspect | Details |
|--------|---------|
| **What it does** | Prevents digital attenuation that reduces bit depth |
| **Technical explanation** | Digital volume at 16-bit: -6dB = 15-bit effective, -12dB = 14-bit |
| **Impact** | **HIGH** - Preserves full dynamic range |
| **Implementation** | Use hardware volume (amp/DAC), keep software at 100% |

#### 1.3 Lossless Source

| Aspect | Details |
|--------|---------|
| **What it does** | Preserves original audio data |
| **Impact** | **MEDIUM-HIGH** - Depends on source quality |
| **Note** | FLAC vs WAV is placebo - both decode to identical PCM |

---

### LAYER 2: HEADPHONE CORRECTION (HIGH Impact)

Arguably the highest-impact optimization after bit-perfect.

#### 2.1 Frequency Response Correction (AutoEQ)

| Aspect | Details |
|--------|---------|
| **What it does** | Corrects headphone FR deviations to match target curve |
| **Impact** | **HIGH** - Often 10+ dB corrections; clearly audible |
| **Scientific basis** | Harman research: 64% prefer headphones tuned to Harman curve |
| **Linux Software** | AutoEQ + EasyEffects/PulseEffects convolver |

**Our Setup:**
- Sennheiser HD800S profiles (44.1-384kHz)
- ThieAudio Monarch MKII profiles (44.1-48kHz)
- Auto-switching daemon for sample rate matching

---

### LAYER 3: DSP & PSYCHOACOUSTICS (MEDIUM Impact)

#### 3.1 Crossfeed

| Aspect | Details |
|--------|---------|
| **What it does** | Blends stereo channels to simulate speaker listening |
| **Impact** | **MEDIUM** - Reduces fatigue; preference-dependent |
| **Linux Software** | BS2B, EasyEffects/PulseEffects crossfeed plugin |

#### 3.2 ReplayGain / Loudness Normalization

| Aspect | Details |
|--------|---------|
| **What it does** | Normalizes perceived loudness across tracks |
| **Impact** | **MEDIUM** - Convenience feature |
| **Tradeoff** | Software gain slightly reduces dynamic range |

---

### LAYER 4: SOFTWARE STACK (LOW-MEDIUM Impact)

#### 4.1 Sound Server Selection

| Server | Notes |
|--------|-------|
| **PipeWire** | Modern, low latency, recommended - **OUR CHOICE** ✓ |
| **PulseAudio** | Mature, stable, adequate for playback |
| **Pure ALSA** | Bit-perfect possible, no mixing |

**Impact:** LOW-MEDIUM - Modern servers are nearly transparent

**Our Setup:** PipeWire 1.5.85 (built from source) with WirePlumber session manager.
Key advantages over PulseAudio:
- Native support for pro audio (JACK replacement)
- Better latency (~5ms vs ~20ms)
- Adaptive sample rate switching (full range 44.1-768kHz)
- More sophisticated buffer management
- Native integration with EasyEffects

#### 4.2 RT Scheduling

| Aspect | Details |
|--------|---------|
| **What it does** | Gives audio threads priority |
| **Impact** | **LOW** for playback (buffered), **HIGH** for recording |
| **Config** | PipeWire uses RTKit by default for RT scheduling |

---

### LAYER 5: ADVANCED RECONSTRUCTION (LOW-MEDIUM Impact)

#### 5.1 HQPlayer Upsampling

| Aspect | Details |
|--------|---------|
| **What it does** | Upsamples to high rates using sophisticated filters |
| **Impact** | **LOW-MEDIUM** - Depends on DAC quality |
| **Cost** | $250+ license, significant CPU |
| **Verdict** | Skip if you have a good DAC (like DX5) |

---

### LAYER 6: HARDWARE ENVIRONMENT (VARIABLE Impact)

#### 6.1 Async USB Mode

| Aspect | Details |
|--------|---------|
| **What it does** | DAC controls timing clock |
| **Impact** | **LOW-MEDIUM** - Modern async USB has inaudible jitter |
| **Our DAC** | DX5 uses async mode |

---

### LAYER 7: EXTREME DIMINISHING RETURNS (VERY LOW Impact)

| Optimization | Impact | Notes |
|--------------|--------|-------|
| RT Kernel | Very Low | Only for recording/live processing |
| Memory playback | Very Low/Placebo | No mechanism for improvement |
| Audiophile Linux distros | Very Low | Convenience, not audible |
| Process isolation | Very Low | Only for extreme low-latency |

---

### LAYER 8: PLACEBO / SNAKE OIL (NO Impact)

| Snake Oil | Reality |
|-----------|---------|
| Expensive USB cables | Digital bits arrive or don't - no quality difference |
| "Audiophile" Ethernet | Packet-based with error correction |
| Cable burn-in | No physical mechanism; listener adaptation |
| MQA | Proven lossy, dropped by Tidal in 2024 |
| Quantum fuses | Violates basic physics |

---

## Impact Summary

| Layer | Category | Impact | Worth Pursuing |
|-------|----------|--------|----------------|
| 1 | Bit-Perfect Chain | **HIGH** | **YES** - Essential |
| 2 | Headphone Correction | **HIGH** | **YES** - Biggest improvement |
| 3 | DSP/Psychoacoustics | **MEDIUM** | Yes - Preference-dependent |
| 4 | Software Stack | **LOW-MEDIUM** | Conditional |
| 5 | Advanced Reconstruction | **LOW-MEDIUM** | Maybe - Expensive, marginal |
| 6 | Hardware Environment | **VARIABLE** | Only if you have issues |
| 7 | Extreme Optimizations | **VERY LOW** | No |
| 8 | Snake Oil | **NONE** | **NO** |

---

## Our Implementation

### Files

```
~/.files/config/
├── pipewire/
│   └── pipewire.conf                    # PipeWire config (192kHz default, allowed-rates)
├── wireplumber/main.lua.d/
│   └── 51-topping-dx5-bitperfect.lua    # Bit-perfect rules for DX5
├── easyeffects/
│   └── easyeffects-ir-switcher.sh       # Auto-switch IR by sample rate
├── pulse/
│   └── AUDIOPHILE-OPTIMIZATION.md       # This file
├── autoeq/
│   ├── Sennheiser HD800 *.wav           # HD800S IRs (source files)
│   └── ThieAudio Monarch MKII *.wav     # Monarch IRs (source files)
├── autostart/
│   └── easyeffects-service.desktop      # EasyEffects autostart
└── systemd/user/
    └── easyeffects-ir-switcher.service  # IR switcher daemon

~/.config/easyeffects/
├── irs/                                 # Converted IR files (.irs)
└── output/
    ├── audiophile-hd800s.json           # HD800S preset (convolver + crossfeed)
    └── audiophile-monarch.json          # Monarch preset (convolver + crossfeed)
```

### Commands

```bash
# Switch headphones
~/.files/config/easyeffects/easyeffects-ir-switcher.sh hd800s
~/.files/config/easyeffects/easyeffects-ir-switcher.sh monarch

# Check status
~/.files/config/easyeffects/easyeffects-ir-switcher.sh status

# View IR switcher logs
journalctl --user -u easyeffects-ir-switcher -f

# Verify PipeWire audio chain
wpctl status
pw-top  # Watch for xruns (ERR column should be 0)

# Check current sample rate
pw-cli info all | grep -A20 "DX5" | grep "audio.rate"
```

### Verification Checklist

- [x] PipeWire 1.5.85 running (`pactl info | grep "Server Name"`)
- [x] DX5 volume at 100% (`wpctl get-volume 46`)
- [x] WirePlumber bit-perfect rules loaded (node.description = "Topping DX5 (Bit-Perfect)")
- [x] EasyEffects running and routing audio (`wpctl status`)
- [x] Convolver enabled with correct IR for headphones
- [x] Crossfeed enabled
- [x] IR switcher daemon running (`systemctl --user status easyeffects-ir-switcher`)
- [ ] No xruns during playback (`pw-top` - ERR column = 0)

---

## Sources

- [AutoEQ GitHub](https://github.com/jaakkopasanen/AutoEq)
- [EasyEffects GitHub](https://github.com/wwmm/easyeffects)
- [CamillaDSP GitHub](https://github.com/HEnquist/camilladsp)
- [Arch Linux PipeWire Wiki](https://wiki.archlinux.org/title/PipeWire)
- [Harman Target Curve Research](https://www.headphonesty.com/2020/04/harman-target-curves-part-3/)
- [Benchmark Media - Audiophile Snake Oil](https://benchmarkmedia.com/blogs/application_notes/audiophile-snake-oil)
