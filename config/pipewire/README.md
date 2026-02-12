# PipeWire Audiophile Audio Configuration

This directory contains PipeWire, WirePlumber, and filter-chain DSP configuration for audiophile-grade playback with the **Topping DX5** USB DAC driving **Sennheiser HD800S** and **ThieAudio Monarch MKII** headphones.

## Overview

This setup enables:
- **Bit-perfect audio transport** with automatic sample rate matching (44.1kHz-384kHz)
- **Native PipeWire filter-chain DSP** — no EasyEffects, no external DSP host
- **3 simultaneous virtual sinks** for instant A/B/C spatial mode switching
- **Per-headphone AutoEQ** with symlink-based profile switching
- **Multi-application support** (High Tide, Spotify, YouTube, system sounds)
- **RT scheduling** via `pipewire` group (SCHED_FIFO priority 88)
- **S32LE output** (25-bit precision F32-to-S32 path in PipeWire 1.4+)

## Architecture

```
Audio Source (FLAC / Spotify / YouTube)
    |
    v
PipeWire (32-bit float internal)
    |
    v
┌─────────────────────────────────────────────────────┐
│  Filter-Chain DSP (10-headphone-dsp.conf)           │
│                                                     │
│  ┌─── Sink 1: "Headphone DSP" (clean) ───────────┐ │
│  │ AutoEQ Convolver → Loudness Comp → MBC → Limit │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Sink 2: "Headphone DSP + Crossfeed" ───────┐ │
│  │ AutoEQ → bs2b Crossfeed → Loud → MBC → Limit  │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Sink 3: "Headphone DSP + Room" ────────────┐ │
│  │ AutoEQ → BRIR True Stereo → Loud → MBC → Limit│ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
    |
    v
ALSA → USB → Topping DX5 (S32LE) → Headphones
```

## DSP Chain Components

### AutoEQ Convolver
Per-headphone frequency correction using minimum-phase impulse responses generated with the AutoEQ CLI.
- **HD800S target**: IEF Preference 2025 + Harman Over-Ear 2018
- **Monarch MKII target**: IEF Preference 2025 + Harman In-Ear 2019
- **Multi-rate IRs**: 44.1k, 48k, 96k, 192k, 384k Hz
- **Profile switching**: Symlinks (`active_*.wav` -> headphone-specific IR files in `config/autoeq/`)

### bs2b Crossfeed (Sink 2 only)
LADSPA plugin providing analog-like stereo-to-binaural crossfeed.
- **Preset**: Jan Meier (700 Hz crossover / 4.5 dB cut)
- **Purpose**: Reduces extreme stereo separation that headphones produce vs speakers

### ASH BRIR True Stereo (Sink 3 only)
Binaural room impulse response convolver for speaker-like spatial presentation.
- **Room**: R02 (WDR Broadcast Control Room, RT60 0.235s)
- **Format**: 4-channel convolver (true stereo: LL, LR, RL, RR)
- **Gain**: 0.5 for level matching with non-BRIR sinks

### LSP Loudness Compensator
ISO 226:2003 equal-loudness contour compensation.
- Adjusts perceived frequency balance at different listening volumes
- Low volumes get bass/treble boost matching human hearing curves

### GentleDynamics Multiband Compressor
8-band Bark-scale multiband compressor (LSP `mb_compressor_stereo`).
- Mixed upward/downward compression
- Reduces listening fatigue on long sessions
- Subtle dynamic range management, not brickwall limiting

### ZaMaximX2 Limiter
Safety brickwall limiter at the end of the chain.
- **Ceiling**: -0.3 dBFS
- Prevents DAC clipping from DSP gain stacking

## Configuration Files

### `pipewire/pipewire.conf`
Core PipeWire daemon configuration:
- **default.clock.rate**: 192000 (high-resolution default)
- **default.clock.allowed-rates**: All standard rates from 44100 to 384000 Hz

### `pipewire/pipewire.conf.d/10-headphone-dsp.conf`
The filter-chain DSP configuration defining all 3 virtual sinks and their processing chains.

### `wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua`
Topping DX5 specific ALSA node properties:
- **audio.format**: S32LE (32-bit integer for maximum precision)
- **resample.quality**: 14 (best sinc filter, minimal aliasing)
- **api.alsa.headroom**: 0 (DX5 is stable async USB)
- **clock.force-quantum**: 1024

