# PipeWire Audiophile Audio Setup - Complete Summary

## What This Setup Does

PipeWire native filter-chain DSP replaces EasyEffects entirely, providing 3 simultaneous virtual sinks for instant A/B/C spatial mode switching — all processing happens inside PipeWire with zero external dependencies beyond LV2/LADSPA plugins.

## What's Working

### 1. Native Filter-Chain DSP
Three virtual sinks, each with a full processing chain:

| Sink | Chain |
|------|-------|
| **Headphone DSP** (clean) | AutoEQ → Loudness Comp → MBC → Limiter |
| **Headphone DSP + Crossfeed** | AutoEQ → bs2b Crossfeed → Loudness Comp → MBC → Limiter |
| **Headphone DSP + Room** | AutoEQ → BRIR True Stereo → Loudness Comp → MBC → Limiter |

Switching between sinks is instant (no PipeWire restart needed).

### 2. Per-Headphone AutoEQ
Symlink-based profile switching between headphone EQ profiles:
- **HD800S**: IEF Preference 2025 + Harman Over-Ear 2018
- **Monarch MKII**: IEF Preference 2025 + Harman In-Ear 2019
- Multi-rate IRs: 44.1k, 48k, 96k, 192k, 384k Hz

### 3. Bit-Perfect Transport
- **Sample rates**: Automatic switching (44.1kHz - 384kHz)
- **Multi-app support**: Spotify, YouTube, High Tide run simultaneously
- **Format**: S32LE output (25-bit precision via PipeWire 1.4+ F32-to-S32 path)
- **Resampler**: Quality 14 (best sinc filter) when resampling is needed

### 4. RT Scheduling
- SCHED_FIFO priority 88 via `pipewire` group membership
- `threadirqs` kernel parameter for reduced interrupt latency

---

## Configuration Files

```
config/pipewire/
├── pipewire.conf                      # Sample rate switching, 192kHz default
├── pipewire.conf.d/
│   └── 10-headphone-dsp.conf          # Filter-chain DSP (3 sinks, full chain)
├── headphone-switch.sh                # CLI: spatial mode + EQ profile switching
├── README.md                          # Full documentation
├── SETUP-UBUNTU.md                    # Ubuntu manual setup guide
└── SUMMARY.md                         # This file

config/wireplumber/main.lua.d/
└── 51-topping-dx5-bitperfect.lua      # DX5: S32LE, resample.quality=14, headroom=0

config/autoeq/
├── active_44100Hz.wav → (symlink)     # Currently active EQ profile
├── active_48000Hz.wav → (symlink)
├── active_96000Hz.wav → (symlink)
├── active_192000Hz.wav → (symlink)
├── active_384000Hz.wav → (symlink)
├── Sennheiser HD800 minimum phase *.wav
└── ThieAudio Monarch MKII minimum phase *.wav
```

### What Each File Does

**`pipewire.conf`:**
- Sets allowed sample rates (44.1kHz - 384kHz)
- Enables automatic rate switching
- Default rate: 192kHz

**`pipewire.conf.d/10-headphone-dsp.conf`:**
- Defines 3 filter-chain virtual sinks
- Each sink: AutoEQ convolver + optional spatial + loudness comp + MBC + limiter
- All processing is native PipeWire — no EasyEffects

**`51-topping-dx5-bitperfect.lua`:**
- S32LE output format (was S24LE — S32LE is strictly better on PipeWire 1.4+)
- resample.quality = 14 (best sinc filter)
- api.alsa.headroom = 0 (DX5 is stable async USB)
- Prevents suspend, keeps ALSA reservation active

**`headphone-switch.sh`:**
- `headphone-switch.sh clean|crossfeed|room` — instant spatial mode switch
- `headphone-switch.sh eq monarch|hd800s` — EQ profile switch (restarts PipeWire)

---

## DSP Chain Details

### AutoEQ Convolver
Per-headphone minimum-phase IR convolution for frequency correction.
Generated with AutoEQ CLI against target response curves.

### bs2b Crossfeed (Sink 2 only)
LADSPA plugin. Jan Meier preset: 700 Hz crossover / 4.5 dB cut.
Analog-like stereo-to-binaural blending to reduce headphone stereo separation.

### ASH BRIR True Stereo (Sink 3 only)
Room R02 (WDR Broadcast Control Room, RT60 0.235s).
4-channel convolver (LL, LR, RL, RR) with gain=0.5 for level matching.

### LSP Loudness Compensator
ISO 226:2003 equal-loudness contours.
Adjusts perceived frequency balance at different listening volumes.

### GentleDynamics MBC
8-band Bark-scale multiband compressor (LSP `mb_compressor_stereo`).
Mixed upward/downward compression. Reduces listening fatigue.

### ZaMaximX2 Limiter
Safety brickwall limiter. Ceiling: -0.3 dBFS.

---

## Usage

### Everyday Listening
```bash
# Set your preferred spatial mode
headphone-switch.sh clean        # No spatial processing
headphone-switch.sh crossfeed    # bs2b crossfeed
headphone-switch.sh room         # BRIR room simulation
```

All sinks include AutoEQ + Loudness Comp + MBC + Limiter.

### Switching Headphones
```bash
headphone-switch.sh eq hd800s    # Switch to HD800S EQ profile
headphone-switch.sh eq monarch   # Switch to Monarch MKII EQ profile
```

EQ switching requires a PipeWire restart (the script handles this).

### Check Status
```bash
headphone-switch.sh              # Show current sink and EQ profile
```

---

## Verification Commands

### Check DSP Sinks are Loaded
```bash
pw-cli ls Node | grep -A3 "Headphone DSP"
# Should show 3 filter-chain nodes
```

### Monitor Playback
```bash
pw-top
# DX5 row: RATE matches source, FORMAT=S32LE, XRUN=0
```

### Check RT Scheduling
```bash
chrt -p $(pgrep -x pipewire)
# Expected: SCHED_FIFO priority 88
```

### Check DX5 Properties
```bash
pw-cli info $(pw-cli ls Node | grep "Topping DX5" | head -1 | awk '{print $2}') \
  | grep -E "resample|headroom|audio.format"
# Expected: resample.quality=14, headroom=0, audio.format=S32LE
```

---

## Audio Quality Chain

```
Source: FLAC 96kHz/24-bit
    |
Player: Decodes to PCM
    |
PipeWire: 32-bit float internal
    |
Filter-Chain: AutoEQ → [Crossfeed|BRIR] → Loudness → MBC → Limiter
    |
ALSA: S32LE → USB
    |
DX5: DAC rate matches source → Headphones
```

---

## Prerequisites (Ubuntu)

```bash
# Required packages
sudo apt install lsp-plugins-lv2 zam-plugins bs2b-ladspa

# RT scheduling
sudo groupadd -f pipewire
sudo usermod -aG pipewire $USER
# Reboot for group change

# Recommended: threadirqs kernel parameter
# Add to GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub
```

See `SETUP-UBUNTU.md` for complete step-by-step setup instructions.

---

## What You Get

- Native PipeWire filter-chain DSP (no EasyEffects dependency)
- 3 virtual sinks for instant spatial mode A/B/C switching
- Per-headphone AutoEQ with one-command profile switching
- S32LE output with quality-14 resampling
- RT scheduling for dropout-free playback under load
- Automatic sample rate matching (44.1kHz - 384kHz)
- Multi-app audio (Spotify + YouTube + High Tide simultaneously)
