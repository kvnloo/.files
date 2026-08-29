local home = os.getenv("HOME")
local hyprglass_plugin = os.getenv("HYPR_LUA_PLUGIN") or (home .. "/.local/share/hyprland/plugins/hyprglass/hyprglass.so")

local hyprglass={
  enabled=false,
  default_theme="dark",
  default_preset="flow",
  layers={enabled=false,preset="flow"},
}

if os.getenv("HYPR_LUA_TEST_MODE") ~= "1" or os.getenv("HYPR_LUA_ISOLATED_MODE") == "1" then
  -- Plugin keys only exist after the shared object has registered them.
  hl.plugin.load(hyprglass_plugin)
  hl.on("hyprland.start", function()
    local hg=hl.plugin.hyprglass
    if not hg then error("hyprglass Lua API unavailable after plugin load") end
    hg.config(hyprglass)
    hg.preset("flow", {
      blur_strength=1.10, blur_iterations=2, refraction_strength=0.42,
      chromatic_aberration=0.18, fresnel_strength=0.46,
      specular_strength=0.52, glass_opacity=0.88,
      edge_thickness=0.045, lens_distortion=0.30,
      dark={brightness=0.88,contrast=0.96,saturation=0.92,vibrancy=0.18,adaptive_dim=0.20},
    })
    hg.layer("waybar", {preset="flow",mask_threshold=0.05})
  end)
end

hl.config({
  input = { kb_layout="us", follow_mouse=1, sensitivity=0, accel_profile="flat", touchpad={ natural_scroll=true } },
  general = { gaps_in=18, gaps_out=8, border_size=4, col={ active_border={colors={"rgba(75A4CDff)","rgba(BE78D1ff)"},angle=45}, inactive_border="rgba(2f343faa)" }, layout="dwindle", allow_tearing=false },
  group = { groupbar={ height=30, font_size=12, font_family="JetBrainsMono Nerd Font", font_weight_active=600, font_weight_inactive=450, gradients=true, blur=true, rounding=12, rounding_power=2, text_padding=10, indicator_gap=2, indicator_height=2, gaps_in=6, gaps_out=8, gradient_rounding=12, gradient_round_only_edges=true } },
  decoration = { rounding=12, active_opacity=1.0, inactive_opacity=0.95, shadow={enabled=true, range=12, offset="-12 -12", render_power=3, color="rgba(00000080)"}, blur={enabled=true,size=6,passes=2,new_optimizations=true,ignore_opacity=true,noise=0.015,vibrancy=0.22,contrast=0.9,brightness=0.85} },
  animations={enabled=true},
  dwindle={preserve_split=true,force_split=2}, master={new_status="master"},
  gestures={workspace_swipe_distance=300,workspace_swipe_create_new=true},
  misc={force_default_wallpaper=0,disable_hyprland_logo=true,disable_splash_rendering=true},
})

-- Nested migration tests run on Xvfb and must not spawn a second Xwayland.
if os.getenv("HYPR_LUA_TEST_MODE") == "1" then
  hl.config({xwayland={enabled=false}})
end

hl.device({name="trackpad", accel_profile="adaptive"})
hl.device({name="pen-passthrough", output="PHONE"})
hl.device({name="touch-passthrough", output="PHONE"})

hl.curve("smoothOut", {type="bezier",points={{0.36,0},{0.66,-0.56}}})
hl.curve("smoothIn", {type="bezier",points={{0.25,1},{0.5,1}}})
hl.curve("overshot", {type="bezier",points={{0.4,0.8},{0.2,1.2}}})
hl.animation({leaf="windows",enabled=true,speed=5,bezier="overshot",style="slide"})
hl.animation({leaf="windowsOut",enabled=true,speed=4,bezier="smoothOut",style="slide"})
hl.animation({leaf="windowsMove",enabled=true,speed=4,bezier="smoothIn",style="slide"})
hl.animation({leaf="border",enabled=true,speed=10,bezier="default"})
hl.animation({leaf="borderangle",enabled=true,speed=40,bezier="default",style="loop"})
hl.animation({leaf="fade",enabled=true,speed=5,bezier="smoothIn"})
hl.animation({leaf="fadeDim",enabled=true,speed=5,bezier="smoothIn"})
hl.animation({leaf="workspaces",enabled=true,speed=6,bezier="overshot",style="slidevert"})

-- Pywal ownership: read its JSON palette directly, never source hyprlang.
local colors = home .. "/.cache/wal/colors.json"
local f = io.open(colors, "r")
if f then
  local body=f:read("*a"); f:close()
  local palette={}
  for hex in body:gmatch('"color%d+"%s*:%s*"#([0-9A-Fa-f]+)"') do table.insert(palette,hex) end
  if #palette >= 6 then hl.config({general={col={active_border={colors={"rgba("..palette[5].."ff)","rgba("..palette[6].."ff)"},angle=45}}}}) end
end
