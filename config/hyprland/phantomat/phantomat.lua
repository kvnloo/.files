-- Phantomat (Hyprland plugin "spatialoverview") for the native Lua config.
-- NOT required by hyprland.lua. To activate once the Lua config is the live
-- one, add as the LAST line of config/hyprland/hyprland.lua (after lua.binds,
-- whose keys this file replaces):
--
--   require("phantomat.phantomat")
--
-- Adapted from upstream examples/spatialoverview.lua to this desktop's keys;
-- the legacy counterpart is phantomat.legacy.conf. Built for Hyprland 0.56.2
-- (efb50993). UNVERIFIED: never parsed by a running Hyprland.

local home = os.getenv("HOME") or error("phantomat: HOME is unset")
local plugin_path = os.getenv("HYPR_LUA_PHANTOMAT_PLUGIN") or (home .. "/.local/share/hyprland/plugins/phantomat/spatialoverview.so")

-- The parity/e2e harnesses load their own plugin set.
if os.getenv("HYPR_LUA_TEST_MODE") == "1" then
  return
end

hl.plugin.load(plugin_path)

-- On the first pass Hyprland has only been told to load the plugin; it parses
-- the config again once the plugin is in. Without the plugin (for example
-- right after a Hyprland update, before a rebuild) nothing below applies and
-- every key keeps the binding from lua/binds.lua.
local loaded = false
for _, plugin in ipairs(hl.get_loaded_plugins()) do
  if plugin.name == "spatialoverview" then
    loaded = true
    break
  end
end
if not loaded then
  return
end

local so = hl.plugin.spatialoverview

hl.config({
  plugin = {
    spatialoverview = {
      layout = "grid",
      scale = 0.36,
      workspace_gap = 0,
      animation = { enabled = true, speed = 8.0, bezier = "spatialOverviewEase" },
      distortion = { enabled = true, strength = 0.14, edge_scale = 1.08, feather = 0.025 },
      canvas = {
        enabled = true,
        desktop_mode = true,
        persistent = true,
        -- One desk across all outputs (upstream default). DP-2 is rotated and
        -- a headless output comes and goes here; false gives each screen its
        -- own camera.
        linked_screens = true,
        places = false,
        initial_zoom = 0.72,
        min_zoom = 0.05,
        max_zoom = 2.5,
        zoom_step = 0.12,
        auto_float = true,
        auto_place = true,
        placement_gap = 40,
        space_pan = false,
        direct_input = true,
        hover_focus = true,
        minimap_enabled = true,
        grid_enabled = true,
        grid_size = 80,
        grid_style = 1,
        background_dim = 0.35,
        snap_enabled = true,
        remember_layout = true,
      },
      navigator = {
        enabled = true,
        labels = true,
        pointer = true,
        accent = "auto", -- follow the active border (pywal)
        mono_font = "JetBrainsMono Nerd Font",
      },
      parallax = { enabled = true, strength = 0.06, depth = 0.12, desktop = false },
      -- Exact layer-namespace match; Noctalia's are per output, so off.
      chrome_animation = { enabled = false },
      wallpaper = 0,
      blur = false,
    },
  },
})

hl.curve("spatialOverviewEase", { type = "bezier", points = { { 0.22, 1.0 }, { 0.36, 1.0 } } })

-- Values changed with the live tuner (CTRL + , in the zoomed-out canvas) win.
if so.tuning_file then
  local ok, tuned = pcall(dofile, so.tuning_file())
  if ok and type(tuned) == "table" then
    local tree = {}
    for key, value in pairs(tuned) do
      local node, parts = tree, {}
      for part in string.gmatch(key, "[^:]+") do
        parts[#parts + 1] = part
      end
      for i = 1, #parts - 1 do
        node[parts[i]] = node[parts[i]] or {}
        node = node[parts[i]]
      end
      node[parts[#parts]] = value
    end
    hl.config({ plugin = { spatialoverview = tree } })
  end
end

-- The canvas: zoom out and search; again goes back. The first press of a
-- session creates it and floats every window onto it.
hl.bind("SUPER + CTRL + G", function()
  so.overview("toggle all")
end)

-- Three-finger swipe down was the one unused 3/4-finger direction.
so.gesture({ fingers = 3, direction = "down", action = "overview" })

-- The canvas action while a canvas is open, the key's original dispatcher
-- otherwise.
local function canvas_or(action, dispatcher, arg)
  return function()
    if not pcall(so.canvas, action) then
      hl.dispatch(hl.dsp.exec_raw(dispatcher, arg or ""))
    end
  end
end

local function rebind(keys, fn, opts)
  hl.unbind(keys)
  hl.bind(keys, fn, opts)
end

local directions = {
  { keys = { "H", "left" }, name = "left", short = "l" },
  { keys = { "J", "down" }, name = "down", short = "d" },
  { keys = { "K", "up" }, name = "up", short = "u" },
  { keys = { "L", "right" }, name = "right", short = "r" },
}
for _, dir in ipairs(directions) do
  for _, key in ipairs(dir.keys) do
    -- Focus the nearest window that way; the camera follows. navigate()
    -- succeeds without a canvas too, so ask the canvas first.
    rebind("SUPER + " .. key, function()
      if pcall(so.canvas, "noop") then
        so.navigate(dir.name)
      else
        hl.dispatch(hl.dsp.exec_raw("movefocus", dir.short))
      end
    end)
    -- Nudge one grid step on the canvas (hold to repeat).
    rebind("SUPER + SHIFT + " .. key, canvas_or("nudge " .. dir.name, "movewindoworgroup", dir.short), { repeating = true })
  end
end

-- Groups do nothing on the canvas: upstream notes a group made there crashes
-- Hyprland when it quits.
rebind("SUPER + W", canvas_or("noop", "togglegroup"))
rebind("SUPER + G", canvas_or("noop", "exec", "$HOME/workspace/.files/scripts/hypr-group-workspace.sh"))

-- Workspaces do nothing on the canvas (canvas.places is off; experimental).
for n = 1, 10 do
  local key = tostring(n % 10)
  rebind("SUPER + " .. key, canvas_or("noop", "workspace", tostring(n)))
  rebind("SUPER + SHIFT + " .. key, canvas_or("noop", "movetoworkspace", tostring(n)))
end

-- New keys, unused before: fill the screen / recent windows on the canvas,
-- toggle floating / cycle off it.
hl.bind("SUPER + T", canvas_or("fill", "togglefloating"))
hl.bind("ALT + Tab", canvas_or("switch next", "cyclenext"), { repeating = true })
hl.bind("ALT + SHIFT + Tab", canvas_or("switch prev", "cyclenext", "prev"), { repeating = true })

-- Left as they are: the 3-finger horizontal workspace swipe and the special
-- workspaces (SUPER + minus / grave, 4-finger down) are untested with the
-- canvas; SUPER + F fullscreen is handled by the plugin per screen.
