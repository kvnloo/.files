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

      -- Low-latency ALSA settings
      ["api.alsa.period-size"] = 256,
      ["api.alsa.headroom"] = 1024,

      -- Keep memory-mapped I/O and batch mode for efficiency
      ["api.alsa.disable-mmap"] = false,
      ["api.alsa.disable-batch"] = false,
    },
  },
}

-- Note: Sample rate switching is controlled by pipewire.conf
-- (default.clock.allowed-rates), not here. This prevents conflicts
-- with the card profile system.