### `headphone-switch.sh`
CLI tool for instant spatial mode and EQ profile switching. See [Switching](#switching).

## Installation

### 1. Symlink Configuration Files

```bash
# WirePlumber DX5 config
mkdir -p ~/.config/wireplumber/main.lua.d
ln -sf ~/workspace/.files/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua \
       ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua

# PipeWire daemon config
mkdir -p ~/.config/pipewire
ln -sf ~/workspace/.files/config/pipewire/pipewire.conf \
       ~/.config/pipewire/pipewire.conf

# PipeWire filter-chain DSP
mkdir -p ~/.config/pipewire/pipewire.conf.d
ln -sf ~/workspace/.files/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf \
       ~/.config/pipewire/pipewire.conf.d/10-headphone-dsp.conf
```

### 2. Restart PipeWire Services

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### 3. Set Default Sink

```bash
# List sinks — you should see 3 "Headphone DSP" entries
wpctl status | grep -A10 "Audio/Sink"

# Set your preferred default
headphone-switch.sh clean      # or crossfeed, or room
```

## Switching

The `headphone-switch.sh` script provides instant switching between spatial modes and EQ profiles.

### Spatial Mode (instant, no restart)
```bash
headphone-switch.sh clean        # AutoEQ + Loudness + MBC + Limiter
headphone-switch.sh crossfeed    # + bs2b crossfeed
headphone-switch.sh room         # + BRIR room simulation
```

### EQ Profile (requires PipeWire restart)
```bash
headphone-switch.sh eq hd800s    # Switch to HD800S IRs
headphone-switch.sh eq monarch   # Switch to Monarch MKII IRs
```

### Show Current Status
```bash
headphone-switch.sh              # Shows active sink and EQ profile
```

## Verification

### Check DSP Chain is Loaded
```bash
pw-cli ls Node | grep -A3 "Headphone DSP"
# Should show 3 filter-chain sink nodes
```

### Check Bit-Perfect Transport
```bash
pw-top
# Find the DX5 row — RATE column should match source, FORMAT=S32LE
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

## How It Works

### Audio Quality Chain
```
Source: FLAC 96kHz/24-bit
    |
High Tide / Spotify: Decodes to PCM
    |
PipeWire: 32-bit float internal processing
    |
Filter-Chain DSP: AutoEQ → [Crossfeed|BRIR] → Loudness → MBC → Limiter
    |
ALSA: S32LE → USB
    |
DX5: Receives processed audio, DAC rate matches source
    |
Result: DSP-processed, sample-rate-matched playback
```

### Single Application
```
High Tide plays 96kHz FLAC
    |
PipeWire detects 96000 in allowed-rates
    |
Filter-chain loads 96kHz AutoEQ IR (active_96000Hz.wav)
    |
DX5 switches to 96kHz (no resampling on the transport)
```

### Multiple Applications (Simultaneous)
```
High Tide (44.1kHz) + YouTube (48kHz) playing together
    |
PipeWire resamples one stream to match the other
    |
Filter-chain processes combined signal
    |
Note: Not sample-rate-matched, but high-quality resampling (quality=14)
```

## Troubleshooting

### Audio Not Working
```bash
# Check services
systemctl --user status pipewire wireplumber

# Restart
systemctl --user restart pipewire pipewire-pulse wireplumber

# Check logs
journalctl --user -u pipewire -f
journalctl --user -u wireplumber -f
```

### Filter-Chain Not Loading
```bash
# Check PipeWire logs for errors
journalctl --user -u pipewire -n 50 --no-pager | grep -i -E "filter|chain|error|fail"

# Verify LV2 plugin paths
ls /usr/lib/lv2/lsp-plugins.lv2/
ls /usr/lib/lv2/ZaMaximX2.lv2/

# Check if LV2_PATH is set
echo $LV2_PATH
# If empty, add to ~/.profile: export LV2_PATH="/usr/lib/lv2"
```

### Sample Rate Not Switching
```bash
# Verify DAC capabilities
cat /proc/asound/card0/stream0

# Check active nodes
pw-cli list-objects | grep -A 10 "alsa_output.usb-Topping_DX5"
```

### Xruns After headroom=0
If you hear clicks/pops, increase headroom incrementally:
```bash
# Edit 51-topping-dx5-bitperfect.lua
# Change: ["api.alsa.headroom"] = 256,
# Then: systemctl --user restart pipewire wireplumber
```

### Reset to Defaults
```bash
rm -rf ~/.config/pipewire ~/.config/wireplumber
systemctl --user restart pipewire wireplumber
```

## Prerequisites (Ubuntu)

```bash
# Required packages
sudo apt install lsp-plugins-lv2 zam-plugins bs2b-ladspa

# RT scheduling
sudo groupadd -f pipewire
sudo usermod -aG pipewire $USER
# Then reboot for group change to take effect

# Recommended kernel parameter
# Add 'threadirqs' to GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub
# Then: sudo update-grub && sudo reboot
```

See `SETUP-UBUNTU.md` for detailed step-by-step Ubuntu setup instructions.

## Technical Details

### Sample Rates
The Topping DX5 supports:
- **CD Family**: 44100, 88200, 176400 Hz
- **DVD Family**: 48000, 96000, 192000 Hz
- **Ultra Hi-Res**: 352800, 384000, 705600, 768000 Hz

### Bit Depth
- **Source**: 16-bit (CD), 24-bit (hi-res), 32-bit (studio)
- **PipeWire Internal**: 32-bit float (lossless processing)
- **DAC Output**: S32LE (25-bit effective precision via PipeWire 1.4+ F32-to-S32 path)

### Why S32LE Instead of S24LE
PipeWire 1.4+ introduced an optimized F32-to-S32 conversion path with 25-bit precision, versus only 17-bit precision in the F32-to-S24 path. S32LE is strictly better for DACs that support it, and the DX5 does.

## Resources

- **PipeWire Wiki**: https://wiki.archlinux.org/title/PipeWire
- **WirePlumber Docs**: https://pipewire.pages.freedesktop.org/wireplumber/
- **AutoEQ**: https://github.com/jaakkopasanen/AutoEq
- **ASH Impulse Responses**: https://github.com/ShanonPearce/ASH-Impulse-Response
- **Topping DX5 Specs**: Up to 32-bit/768kHz PCM, DSD512
