-- Dynamic hyprlang sources become explicit Lua bridges / generated artifacts.
-- Runtime helpers (phone-display, gui-e2e) keep hyprctl keyword/dispatch IPC.
local home = os.getenv("HOME") or error("hypr lua bridge: HOME is unset")
local here = debug.getinfo(1, "S").source:gsub("^@", "")

local function missing(kind, path)
  error("hypr lua bridge: " .. kind .. " missing: " .. path)
end

local function load_artifact(path, kind)
  local chunk, err = loadfile(path)
  if not chunk then
    missing(kind, path .. " (" .. tostring(err) .. ")")
  end
  chunk()
end

-- Pywal: generated Lua artifact replaces sourced pywal hyprlang colors
local pywal_path = os.getenv("HYPR_LUA_PYWAL_LUA") or (home .. "/.cache/wal/colors-hyprland.lua")
load_artifact(pywal_path, "pywal generated Lua artifact")
if type(HYPR_PYWAL) ~= "table" or type(HYPR_PYWAL.hyprglass_tint) ~= "string" then
  error("hypr lua bridge: pywal artifact did not set HYPR_PYWAL: " .. pywal_path)
end

-- Liquid-glass: in-tree explicit bridge for liquid-glass.conf
local glass_artifact = os.getenv("HYPR_LUA_LIQUID_GLASS")
  or here:gsub("bridges%.lua$", "generated/liquid_glass.lua")
load_artifact(glass_artifact, "liquid-glass explicit bridge")

-- persist-monitor-layout output is generated, not sourced by live hyprland.
-- Artifact exists for Lua consumers; do not apply at startup.
local monitors_artifact = os.getenv("HYPR_LUA_GENERATED_MONITORS")
  or here:gsub("bridges%.lua$", "generated/monitors.lua")
local monitors_chunk, monitors_err = loadfile(monitors_artifact)
if not monitors_chunk then
  missing("persist-monitor-layout generated Lua artifact", monitors_artifact .. " (" .. tostring(monitors_err) .. ")")
end
