local noctCall = "noctalia msg "
local brightnessControl = os.getenv("HOME") .. "/workspace/.files/scripts/macbook-brightness "

-- 2015 MacBook Pro function row.
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd(brightnessControl .. "display down"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd(brightnessControl .. "display up"),   { locked = true, repeating = true })

hl.bind("XF86LaunchA", hl.dsp.exec_cmd(noctCall .. "window-switcher"),        { locked = true })
hl.bind("XF86LaunchB", hl.dsp.exec_cmd(noctCall .. "panel-toggle launcher"), { locked = true })

hl.bind("XF86KbdBrightnessDown", hl.dsp.exec_cmd(brightnessControl .. "keyboard down"), { locked = true, repeating = true })
hl.bind("XF86KbdBrightnessUp",   hl.dsp.exec_cmd(brightnessControl .. "keyboard up"),   { locked = true, repeating = true })

-- Depending on hid_apple fnmode, the media row may arrive as raw F7-F12.
hl.bind("F7",  hl.dsp.exec_cmd(noctCall .. "media previous"), { locked = true })
hl.bind("F8",  hl.dsp.exec_cmd(noctCall .. "media toggle"),   { locked = true })
hl.bind("F9",  hl.dsp.exec_cmd(noctCall .. "media next"),     { locked = true })
hl.bind("F10", hl.dsp.exec_cmd(noctCall .. "volume-mute"),    { locked = true })
hl.bind("F11", hl.dsp.exec_cmd(noctCall .. "volume-down"),    { locked = true, repeating = true })
hl.bind("F12", hl.dsp.exec_cmd(noctCall .. "volume-up"),      { locked = true, repeating = true })
