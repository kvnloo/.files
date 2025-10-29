# PipeWire Bit-Perfect Audio Configuration

This directory contains PipeWire and WirePlumber configuration for bit-perfect audio playback with the **Topping DX5** USB DAC.

## Overview

This setup enables:
- ✅ **Bit-perfect audio playback** with automatic sample rate matching
- ✅ **Multi-application support** (High Tide, Spotify, YouTube, system sounds)
- ✅ **Automatic DAC configuration** matching source material (44.1kHz, 48kHz, 88.2kHz, 96kHz, 176.4kHz, 192kHz)
- ✅ **No exclusive ALSA locking** - all applications can access the DAC simultaneously

## Configuration Files

### `pipewire/pipewire.conf`
Core PipeWire configuration with:
- **default.clock.rate**: 192000 (high-resolution default)
- **default.clock.allowed-rates**: All standard sample rates from CD quality (44.1kHz) to hi-res (192kHz)

### `wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua`
Topping DX5 specific configuration with:
- **24-bit audio format** (S24LE) for optimal quality
- **Passthrough mode** for bit-perfect playback
- **Dynamic sample rate switching** to match source material
- **Low-latency ALSA settings** (256 sample period size)

## Installation

### 1. Symlink Configuration Files

```bash
# From the dotfiles repository root
ln -sf "$(pwd)/config/pipewire" ~/.config/pipewire
ln -sf "$(pwd)/config/wireplumber" ~/.config/wireplumber
```

**Or** if you prefer individual file symlinks:
```bash
mkdir -p ~/.config/pipewire ~/.config/wireplumber/main.lua.d
ln -sf "$(pwd)/config/pipewire/pipewire.conf" ~/.config/pipewire/pipewire.conf
ln -sf "$(pwd)/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua" \
       ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua
```

### 2. Restart PipeWire Services

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### 3. Verify Services are Running

```bash
systemctl --user status pipewire pipewire-pulse wireplumber
```

## Verification

### Check Bit-Perfect Playback

Use `pw-top` to monitor real-time sample rates:

```bash
pw-top
```

**What to look for:**
- Find the row for your Topping DX5 (`alsa_output.usb-Topping_DX5`)
- Check the **RATE** column:
  - Playing 44.1kHz FLAC → Should show **44100**
  - Playing Spotify (44.1kHz) → Should show **44100**
  - Playing YouTube (48kHz) → Should show **48000**
  - Playing 96kHz hi-res → Should show **96000**

**If RATE matches source = bit-perfect playback ✅**

### Using the Verification Script

```bash
scripts/verify-bitperfect-audio.sh
```

This script will:
- Check if PipeWire services are running
- Display current sample rate for the Topping DX5
- Show active audio streams
- Provide troubleshooting tips

## Application Configuration

### High Tide (Tidal Client)
1. Open High Tide settings
2. Change **Audio Backend** from `ALSA` to `Automatic` or `PipeWire`
3. This releases exclusive ALSA access
4. Note: Gapless playback may have issues with PipeWire in current versions

### Spotify
- No configuration needed
- Spotify automatically uses PipeWire through PulseAudio compatibility
- Runs at 44.1kHz (Ogg Vorbis 320kbps max quality)
- Enable "High Quality Streaming" in Spotify settings

### YouTube (Browser)
- No configuration needed
- Browsers automatically use PipeWire
- YouTube typically uses 48kHz AAC/Opus audio

## How It Works

### Single Application (Bit-Perfect)
```
High Tide plays 96kHz FLAC
    ↓
PipeWire detects 96000 in allowed-rates
    ↓
DX5 supports 96kHz
    ↓
PipeWire sets DAC to 96kHz (no resampling)
    ↓
✅ Bit-perfect playback
```

### Multiple Applications (Sequential)
```
High Tide plays 44.1kHz → DAC at 44.1kHz (bit-perfect)
    ↓ pause High Tide
YouTube plays 48kHz → DAC switches to 48kHz (bit-perfect)
    ↓ pause YouTube
High Tide resumes → DAC switches back to 44.1kHz (bit-perfect)
```

