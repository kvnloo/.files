from kitty.boss import get_boss
from kitty.fast_data_types import Screen, get_options
from kitty.tab_bar import DrawData, ExtraData, TabBarData, as_rgb, draw_title
from kitty.utils import color_as_int


def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_tab_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    opts = get_options()
    bg = screen.cursor.bg
    default_bg = as_rgb(int(draw_data.default_bg))

    if is_last and not tab.is_active:
        active_bg = as_rgb(color_as_int(opts.active_tab_background))
    else:
        active_bg = default_bg

    if tab.is_active:
        tab_bg = as_rgb(color_as_int(opts.active_tab_background))
        tab_fg = as_rgb(color_as_int(opts.active_tab_foreground))
    else:
        tab_bg = as_rgb(color_as_int(opts.inactive_tab_background))
        tab_fg = as_rgb(color_as_int(opts.inactive_tab_foreground))

    # Gap before tab
    if index > 1:
        screen.cursor.bg = default_bg
        screen.draw(" ")

    # Left rounded cap
    screen.cursor.fg = tab_bg
    screen.cursor.bg = default_bg
    screen.draw("\ue0b6")  #

    # Tab content
    screen.cursor.bg = tab_bg
    screen.cursor.fg = tab_fg
    title = f" {index}: {tab.title} "
    if len(title) > max_tab_length:
        title = title[: max_tab_length - 1] + "\u2026"
    screen.draw(title)

    # Right rounded cap
    screen.cursor.fg = tab_bg
    screen.cursor.bg = default_bg
    screen.draw("\ue0b4")  #

    return screen.cursor.x
