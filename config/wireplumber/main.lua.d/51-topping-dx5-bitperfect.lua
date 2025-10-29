-- Topping DX5 Bit-Perfect Audio Configuration (Fixed Version)
-- This configuration applies properties to the DX5 AFTER the card profile
-- creates the sink, ensuring compatibility with WirePlumber's profile system.

alsa_monitor.rules = {
  {
    matches = {
      {
        -- Match the DX5 sink node (not the card/device)
        { "node.name", "matches", "alsa_output.usb-Topping_DX5*" },
      },
    },
    apply_properties = {
      -- Set higher session priority so DX5 is preferred
      ["priority.session"] = 2000,

      -- Node description (shown in audio apps)
      ["node.description"] = "Topping DX5 (Bit-Perfect)",

      -- Disable resampling when rates match (bit-perfect)
      ["resample.quality"] = 0,

      -- ALSA buffer settings for smooth sample rate switching
      -- These settings eliminate stutter when DAC reinitializes at new rate

      -- Start delay: Time for DAC to lock to new clock before audio begins
      -- This is measured in SAMPLES (adaptive to sample rate):
      --   @ 44.1kHz: 12288 samples = 278ms
      --   @ 48kHz:   12288 samples = 256ms
      --   @ 96kHz:   12288 samples = 128ms
      --   @ 192kHz:  12288 samples = 64ms
      ["api.alsa.start-delay"] = 12288,     -- Increased to 50% more time (Option 1 from tuning guide)

      -- Period size: Number of samples per hardware interrupt
      ["api.alsa.period-size"] = 1024,      -- Larger periods = more buffering

      -- Headroom: Additional buffer space before underruns
      ["api.alsa.headroom"] = 4096,         -- Increased for extra safety margin

      -- Disable software volume control (passthrough to hardware)
      ["channelmix.normalize"] = false,

      -- Prevent device suspend to avoid reopening delays
      ["session.suspend-timeout-seconds"] = 0,  -- Never suspend DX5

      -- Keep device reserved even when idle (prevents release/reacquire)
      ["api.alsa.disable-reserve"] = false,     -- Keep reservation active

      -- This creates a "preroll buffer" of silence during sample rate changes
      -- DAC receives silence → locks to new rate → real audio starts smoothly

      -- Keep memory-mapped I/O and batch mode for efficiency
      ["api.alsa.disable-mmap"] = false,
      ["api.alsa.disable-batch"] = false,
    },
  },
}

-- Note: Sample rate switching is controlled by pipewire.conf
-- (default.clock.allowed-rates), not here. This prevents conflicts
-- with the card profile system.