### Multiple Applications (Simultaneous)
```
High Tide (44.1kHz) + YouTube (48kHz) playing together
    ↓
PipeWire must choose one rate and resample the other
    ↓
⚠️ Not strictly bit-perfect, but higher quality than ALSA blocking
```

## Advantages Over ALSA Exclusive Mode

| Feature | ALSA Exclusive | PipeWire |
|---------|---------------|----------|
| Multiple apps | ❌ Blocked | ✅ Simultaneous |
| Auto rate switching | ❌ Manual | ✅ Automatic |
| Bit-perfect (single app) | ✅ Yes | ✅ Yes |
| Bit-perfect (multi-app) | N/A | ⚠️ Limited* |
| User experience | 🔴 Frustrating | 🟢 Seamless |

*When apps play different sample rates simultaneously, some resampling may occur.

## Troubleshooting

### Audio Not Working
```bash
# Check if services are running
systemctl --user status pipewire wireplumber

# Restart services
systemctl --user restart pipewire pipewire-pulse wireplumber

# Check for errors
journalctl --user -u pipewire -f
journalctl --user -u wireplumber -f
```

### Sample Rate Not Switching
```bash
# Verify DAC capabilities
cat /proc/asound/card0/stream0

# Check active nodes
pw-cli list-objects | grep -A 10 "alsa_output.usb-Topping_DX5"

# Check current properties
pw-cli info [node-id]
```

### Reset to Defaults
```bash
# Remove custom configurations
rm ~/.config/pipewire/pipewire.conf
rm -rf ~/.config/wireplumber/main.lua.d

# Restart services
systemctl --user restart pipewire wireplumber
```

## Technical Details

### Sample Rates

The **Topping DX5** supports an impressive range of sample rates:

- **CD Family**: 44100 Hz, 88200 Hz, 176400 Hz (multiples of 44.1kHz)
- **DVD Family**: 48000 Hz, 96000 Hz, 192000 Hz (multiples of 48kHz)
- **Ultra Hi-Res**: 352800 Hz, 384000 Hz, 705600 Hz, 768000 Hz (DSD128/256 equivalent)

All these rates are configured in both `pipewire.conf` and the WirePlumber rule file.

#### Dynamic Rate Detection

Instead of hardcoding sample rates, you can configure PipeWire to **auto-detect** supported rates from ALSA:

**In `wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua`:**
```lua
-- Set to empty string to auto-detect from ALSA
["audio.allowed-rates"] = "",
```

**Pros:**
- Automatically uses all rates your DAC supports
- No need to update config if you change DACs
- Always up-to-date with hardware capabilities

**Cons:**
- Less explicit control over which rates are allowed
- May enable rates you don't intend to use
- Slightly less predictable behavior

**Recommendation:** Explicit listing (current configuration) provides better control for audiophile use cases.

### Bit Depth
- **Source**: 16-bit (CD), 24-bit (hi-res), 32-bit (studio)
- **PipeWire Internal**: 32-bit float (lossless processing)
- **DAC Output**: 24-bit (S24LE) - optimal for DX5 hardware

Conversion from 16/24-bit to 32-bit float and back to 24-bit is mathematically lossless (bit-perfect).

### Passthrough Mode
When enabled, PipeWire:
- Skips unnecessary audio processing
- Passes audio directly to the DAC
- Preserves original bit depth and sample rate
- Provides the shortest audio path for minimal latency

## Resources

- **PipeWire Wiki**: https://wiki.archlinux.org/title/PipeWire
- **WirePlumber Docs**: https://pipewire.pages.freedesktop.org/wireplumber/
- **Topping DX5 Specs**: Supports up to 32-bit/768kHz PCM, DSD512
- **Audiophile Linux Guide**: https://discovery.endeavouros.com/audio/audiophile/

## Notes

- Current configuration optimized for **Topping DX5**
- Modify device matching rules in `51-topping-dx5-bitperfect.lua` for other DACs
- Quantum settings can be adjusted for different latency requirements
- For production music work, consider lower quantum values (128-256)
