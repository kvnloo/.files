import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
THEME = REPO / "scripts" / "theme"

spec = importlib.util.spec_from_file_location("theme_manager", REPO / "scripts/theme_manager.py")
tm = importlib.util.module_from_spec(spec)
sys.modules["theme_manager"] = tm
spec.loader.exec_module(tm)

NAMED = """
mode = "dark"
accent = "#7AA2F7"
selection = "#292e42"
muted = "#414868"
background = "#1a1b26"
dark_background = "#13141c"
darker_background = "#0e0e14"
lighter_background = "#24283b"
foreground = "#a9b1d6"
dark_foreground = "#565f89"
bright_foreground = "#c0caf5"
red = "#f7768e"
yellow = "#e0af68"
orange = "#eb927b"
green = "#9ece6a"
cyan = "#449dab"
blue = "#7aa2f7"
magenta = "#ad8ee6"
bright_red = "#ff7a93"
hyprland_active_border = "rgba(f38cecee) rgba(aabbccee) 45deg"
"""

ALACRITTY = """
[colors]
[colors.primary]
background = '#000000'
foreground = '#FFFFFF'
[colors.normal]
black = '#000000'
red = '#c83730'
green = '#66cc33'
yellow = '#cc7833'
blue = '#3387cc'
magenta = '#9933cc'
cyan = '#cccc33'
white = '#FFFFFF'
[colors.bright]
black = '#404040'
red = '#FF6B6B'
[colors.selection]
background = '#73597E'
"""


def theme(*args: str, home: Path, themes: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(THEME), "--home", str(home), "--themes-dir", str(themes), *args],
        capture_output=True, text=True, check=False, env=env,
    )


def tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def named_theme(tmp_path: Path, slug: str = "tokyo-night") -> Path:
    source = tmp_path / "cache" / slug
    (source / "backgrounds").mkdir(parents=True)
    (source / "backgrounds/1.png").write_bytes(b"png")
    (source / "colors.toml").write_text(NAMED)
    (source / "icons.theme").write_text("Yaru-magenta\n")
    (source / "neovim.lua").write_text('return { { "LazyVim/LazyVim", opts = { colorscheme = "tokyonight-night" } } }\n')
    return source


def legacy_theme(tmp_path: Path) -> Path:
    source = tmp_path / "cache" / "omarchy-all-hallows-eve-theme"
    (source / ".git/refs/heads").mkdir(parents=True)
    (source / ".git/HEAD").write_text("ref: refs/heads/master\n")
    (source / ".git/refs/heads/master").write_text("21aa0f7d354aabe7b278117144773a07708db942\n")
    (source / ".git/config").write_text('[remote "origin"]\n\turl = https://example.invalid/hallows\n')
    (source / "alacritty.toml").write_text(ALACRITTY)
    (source / "hyprland.conf").write_text("$activeBorderColor = rgb(9933cc)\ngeneral {\n col.active_border = $activeBorderColor\n}\n")
    (source / "light.mode").write_text("")
    return source


# ---- palette normaliser ---------------------------------------------------

def test_normalise_derives_a_complete_palette_from_background_and_foreground() -> None:
    palette = tm.normalise({"bg": "#101010", "fg": "EEEEEE"}, name="Tiny", slug="tiny")
    assert palette["mode"] == "dark"
    assert set(palette["colors"]) == set(tm.COLOR_KEYS)
    assert len(palette["ansi"]) == 16
    assert all(tm.HEX.fullmatch(value) for value in [*palette["colors"].values(), *palette["ansi"]])
    assert palette["colors"]["background"] == "#101010"
    assert palette["colors"]["foreground"] == "#eeeeee"


def test_normalise_detects_light_mode_and_keeps_text_readable() -> None:
    palette = tm.normalise(
        {"background": "#fafafa", "foreground": "#202020", "muted": "#f0f0f0", "accent": "#ffe000"},
        name="Paper", slug="paper",
    )
    colors = palette["colors"]
    assert palette["mode"] == "light"
    assert tm.contrast(colors["foreground_dim"], colors["background"]) >= 5.0
    assert tm.contrast(colors["on_accent"], colors["accent"]) >= 4.5


def test_normalise_accepts_every_colour_spelling_and_prefers_indexed_colours() -> None:
    assert tm.norm_hex("rgba(F38CECee)") == "#f38cec"
    assert tm.norm_hex("0xff9933cc") == "#9933cc"
    assert tm.norm_hex("#ABC") == "#aabbcc"
    assert tm.norm_hex("rgba(1,2,3,0.5)") is None
    palette = tm.normalise(
        {"background": "#000000", "foreground": "#ffffff", "color1": "#aa0000", "red": "#ff0000",
         "color8": "#555555"},
        name="X", slug="x",
    )
    assert palette["colors"]["red"] == "#ff0000"   # named colour wins for the semantic role
    assert palette["ansi"][1] == "#aa0000"         # indexed colour wins for the terminal slot
    assert palette["ansi"][8] == "#555555"


