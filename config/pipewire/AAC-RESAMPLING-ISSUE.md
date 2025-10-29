# AAC 96kHz Resampling Issue - Investigation Guide

## The Problem

Songs showing "AAC 96kHz" in High Tide are not triggering the DAC to switch to 96kHz. Instead, the audio is being resampled, while FLAC files work correctly for bit-perfect sample rate switching.

## Why This Might Happen

### 1. AAC Decoding at Lower Rate
**Most Likely Cause:** High Tide might be decoding AAC files and outputting them to PipeWire at 48kHz (the default for many decoders), even though the metadata says 96kHz.

AAC is a compressed format, and the decoder determines the output sample rate. High Tide's AAC decoder might:
- Default to 48kHz output regardless of source
- Not support 96kHz AAC decoding
- Have a configuration option limiting AAC output rate

### 2. PipeWire Configuration
**Less Likely:** PipeWire might not be switching rates properly for this specific stream, but since FLAC works, this is unlikely.

### 3. AAC File Metadata vs Actual Content
**Possible:** The file's metadata might say 96kHz, but the actual audio data might be at a different rate.

---

## Diagnostic Process

### Step 1: Use the Diagnostic Script

Run the real-time diagnostic tool while playing the AAC track:

```bash
./scripts/diagnose-stream-rate.sh
```

This will show:
- DAC hardware sample rate (what the DX5 is actually running at)
- PipeWire sink configuration
- Active stream information including the actual rate High Tide is outputting

### Step 2: Interpret the Results

**Scenario A: High Tide outputs 48kHz for AAC**
```
📡 DAC Hardware Rate: 48000
🔧 PipeWire Sink Configuration: s32le 2ch 48000Hz
🎵 Active PipeWire Streams:
  Stream 1: High Tide
    Format: F32 48000Hz
    Playing: [Your AAC track]

✅ DAC and PipeWire rates MATCH - bit-perfect
💡 High Tide is decoding AAC at 48kHz, not 96kHz
```

**This means:** The problem is in High Tide's AAC decoder settings. The metadata says 96kHz, but High Tide is only outputting 48kHz.

**Scenario B: High Tide outputs 96kHz but PipeWire resamples**
```
📡 DAC Hardware Rate: 48000
🔧 PipeWire Sink Configuration: s32le 2ch 48000Hz
🎵 Active PipeWire Streams:
  Stream 1: High Tide
    Format: F32 96000Hz
    Playing: [Your AAC track]

⚠️  DAC rate (48000) != PipeWire rate (48000)
    Stream is 96kHz but being resampled!
```

**This means:** High Tide is correctly outputting 96kHz, but PipeWire isn't switching the DAC. This could indicate a PipeWire configuration issue.

---

## Solutions by Scenario

### Solution A: High Tide AAC Decoder Limitation

If High Tide is decoding AAC at 48kHz:

1. **Check High Tide settings** for AAC output sample rate configuration
2. **Check High Tide audio backend settings** - ensure it's using PipeWire natively
3. **Convert AAC to FLAC** if bit-perfect 96kHz is important for this track:
   ```bash
   ffmpeg -i input.aac -c:a flac -sample_fmt s24 -ar 96000 output.flac
   ```

### Solution B: PipeWire Not Switching for AAC Streams

If High Tide outputs 96kHz but PipeWire doesn't switch:

1. **Check if 96000 is in allowed rates:**
   ```bash
   grep "allowed-rates" ~/.config/pipewire/pipewire.conf
   ```
   Should show: `default.clock.allowed-rates = [ 44100 48000 88200 96000 ... ]`

2. **Restart PipeWire services:**
   ```bash
   systemctl --user restart pipewire wireplumber
   ```

3. **Monitor PipeWire logs during playback:**
   ```bash
   journalctl --user -u pipewire -f
   ```

### Solution C: AAC File Quality Issue

If the AAC file itself is problematic:

1. **Check actual AAC file properties:**
   ```bash
   ffprobe your_file.aac 2>&1 | grep -E "Stream|Audio|sample_rate"
   ```

2. **Compare with a working FLAC:**
   ```bash
   ffprobe working_file.flac 2>&1 | grep -E "Stream|Audio|sample_rate"
   ```

---

## Understanding AAC vs FLAC for Bit-Perfect

### Why FLAC Works Better

| Aspect | FLAC | AAC |
|--------|------|-----|
| **Compression** | Lossless | Lossy |
| **Decoding** | Direct PCM reconstruction | Psychoacoustic decoding |
| **Sample Rate** | Preserved exactly | Decoder-dependent |
| **Bit Depth** | Preserved exactly | Always decoded to float |
| **Bit-Perfect** | ✅ Yes | ❌ No (lossy compression) |

### AAC Decoding Reality

AAC is a **lossy format**, which means:
1. The original audio is compressed using psychoacoustic models
2. Some information is permanently discarded
3. Decoding reconstructs an approximation, not the original

**Even if High Tide outputs 96kHz for an AAC file, it's not "bit-perfect" because:**
- AAC encoding already discarded audio information
- The decoder creates new PCM samples based on the compressed data
- The output is a reconstruction, not the original recording

**Recommendation:** For true bit-perfect audio quality, use lossless formats (FLAC, WAV, ALAC). AAC is fine for convenience, but you're not getting bit-perfect quality anyway due to the lossy compression.

---

## Quick Decision Tree

```
AAC 96kHz not switching DAC rate?
│
├─ Run diagnostic script
│
├─ Does High Tide output 48kHz?
│  ├─ Yes → High Tide AAC decoder limitation
│  │        → Check High Tide settings
│  │        → Consider converting to FLAC
│  │
│  └─ No, outputs 96kHz → PipeWire not switching
│           → Check allowed-rates configuration
│           → Check PipeWire logs
│           → Verify 96000 in pipewire.conf
│
└─ Does it matter for quality?
   └─ AAC is lossy anyway → Not bit-perfect regardless of sample rate
      → Use FLAC for true bit-perfect playback
```

---

## Testing Plan

1. **Run diagnostic** while playing the AAC track
2. **Note the actual output rate** from High Tide
3. **Compare with FLAC** playback of the same track (if available)
4. **Check High Tide settings** for AAC configuration
5. **Report findings** for targeted solution

---

## Expected Outcome

Most likely: High Tide's AAC decoder is outputting 48kHz regardless of the source file's metadata. This is common behavior for AAC decoders, as 48kHz is the standard output rate for video/streaming content.

**If this is important:** Convert the track to FLAC for genuine bit-perfect 96kHz playback. AAC is inherently lossy, so even at 96kHz, you're not getting the full quality anyway.
