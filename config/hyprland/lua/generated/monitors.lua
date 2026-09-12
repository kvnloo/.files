-- Generated from persist-monitor-layout monitors.conf by build-hypr-lua-generated-monitors.
-- Not sourced by live hyprland.legacy.conf; do not hand-edit monitors.conf.
-- Do not apply at startup (legacy does not source this file).
local function apply_generated_monitors()
  hl.monitor({ output="DP-1", mode="1920x1080@60", position="6480x0", scale=1 })
  hl.monitor({ output="DP-2", mode="1920x1080@60", position="8400x0", scale=1 })
  hl.monitor({ output="", mode="preferred", position="auto", scale=1 })
end
return { apply = apply_generated_monitors, sourced = false }
