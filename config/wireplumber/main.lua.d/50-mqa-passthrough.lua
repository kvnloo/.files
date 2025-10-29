-- MQA Passthrough Attempt for PipeWire
--
-- IMPORTANT: This configuration may NOT fully enable MQA hardware decoding.
--
-- The fundamental issue:
-- - MQA requires bit-identical passthrough of the encoded stream
-- - PipeWire converts ALL audio to 32-bit float internally for processing
-- - This conversion destroys the MQA encoding signature
-- - Your DAC can't recognize the MQA stream after PipeWire processes it
--
-- Current status:
-- ✅ ALSA exclusive mode: MQA works (bypasses all processing)
-- ❌ PipeWire mode: MQA doesn't work (converts to 32-bit float, then back to PCM)
--
-- This configuration attempts to minimize format conversion, but may not be sufficient
-- for full MQA passthrough due to PipeWire's architecture.

alsa_monitor.rules = {
  {
    matches = {
      {
        -- Match Topping DX5 specifically
        { "node.name", "matches", "alsa_output.usb-Topping_DX5*" },
      },
    },
    apply_properties = {
      -- Try to preserve input format (may not prevent internal 32-bit float conversion)
      -- MQA is typically delivered as S16LE (16-bit) or S24LE (24-bit)
      ["audio.format"] = "S16LE",  -- Force 16-bit input/output

      -- Alternative: Try S24LE if MQA tracks are 24-bit
      -- ["audio.format"] = "S24LE",

      -- Disable all audio processing that might touch the stream
      ["channelmix.normalize"] = false,
      ["channelmix.mix-lfe"] = false,
      ["channelmix.upmix"] = false,
      ["channelmix.disable"] = true,

      -- No resampling
      ["resample.quality"] = 0,
      ["resample.disable"] = true,

      -- Attempt passthrough mode
      ["audio.passthrough"] = true,
    },
  },
}

-- ============================================================================
-- RECOMMENDED APPROACH: Use ALSA Exclusive Mode for MQA
-- ============================================================================
--
-- For reliable MQA hardware decoding, configure High Tide to use:
-- • Audio Backend: ALSA (exclusive mode)
-- • This bypasses PipeWire entirely
-- • MQA streams reach your DAC untouched
--
-- Trade-offs:
-- ✅ MQA hardware decoding works
-- ❌ No simultaneous multi-app audio (ALSA locks the device)
-- ❌ Manual switching between apps
--
-- For everyday listening (non-MQA):
-- • Use PipeWire mode for multi-app support and convenience
-- • FLAC hi-res quality is actually better than MQA anyway
--
-- ============================================================================

-- NOTE: If this configuration causes audio issues, delete this file and
-- restart WirePlumber. PipeWire's architecture makes true MQA passthrough
-- extremely difficult without bypassing it entirely (ALSA exclusive mode).
