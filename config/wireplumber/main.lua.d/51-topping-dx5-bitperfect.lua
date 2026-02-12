-- Topping DX5 Bit-Perfect Audio Configuration
-- Applies properties to the DX5 sink node AFTER WirePlumber creates it.
-- Companion to pipewire.conf (which controls allowed-rates and default rate).

alsa_monitor.rules = {
  {
    matches = {
      {
        -- Match the DX5 sink node (not the card/device)
        { "node.name", "matches", "alsa_output.usb-Topping_DX5*" },
      },
    },
    apply_properties = {
      -- Session priority: DX5 is the preferred output
      ["priority.session"] = 2000,

      -- Node description (shown in audio apps)
      ["node.description"] = "Topping DX5 (Bit-Perfect)",

      -- Force S32LE output format for maximum precision
      -- PipeWire 1.4+ uses 25-bit precision F32↔S32 path (vs 17-bit with S24LE)
      ["audio.format"] = "S32LE",

      -- Best-quality resampler (longest sinc filter, minimal aliasing)
      -- Resampling occurs during rate transitions and EasyEffects mismatches;
      -- quality=0 was WORST quality, not bypass. 14 = best available.
      ["resample.quality"] = 14,

      -- ALSA buffer settings for smooth sample rate switching
      -- Start delay: DAC clock-lock time before audio begins (in samples)
      --   @ 44.1kHz: 12288 = 278ms | @ 192kHz: 12288 = 64ms
      ["api.alsa.start-delay"] = 12288,

      -- Period size: samples per hardware interrupt
      ["api.alsa.period-size"] = 1024,

      -- Headroom: extra buffer before underruns
      -- DX5 is a stable async USB DAC; 4096 added ~21ms unnecessary latency.
      -- Start at 0, increase to 256 only if xruns occur.
      ["api.alsa.headroom"] = 0,

      -- Disable software volume/channel mixing (passthrough to hardware)
      ["channelmix.normalize"] = false,

      -- Never suspend: avoids reopening delays on the USB DAC
      ["session.suspend-timeout-seconds"] = 0,

      -- Keep ALSA reservation active (prevents release/reacquire)
      ["api.alsa.disable-reserve"] = false,

      -- Memory-mapped I/O and batch mode for efficiency
      ["api.alsa.disable-mmap"] = false,
      ["api.alsa.disable-batch"] = false,
    },
  },
}
