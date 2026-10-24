local noctCall = "noctalia msg "
local brightnessControl = os.getenv("HOME") .. "/workspace/.files/scripts/macbook-brightness "

-- 2015 MacBook Pro function row.
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd(brightnessControl .. "display down"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd(brightnessControl .. "display up"),   { locked = true, repeating = true })
hl.bind("F1", hl.dsp.exec_cmd(brightnessControl .. "display down"), { locked = true, repeating = true })
hl.bind("F2", hl.dsp.exec_cmd(brightnessControl .. "display up"),   { locked = true, repeating = true })

hl.bind("XF86LaunchA", hl.dsp.exec_cmd(noctCall .. "window-switcher"),        { locked = true })
hl.bind("XF86LaunchB", hl.dsp.exec_cmd(noctCall .. "panel-toggle launcher"), { locked = true })

hl.bind("XF86KbdBrightnessDown", hl.dsp.exec_cmd(brightnessControl .. "keyboard down"), { locked = true, repeating = true })
hl.bind("XF86KbdBrightnessUp",   hl.dsp.exec_cmd(brightnessControl .. "keyboard up"),   { locked = true, repeating = true })

hl.bind("SUPER + SHIFT + L", hl.dsp.exec_cmd("sleep 0.5 && noctalia msg dpms-off"), { locked = true })

-- Depending on hid_apple fnmode, the media row may arrive as raw F7-F12.
hl.bind("F7",  hl.dsp.exec_cmd(noctCall .. "media previous"), { locked = true })
hl.bind("F8",  hl.dsp.exec_cmd(noctCall .. "media toggle"),   { locked = true })
hl.bind("F9",  hl.dsp.exec_cmd(noctCall .. "media next"),     { locked = true })
hl.bind("F10", hl.dsp.exec_cmd(noctCall .. "volume-mute"),    { locked = true })
hl.bind("F11", hl.dsp.exec_cmd(noctCall .. "volume-down"),    { locked = true, repeating = true })
hl.bind("F12", hl.dsp.exec_cmd(noctCall .. "volume-up"),      { locked = true, repeating = true })

-- Host delta kept off the shared binds file. Shared config uses Super+W for
-- the browser; this laptop keeps vim focus, Super+B browser, and tab groups.
hl.bind("SUPER + H", hl.dsp.focus({ direction = "left" }))
hl.bind("SUPER + K", hl.dsp.focus({ direction = "up" }))
hl.bind("SUPER + B", hl.dsp.exec_cmd("uwsm app -- firefox"))
hl.bind("SUPER + ALT + W", hl.dsp.group.toggle())
hl.bind("SUPER + G", hl.dsp.exec_cmd(os.getenv("HOME") .. "/workspace/.files/scripts/hypr-group-workspace.sh"))
hl.bind("SUPER + bracketright", hl.dsp.group.next())
hl.bind("SUPER + bracketleft", hl.dsp.group.prev())
hl.bind("SUPER + SHIFT + G", hl.dsp.window.move({ out_of_group = true }))
hl.bind("SUPER + SHIFT + H", hl.dsp.window.move({ direction = "l", group_aware = true }))
hl.bind("SUPER + SHIFT + J", hl.dsp.window.move({ direction = "d", group_aware = true }))
hl.bind("SUPER + SHIFT + K", hl.dsp.window.move({ direction = "u", group_aware = true }))
hl.bind("SUPER + SHIFT + A", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.local/bin/agent-seat toggle"))