def test_normalise_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="no foreground"):
        tm.normalise({"background": "#000000"}, name="X", slug="x")
    with pytest.raises(ValueError, match="invalid theme slug"):
        tm.normalise({"background": "#000000", "foreground": "#ffffff"}, name="X", slug="../x")


def test_palette_file_round_trips(tmp_path: Path) -> None:
    palette = tm.normalise(tomllib.loads(NAMED), name="Tokyo Night", slug="tokyo-night", mode="dark")
    palette["extras"] = {"icon_theme": "Yaru-magenta"}
    palette["overrides"] = {"noctalia": {"mHover": "#123456"}}
    path = tmp_path / "palette.toml"
    path.write_text(tm.dump_palette(palette))
    assert tm.load_palette(path) == palette
    assert tm.noctalia_scheme(palette)["mHover"] == "#123456"


# ---- the two Omarchy import formats ----------------------------------------

def test_import_colors_toml_format(tmp_path: Path) -> None:
    themes = tmp_path / "themes"
    record = tm.import_theme(named_theme(tmp_path), themes)
    palette = tm.load_palette(themes / "tokyo-night/palette.toml")
    assert record["format"] == "omarchy-colors-toml"
    assert record["commit"] is None and record["url"] is None
    assert palette["mode"] == "dark"
    assert palette["colors"]["accent"] == "#7aa2f7"
    assert palette["colors"]["surface"] == "#24283b"
    assert palette["colors"]["selection_background"] == "#292e42"
    assert palette["ansi"][0] == "#13141c" and palette["ansi"][8] == "#414868"
    assert palette["ansi"][9] == "#ff7a93" and palette["ansi"][10] == "#9ece6a"
    assert palette["extras"]["icon_theme"] == "Yaru-magenta"
    assert palette["extras"]["nvim_colorscheme"] == "tokyonight-night"
    assert palette["extras"]["wallpapers"].endswith("tokyo-night/backgrounds")
    assert tm.nvim_choice(palette, {"tokyonight.nvim"})[:2] == ("tokyonight-night", True)
    assert tm.nvim_choice(palette, set())[:2] == ("tokyonight", False)


def test_import_legacy_format_reads_provenance_without_running_git(tmp_path: Path) -> None:
    themes = tmp_path / "themes"
    record = tm.import_theme(legacy_theme(tmp_path), themes)
    assert record["slug"] == "all-hallows-eve"
    assert record["format"] == "omarchy-legacy"
    assert record["url"] == "https://example.invalid/hallows"
    assert record["commit"] == "21aa0f7d354aabe7b278117144773a07708db942"
    palette = tm.load_palette(themes / "all-hallows-eve/palette.toml")
    assert palette["mode"] == "light"               # light.mode marker beats luminance
    assert palette["colors"]["accent"] == "#9933cc"  # from hyprland.conf, as text
    assert palette["colors"]["red"] == "#c83730"
    assert palette["ansi"][8] == "#404040" and palette["ansi"][9] == "#ff6b6b"
    assert palette["ansi"][10] == "#66cc33"         # missing bright falls back to normal
    lock = json.loads((themes / "themes.lock.json").read_text())
    assert lock["all-hallows-eve"]["commit"] == record["commit"]


def test_import_is_idempotent_and_never_executes_theme_files(tmp_path: Path) -> None:
    source = named_theme(tmp_path)
    marker = tmp_path / "executed"
    (source / "install.sh").write_text(f"#!/bin/sh\ntouch {marker}\n")
    (source / "install.sh").chmod(0o755)
    (source / "neovim.lua").write_text(f'os.execute("touch {marker}")\nreturn {{ colorscheme = "tokyonight-night" }}\n')
    themes, home = tmp_path / "themes", tmp_path / "home"
    env = {**os.environ, "THEME_IMPORT_CACHE": str(tmp_path / "cache")}
    first = theme("import", "--all", home=home, themes=themes, env=env)
    assert first.returncode == 0, first.stderr
    before = tree(themes)
    second = theme("import", "tokyo-night", home=home, themes=themes, env=env)
    assert second.returncode == 0, second.stderr
    assert tree(themes) == before
    assert not marker.exists()
    assert not home.exists()                        # import writes nothing under the home


def test_import_reports_unusable_theme(tmp_path: Path) -> None:
    (tmp_path / "cache/empty").mkdir(parents=True)
    result = theme("import", str(tmp_path / "cache/empty"), home=tmp_path / "home", themes=tmp_path / "themes")
    assert result.returncode == 1
    assert "no colors.toml" in result.stderr


