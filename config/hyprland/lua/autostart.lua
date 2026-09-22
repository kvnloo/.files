local home=os.getenv("HOME")
if os.getenv("HYPR_LUA_TEST_MODE") == "1" or os.getenv("HYPR_LUA_ISOLATED_MODE") == "1" then return end
hl.on("hyprland.start", function()
  for _,cmd in ipairs({
    home.."/workspace/.files/scripts/bar-mode.sh restore",
    home.."/workspace/.files/scripts/wallpaper-mode.sh restore",
    "/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1",
    home.."/workspace/.files/scripts/kdeconnect-tailnet.py --start",
    "warp-terminal --class scratch_term",
    "wl-paste --type text --watch cliphist store",
    "wl-paste --type image --watch cliphist store",
    "env GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb WAYLAND_DISPLAY= rustdesk",
  }) do hl.exec_cmd(cmd) end
end)