# ---- apply ----------------------------------------------------------------

def test_apply_writes_only_the_generated_directory_and_is_idempotent(tmp_path: Path) -> None:
    themes, home = tmp_path / "themes", tmp_path / "home"
    tm.import_theme(named_theme(tmp_path), themes)
    (home / ".config/kitty").mkdir(parents=True)
    (home / ".config/kitty/kitty.conf").write_text("include ~/.cache/wal/colors-kitty.conf\n")

    dry = theme("apply", "tokyo-night", "--dry-run", home=home, themes=themes)
    assert dry.returncode == 0, dry.stderr
    assert "would write" in dry.stdout
    assert not (home / ".local").exists()

    first = theme("apply", "tokyo-night", home=home, themes=themes)
    assert first.returncode == 0, first.stderr
    written = {path for path in tree(home)}
    assert all(path.startswith(".local/state/theme/") or path == ".config/kitty/kitty.conf" for path in written)
    assert (home / ".config/kitty/kitty.conf").read_text() == "include ~/.cache/wal/colors-kitty.conf\n"
    generated = home / ".local/state/theme/generated"
    for name in ("hyprland.conf", "kitty.conf", "alacritty.toml", "rofi.rasi", "dunst.conf", "hyprlock.conf",
                 "waybar.css", "tmux.conf", "btop.theme", "shell.sh", "delta.gitconfig", "gtk3.css", "gtk4.css",
                 "qt6ct.conf", "nvim.lua", "noctalia/Unified/Unified.json", "current.json"):
        assert (generated / name).is_file(), name
    assert json.loads((generated / "noctalia/Unified/Unified.json").read_text())["dark"]["mPrimary"] == "#7aa2f7"
    assert tomllib.loads((generated / "alacritty.toml").read_text())["colors"]["primary"]["background"] == "#1a1b26"

    before = tree(home)
    second = theme("apply", "tokyo-night", home=home, themes=themes)
    assert second.returncode == 0, second.stderr
    assert "wrote" not in second.stdout
    assert tree(home) == before                     # same bytes, same mtimes
    assert "would run" in second.stdout or "wallpaper" not in second.stdout


def test_home_flag_never_runs_live_commands(tmp_path: Path) -> None:
    themes, home = tmp_path / "themes", tmp_path / "home"
    tm.import_theme(named_theme(tmp_path), themes)
    fake = tmp_path / "bin"
    fake.mkdir()
    for tool in ("hyprctl", "qs", "pkill", "dunstctl", "tmux", "rofi", "swaybg", "wal"):
        (fake / tool).write_text(f"#!/bin/sh\necho {tool} \"$@\" >> {tmp_path}/called\n")
        (fake / tool).chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    (home / ".config/kitty").mkdir(parents=True)
    (home / ".config/kitty/kitty.conf").write_text("include ~/.cache/wal/colors-kitty.conf\n")
    assert theme("apply", "tokyo-night", home=home, themes=themes, env=env).returncode == 0
    assert theme("wire", "kitty", home=home, themes=themes, env=env).returncode == 0
    applied = theme("apply", "tokyo-night", home=home, themes=themes, env=env)
    assert "would run: pkill -USR1 -x kitty" in applied.stdout
    assert theme("pick", home=home, themes=themes, env=env).returncode != 0
    assert not (tmp_path / "called").exists()


def test_wire_refuses_before_apply_then_round_trips(tmp_path: Path) -> None:
    themes, home = tmp_path / "themes", tmp_path / "home"
    tm.import_theme(named_theme(tmp_path), themes)
    kitty = home / ".config/kitty/kitty.conf"
    kitty.parent.mkdir(parents=True)
    original = "font_size 12\ninclude ~/.cache/wal/colors-kitty.conf\n"
    kitty.write_text(original)
    (home / ".config/dunst").mkdir()

    refused = theme("wire", "kitty", "dunst", home=home, themes=themes)
    assert refused.returncode == 1 and "generate first" in refused.stdout
    assert kitty.read_text() == original

    assert theme("apply", "tokyo-night", home=home, themes=themes).returncode == 0
    wired = theme("wire", "kitty", "dunst", home=home, themes=themes)
    assert wired.returncode == 0, wired.stdout
    assert kitty.read_text() == "font_size 12\ninclude ~/.local/state/theme/generated/kitty.conf\n"
    link = home / ".config/dunst/dunstrc.d/50-theme.conf"
    assert link.is_symlink() and link.resolve() == (home / ".local/state/theme/generated/dunst.conf").resolve()
    again = theme("wire", "kitty", "dunst", home=home, themes=themes)
    assert again.returncode == 0 and "already wired" in again.stdout

    assert theme("unwire", "kitty", "dunst", home=home, themes=themes).returncode == 0
    assert kitty.read_text() == original
    assert not link.is_symlink()


def test_wallpaper_mode_uses_pywal_palette_as_just_another_source(tmp_path: Path) -> None:
    themes, home = tmp_path / "themes", tmp_path / "home"
    (home / ".cache/wal").mkdir(parents=True)
    (home / ".cache/wal/colors.json").write_text(json.dumps({
        "special": {"background": "#181f23", "foreground": "#d1deda", "cursor": "#d1deda"},
        "colors": {f"color{i}": c for i, c in enumerate(
            ["#181f23", "#678C3E", "#6D8F57", "#99A362", "#C8BE72", "#4FA5B3", "#98B39E", "#d1deda"] * 2)},
    }))
    result = theme("wallpaper-mode", home=home, themes=themes)
    assert result.returncode == 0, result.stderr
    state = json.loads((home / ".local/state/theme/state.json").read_text())
    assert (state["slug"], state["source"]) == ("wallpaper", "wallpaper")
    current = json.loads((home / ".local/state/theme/generated/current.json").read_text())
    assert current["colors"]["background"] == "#181f23"
    assert current["colors"]["accent"] == "#c8be72"
    assert current["colors"]["red"] == "#ff7085"   # alerts stay red whatever the wallpaper
    assert current["ansi"][1] == "#678c3e"         # terminal colours stay the wallpaper's
    assert "wallpaper-mode.sh" not in result.stdout  # the wallpaper itself is left alone


def test_pywal_hook_defers_to_the_theme_manager_once_activated(tmp_path: Path) -> None:
    """apply-pywal-theme.sh must not push wallpaper colours over a fixed theme."""
    themes, home = tmp_path / "themes", tmp_path / "home"
    tm.import_theme(named_theme(tmp_path), themes)
    fake = tmp_path / "bin"
    fake.mkdir()
    for tool in ("wal", "hyprctl", "dunstctl", "pkill", "tmux", "qs", "notify-send"):
        (fake / tool).write_text(f"#!/bin/sh\necho {tool} \"$@\" >> {tmp_path}/called\n")
        (fake / tool).chmod(0o755)
    (home / ".cache/wal").mkdir(parents=True)
    (home / ".cache/wal/colors.json").write_text(json.dumps({
        "special": {"background": "#181f23", "foreground": "#d1deda", "cursor": "#d1deda"},
        "colors": {f"color{i}": "#c8be72" for i in range(16)},
    }))
    (home / ".cache/wal/colors-kitty.conf").write_text("color8       #000000\n")
    (home / ".cache/wal/colors-waybar.css").write_text("@define-color color8 #000000;\n")
    image = tmp_path / "wall.png"
    image.write_bytes(b"png")
    env = {**os.environ, "HOME": str(home), "PATH": f"{fake}:{os.environ['PATH']}", "THEME_NO_LIVE": "1"}
    hook = [str(REPO / "scripts/apply-pywal-theme.sh"), str(image)]

    assert theme("apply", "tokyo-night", home=home, themes=themes, env=env).returncode == 0
    fixed = subprocess.run(hook, capture_output=True, text=True, env=env, check=False)
    assert fixed.returncode == 0, fixed.stderr
    calls = (tmp_path / "called").read_text().splitlines()
    assert [call.split()[0] for call in calls] == ["wal"]           # no hyprctl / dunstctl / pkill
    current = home / ".local/state/theme/generated/current.json"
    assert json.loads(current.read_text())["slug"] == "tokyo-night"

    assert theme("wallpaper-mode", home=home, themes=themes, env=env).returncode == 0
    followed = subprocess.run(hook, capture_output=True, text=True, env=env, check=False)
    assert followed.returncode == 0, followed.stderr
    assert json.loads(current.read_text())["slug"] == "wallpaper"
    calls = (tmp_path / "called").read_text().splitlines()
    assert {call.split()[0] for call in calls} == {"wal"}


def test_every_shipped_palette_loads_and_renders() -> None:
    slugs = sorted(path.parent.name for path in (REPO / "config/themes").glob("*/palette.toml"))
    assert "groot-baseline" in slugs and "tokyo-night" in slugs
    lock = json.loads((REPO / "config/themes/themes.lock.json").read_text())
    assert set(lock) == set(slugs)
    for slug in slugs:
        palette = tm.load_palette(REPO / "config/themes" / slug / "palette.toml")
        assert palette["slug"] == slug
        for component in tm.COMPONENTS:
            assert all(text.endswith("\n") for text in component.render(palette).values())
