#!/usr/bin/env python3
"""Unified desktop theme manager.

One palette per theme (config/themes/<slug>/palette.toml) is rendered into one
generated directory (~/.local/state/theme/generated) that the hand-written
component configs include.  Switching a theme rewrites only that directory and
then asks each wired component to reload.  See docs/theme-manager.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THEMES = ROOT / "config/themes"
DEFAULT_IMPORT_CACHE = Path("/mnt/zer0models/themes/omarchy")
GENERATED_REL = ".local/state/theme/generated"
SCHEME = "Unified"  # name of the generated Noctalia / Kvantum / btop theme
WALLPAPER_SLUG = "wallpaper"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SLUG = re.compile(r"[a-z0-9][a-z0-9.-]*")
HEX = re.compile(r"#[0-9a-f]{6}")

COLOR_KEYS = (
    "background", "background_dim", "surface", "surface_alt",
    "foreground", "foreground_dim", "foreground_bright",
    "accent", "accent_alt", "on_accent",
    "selection_background", "selection_foreground", "cursor", "border",
    "red", "green", "yellow", "blue", "magenta", "cyan", "orange",
)
ANSI_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")


def _load_pywal_sync():
    """Reuse the contrast maths of the existing pywal generator."""
    spec = importlib.util.spec_from_file_location(
        "sync_pywal_theme", ROOT / "scripts/sync-pywal-theme.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pywal = _load_pywal_sync()
contrast = _pywal.contrast
readable = _pywal.readable_muted  # nudges a colour until it reads on a background


# --------------------------------------------------------------------------
# colour helpers
# --------------------------------------------------------------------------

def norm_hex(value: object) -> str | None:
    """Return '#rrggbb' for any of the spellings theme files use, else None."""
    if not isinstance(value, str):
        return None
    text = value.strip().strip("'\"").lower()
    match = re.fullmatch(r"rgba?\(\s*([0-9a-f]{6})(?:[0-9a-f]{2})?\s*\)", text)
    if match:
        return "#" + match.group(1)
    match = re.fullmatch(r"0x(?:[0-9a-f]{2})?([0-9a-f]{6})", text)
    if match:
        return "#" + match.group(1)
    match = re.fullmatch(r"#?([0-9a-f]{6})(?:[0-9a-f]{2})?", text)
    if match:
        return "#" + match.group(1)
    match = re.fullmatch(r"#?([0-9a-f])([0-9a-f])([0-9a-f])", text)
    if match:
        return "#" + "".join(channel * 2 for channel in match.groups())
    return None


def mix(first: str, second: str, ratio: float) -> str:
    a, b = _pywal.rgb(first), _pywal.rgb(second)
    return _pywal.hex_color(tuple(round(x + (y - x) * ratio) for x, y in zip(a, b)))


def best_on(background: str, *candidates: str) -> str:
    """The most readable candidate on ``background``; black/white if none reads."""
    best = max(candidates, key=lambda c: contrast(c, background))
    if contrast(best, background) >= 4.5:
        return best
    return max(("#000000", "#ffffff"), key=lambda c: contrast(c, background))


def strip(value: str) -> str:
    return value.lstrip("#")


def rgb_csv(value: str) -> str:
    return ", ".join(str(channel) for channel in _pywal.rgb(value))


# --------------------------------------------------------------------------
# palette normaliser
# --------------------------------------------------------------------------

ALIASES = {
    "bg": "background", "fg": "foreground",
    "dark_bg": "dark_background", "darker_bg": "darker_background",
    "lighter_bg": "lighter_background", "dark_fg": "dark_foreground",
    "light_fg": "light_foreground", "bright_fg": "bright_foreground",
    "selection": "selection_background",
}


def normalise(raw: dict, *, name: str, slug: str, mode: str | None = None) -> dict:
    """Turn any loose colour mapping into the palette every renderer consumes.

    ``raw`` may carry Omarchy 4.x names (accent, red, bright_red, muted,
    lighter_background ...), indexed terminal colours (color0..color15) or
    both.  Only background and foreground are mandatory; the rest is derived.
    """
    if not SLUG.fullmatch(slug):
        raise ValueError(f"invalid theme slug: {slug!r}")
    src: dict[str, str] = {}
    for key, value in raw.items():
        colour = norm_hex(value)
        if colour:
            src.setdefault(ALIASES.get(key, key), colour)
    for required in ("background", "foreground"):
        if required not in src:
            raise ValueError(f"{slug}: palette has no {required}")
    bg, fg = src["background"], src["foreground"]
    if mode not in ("dark", "light"):
        mode = "dark" if _pywal.luminance(bg) <= _pywal.luminance(fg) else "light"
    dark = mode == "dark"
    edge = "#000000" if dark else "#ffffff"

    def pick(*keys: str, default: str) -> str:
        return next((src[key] for key in keys if key in src), default)

    # Semantic roles prefer named colours; terminal slots prefer indexed ones.
    named, slots = {}, {}
    for index, colour in enumerate(ANSI_NAMES[1:7], start=1):
        named[colour] = pick(colour, f"color{index}", default=mix(fg, bg, 0.3))
        slots[colour] = pick(f"color{index}", default=named[colour])
    muted = pick("dark_foreground", "muted", "color8", default=mix(bg, fg, 0.4))
    ansi = [
        pick("color0", "dark_background", default=mix(bg, "#000000", 0.3)) if dark
        else pick("color0", default=mix(bg, fg, 0.85)),
        *slots.values(),
        pick("color7", default=fg if dark else mix(bg, fg, 0.6)),
        pick("color8", "muted", default=muted),
        *[
            pick(f"color{index + 8}", f"bright_{colour}", default=slots[colour])
            for index, colour in enumerate(ANSI_NAMES[1:7], start=1)
        ],
        pick("color15", "bright_foreground", default=fg),
    ]
    accent = pick("accent", default=named["blue"])
    accent_alt = next(
        (named[c] for c in ("magenta", "cyan", "blue", "green") if named[c] != accent),
        accent,
    )
    selection_bg = pick("selection_background", default=mix(bg, accent, 0.3))
    selection_fg = pick("selection_foreground", default=fg)
    if contrast(selection_fg, selection_bg) < 3:
        selection_fg = best_on(selection_bg, fg, bg)
    colors = {
        "background": bg,
        "background_dim": pick("darker_background", "dark_background", default=mix(bg, "#000000", 0.25 if dark else 0.06)),
        "surface": pick("lighter_background", default=mix(bg, fg, 0.07)),
        "surface_alt": mix(bg, fg, 0.14),
        "foreground": fg,
        "foreground_dim": readable(muted, bg),
        "foreground_bright": pick("bright_foreground", default=fg),
        "accent": accent,
        "accent_alt": accent_alt,
        "on_accent": best_on(accent, bg, fg),
        "selection_background": selection_bg,
        "selection_foreground": selection_fg,
        "cursor": pick("cursor", default=fg),
        "border": mix(bg, fg, 0.25),
        **named,
        "orange": pick("orange", default=mix(named["red"], named["yellow"], 0.5)),
    }
    return validate({"name": name, "slug": slug, "mode": mode, "colors": colors,
                     "ansi": ansi, "extras": {}, "overrides": {}})


def validate(palette: dict) -> dict:
    slug = palette.get("slug", "?")
    if palette.get("mode") not in ("dark", "light"):
        raise ValueError(f"{slug}: mode must be dark or light")
    for key in COLOR_KEYS:
        if not HEX.fullmatch(str(palette["colors"].get(key, ""))):
            raise ValueError(f"{slug}: colors.{key} is not #rrggbb")
    ansi = palette.get("ansi", [])
    if len(ansi) != 16 or not all(HEX.fullmatch(str(value)) for value in ansi):
        raise ValueError(f"{slug}: ansi needs sixteen #rrggbb colours")
    palette.setdefault("extras", {})
    palette.setdefault("overrides", {})
    return palette


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def dump_palette(palette: dict) -> str:
    lines = [
        "# Normalised theme palette: the single source of truth for this theme.",
        "# Written by `theme import`; safe to hand-edit (re-import overwrites).",
        f"name = {_toml_string(palette['name'])}",
        f"slug = {_toml_string(palette['slug'])}",
        f"mode = {_toml_string(palette['mode'])}",
        "",
        "[colors]",
        *[f"{key} = {_toml_string(palette['colors'][key])}" for key in COLOR_KEYS],
        "",
        "[ansi]",
        *[f"color{index} = {_toml_string(value)}" for index, value in enumerate(palette["ansi"])],
    ]
    if palette.get("extras"):
        lines += ["", "[extras]"]
        lines += [f"{key} = {_toml_string(value)}" for key, value in sorted(palette["extras"].items())]
    for component, values in sorted(palette.get("overrides", {}).items()):
        lines += ["", f"[overrides.{component}]"]
        lines += [f"{key} = {_toml_string(value)}" for key, value in sorted(values.items())]
    return "\n".join(lines) + "\n"


def load_palette(path: Path) -> dict:
    data = tomllib.loads(path.read_text())
    data["ansi"] = [data.get("ansi", {}).get(f"color{index}") for index in range(16)]
    return validate(data)


# --------------------------------------------------------------------------
# importers (third-party theme directories are read as data only)
# --------------------------------------------------------------------------

def _read_text(path: Path, limit: int = 262144) -> str:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return ""


def parse_colors_toml(directory: Path) -> dict:
    """Omarchy 4.x: one colors.toml (named colours, indexed colours, or both)."""
    return {k: v for k, v in tomllib.loads(_read_text(directory / "colors.toml")).items()
            if isinstance(v, str)}


def parse_legacy(directory: Path) -> dict:
    """Omarchy legacy: per-app files.  alacritty.toml first, kitty.conf second."""
    raw: dict[str, str] = {}
    try:
        colors = tomllib.loads(_read_text(directory / "alacritty.toml")).get("colors", {})
    except tomllib.TOMLDecodeError:
        colors = {}
    primary = colors.get("primary", {})
    raw.update({k: primary[k] for k in ("background", "foreground") if k in primary})
    for offset, group in ((0, "normal"), (8, "bright")):
        for index, colour in enumerate(ANSI_NAMES):
            if colour in colors.get(group, {}):
                raw[f"color{index + offset}"] = colors[group][colour]
    if "cursor" in colors.get("cursor", {}):
        raw["cursor"] = colors["cursor"]["cursor"]
    selection = colors.get("selection", {})
    if "background" in selection:
        raw["selection_background"] = selection["background"]
    if "text" in selection:
        raw["selection_foreground"] = selection["text"]
    for line in _read_text(directory / "kitty.conf").splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"(back|fore)ground|cursor|color\d{1,2}|selection_(back|fore)ground", parts[0]):
            raw.setdefault(parts[0], parts[1])
    for line in _read_text(directory / "hyprland.conf").splitlines():
        if re.search(r"activeBorderColor\s*=|col\.active_border\s*=", line):
            found = re.search(r"rgba?\([0-9a-fA-F]{6,8}\)|0x[0-9a-fA-F]{8}", line.split("=", 1)[1])
            if found:
                raw["accent"] = found.group(0)
                break
    return {key: value for key, value in raw.items() if norm_hex(value)}


def parse_pywal(path: Path) -> dict:
    """pywal's colors.json: the wallpaper-derived palette."""
    data = json.loads(path.read_text())
    raw = dict(data.get("colors", {}))
    raw.update({k: v for k, v in data.get("special", {}).items() if k in ("background", "foreground", "cursor")})
    raw.setdefault("accent", raw.get("color4", ""))
    # A wallpaper's "red" can be any hue.  Keep alerts recognisable, with the
    # same fixed colours sync-pywal-theme.py uses; terminal slots stay pywal's.
    raw.update({"green": "#64d8a1", "yellow": "#f0b65b", "red": "#ff7085"})
    return raw


def _git_provenance(directory: Path) -> tuple[str | None, str | None]:
    """Read origin URL and HEAD commit from .git as text; git is never run there."""
    git = directory / ".git"
    url = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', _read_text(git / "config"))
    head = _read_text(git / "HEAD").strip()
    commit = head
    if head.startswith("ref: "):
        ref = head[5:].strip()
        commit = _read_text(git / ref).strip() if re.fullmatch(r"refs/[\w./-]+", ref) and ".." not in ref else ""
        if not commit:
            packed = re.search(rf"^([0-9a-f]{{40}}) {re.escape(ref)}$", _read_text(git / "packed-refs"), re.M)
            commit = packed.group(1) if packed else ""
    return (url.group(1) if url else None, commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9.]+", "-", name.lower()).strip("-.")
    return re.sub(r"^omarchy-|-theme$", "", slug) or "theme"


def import_theme(source: Path, themes: Path, *, slug: str | None = None,
                 dry_run: bool = False) -> dict:
    """Normalise one theme directory (or pywal colors.json) into ``themes``."""
    source = source.resolve()
    extras: dict[str, str] = {}
    mode = None
    url = commit = None
    if source.is_file():
        raw, fmt = parse_pywal(source), "pywal-json"
        slug = slug or slugify(source.parent.name)
    else:
        slug = slug or slugify(source.name)
        if (source / "colors.toml").is_file():
            raw, fmt = parse_colors_toml(source), "omarchy-colors-toml"
            mode = raw.get("mode")
        elif (source / "alacritty.toml").is_file() or (source / "kitty.conf").is_file():
            raw, fmt = parse_legacy(source), "omarchy-legacy"
        else:
            raise ValueError(f"{source}: no colors.toml, alacritty.toml or kitty.conf")
        if (source / "light.mode").exists():
            mode = "light"
        icon = _read_text(source / "icons.theme", 200).strip()
        if re.fullmatch(r"[\w.+ -]{1,80}", icon):
            extras["icon_theme"] = icon
        # neovim.lua is never executed: only the colourscheme *name* is read.
        scheme = re.search(r'colorscheme\s*=\s*"([\w.-]{1,60})"', _read_text(source / "neovim.lua"))
        if scheme:
            extras["nvim_colorscheme"] = scheme.group(1)
        if (source / "backgrounds").is_dir():
            extras["wallpapers"] = str(source / "backgrounds")
        if (source / "preview.png").is_file():
            extras["preview"] = str(source / "preview.png")
        url, commit = _git_provenance(source)
    name = slug.replace("-", " ").title()
    palette = normalise(raw, name=name, slug=slug, mode=mode)
    palette["extras"] = extras
    record = {"format": fmt, "source": str(source), "url": url, "commit": commit}
    if not dry_run:
        target = themes / slug
        target.mkdir(parents=True, exist_ok=True)
        write_if_changed(target / "palette.toml", dump_palette(palette))
        lock_path = themes / "themes.lock.json"
        lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
        lock[slug] = record
        write_if_changed(lock_path, json.dumps(dict(sorted(lock.items())), indent=2) + "\n")
    return {"slug": slug, **record}


# --------------------------------------------------------------------------
# renderers: palette -> {path relative to the generated directory: text}
# --------------------------------------------------------------------------

BANNER = "Generated by scripts/theme (theme: {slug}); do not edit."

# Neovim colourschemes this manager knows by theme slug -> (colourscheme, plugin).
NVIM_SCHEMES = {
    "tokyo-night": ("tokyonight-night", "tokyonight.nvim"),
    "catppuccin": ("catppuccin-mocha", "catppuccin"),
    "catppuccin-dark": ("catppuccin-mocha", "catppuccin"),
    "catppuccin-latte": ("catppuccin-latte", "catppuccin"),
    "gruvbox": ("gruvbox", "gruvbox.nvim"),
    "gruvbox-material": ("gruvbox-material", "gruvbox-material"),
    "nord": ("nordfox", "nightfox.nvim"),
    "everforest": ("everforest", "everforest-nvim"),
    "kanagawa": ("kanagawa", "kanagawa.nvim"),
    "rose-pine": ("rose-pine", "rose-pine"),
    "dracula": ("dracula", "dracula.nvim"),
    "matte-black": ("matteblack", "matteblack.nvim"),
    "osaka-jade": ("bamboo", "bamboo.nvim"),
    "ristretto": ("monokai-pro-ristretto", "monokai-pro.nvim"),
    "flexoki-light": ("flexoki-light", "flexoki-neovim"),
    "flexoki-dark": ("flexoki-dark", "flexoki-neovim"),
}


def installed_nvim_plugins() -> set[str]:
    try:
        return set(json.loads((ROOT / "config/nvim/lazy-lock.json").read_text()))
    except (OSError, ValueError):
        return set()


def noctalia_scheme(p: dict) -> dict:
    c, a = p["colors"], p["ansi"]
    scheme = {
        "mPrimary": c["accent"], "mOnPrimary": c["on_accent"],
        "mSecondary": c["accent_alt"], "mOnSecondary": best_on(c["accent_alt"], c["background"], c["foreground"]),
        "mTertiary": c["green"], "mOnTertiary": best_on(c["green"], c["background"], c["foreground"]),
        "mError": c["red"], "mOnError": best_on(c["red"], c["background"], c["foreground"]),
        "mSurface": c["background"], "mOnSurface": c["foreground"],
        "mSurfaceVariant": c["surface"],
        "mOnSurfaceVariant": readable(mix(c["foreground"], c["background"], 0.25), c["surface"]),
        "mOutline": c["border"], "mShadow": c["background_dim"],
        "mHover": c["green"], "mOnHover": best_on(c["green"], c["background"], c["foreground"]),
    }
    scheme.update({k: v for k, v in p["overrides"].get("noctalia", {}).items()
                   if k in scheme and norm_hex(v)})
    scheme["terminal"] = {
        "normal": dict(zip(ANSI_NAMES, a[:8])),
        "bright": dict(zip(ANSI_NAMES, a[8:])),
        "foreground": c["foreground"], "background": c["background"],
        "selectionFg": c["selection_foreground"], "selectionBg": c["selection_background"],
        "cursorText": c["background"], "cursor": c["cursor"],
    }
    return scheme


def render_noctalia(p: dict) -> dict[str, str]:
    scheme = noctalia_scheme(p)
    # Same colours under both keys: the theme, not Noctalia's dark switch, decides.
    return {f"noctalia/{SCHEME}/{SCHEME}.json": json.dumps({"dark": scheme, "light": scheme}, indent=2) + "\n"}


def render_hyprland(p: dict) -> dict[str, str]:
    c, n = p["colors"], noctalia_scheme(p)

    def rgba(value: str, alpha: str = "ff") -> str:
        return f"rgba({strip(value)}{alpha})"

    # Border and group keys mirror config/noctalia/hyprland-group-colors.conf so
    # Noctalia's own template and this file always agree.
    active = f"{rgba(n['mPrimary'])} {rgba(n['mSecondary'])} 90deg"
    lines = [
        f"# {BANNER.format(slug=p['slug'])}",
        f"general:col.active_border = {active}",
        f"general:col.inactive_border = {rgba(n['mOutline'])}",
        f"group:col.border_active = {active}",
        f"group:col.border_inactive = {rgba(n['mOutline'])}",
        f"group:col.border_locked_active = {active}",
        f"group:col.border_locked_inactive = {rgba(n['mOutline'])}",
        f"group:groupbar:col.active = {rgba(n['mPrimary'])}",
        f"group:groupbar:col.inactive = {rgba(n['mSurfaceVariant'])}",
        f"group:groupbar:col.locked_active = {rgba(n['mPrimary'])}",
        f"group:groupbar:col.locked_inactive = {rgba(n['mSurface'])}",
        f"group:groupbar:text_color = {rgba(n['mOnPrimary'])}",
        f"group:groupbar:text_color_inactive = {rgba(n['mOnSurfaceVariant'])}",
        f"group:groupbar:text_color_locked_active = {rgba(n['mOnPrimary'])}",
        f"group:groupbar:text_color_locked_inactive = {rgba(n['mOnSurface'])}",
        f"decoration:shadow:color = {rgba(mix(c['background_dim'], '#000000', 0.6), '80')}",
        f"plugin:hyprglass:tint_color = 0x{strip(c['background'])}38",
    ]
    return {"hyprland.conf": "\n".join(lines) + "\n"}


def render_kitty(p: dict) -> dict[str, str]:
    c, a = p["colors"], p["ansi"]
    rows = [
        ("foreground", c["foreground"]), ("background", c["background"]),
        ("cursor", c["cursor"]), ("cursor_text_color", c["background"]),
        ("selection_foreground", c["selection_foreground"]),
        ("selection_background", c["selection_background"]),
        ("url_color", c["accent"]),
        ("active_border_color", c["accent"]), ("inactive_border_color", c["border"]),
        ("active_tab_foreground", c["on_accent"]), ("active_tab_background", c["accent"]),
        ("inactive_tab_foreground", c["foreground_dim"]), ("inactive_tab_background", c["surface"]),
        *[(f"color{index}", value) for index, value in enumerate(a)],
    ]
    body = "\n".join(f"{key:<24}{value}" for key, value in rows)
    return {"kitty.conf": f"# {BANNER.format(slug=p['slug'])}\n{body}\n"}


def render_alacritty(p: dict) -> dict[str, str]:
    c, a = p["colors"], p["ansi"]
    lines = [
        f"# {BANNER.format(slug=p['slug'])}",
        "[colors]",
        "draw_bold_text_with_bright_colors = true",
        "",
        "[colors.primary]",
        f'background = "{c["background"]}"',
        f'foreground = "{c["foreground"]}"',
        f'dim_foreground = "{c["foreground_dim"]}"',
        "",
        "[colors.cursor]",
        f'text = "{c["background"]}"',
        f'cursor = "{c["cursor"]}"',
        "",
        "[colors.selection]",
        f'text = "{c["selection_foreground"]}"',
        f'background = "{c["selection_background"]}"',
        "",
        "[colors.normal]",
        *[f'{name} = "{a[index]}"' for index, name in enumerate(ANSI_NAMES)],
        "",
        "[colors.bright]",
        *[f'{name} = "{a[index + 8]}"' for index, name in enumerate(ANSI_NAMES)],
    ]
    return {"alacritty.toml": "\n".join(lines) + "\n"}


def render_rofi(p: dict) -> dict[str, str]:
    c = p["colors"]
    # Variable names match pywal's colors-rofi-dark.rasi, which config/rofi
    # /colors.rasi already maps onto the launcher layout.
    pairs = {
        "background": c["background"], "foreground": c["foreground"],
        "border-color": c["accent"], "separatorcolor": c["border"],
        "normal-background": c["background"], "normal-foreground": c["foreground"],
        "alternate-normal-background": c["background"], "alternate-normal-foreground": c["foreground"],
        "active-background": c["accent"], "active-foreground": c["on_accent"],
        "alternate-active-background": c["background"], "alternate-active-foreground": c["accent"],
        "urgent-background": c["red"], "urgent-foreground": best_on(c["red"], c["background"], c["foreground"]),
        "alternate-urgent-background": c["background"], "alternate-urgent-foreground": c["red"],
        "selected-normal-background": c["accent"], "selected-normal-foreground": c["on_accent"],
        "selected-active-background": c["accent_alt"],
        "selected-active-foreground": best_on(c["accent_alt"], c["background"], c["foreground"]),
        "selected-urgent-background": c["red"],
        "selected-urgent-foreground": best_on(c["red"], c["background"], c["foreground"]),
    }
    body = "\n".join(f"    {key}: {value};" for key, value in pairs.items())
    return {"rofi.rasi": f"/* {BANNER.format(slug=p['slug'])} */\n* {{\n{body}\n}}\n"}


def render_dunst(p: dict) -> dict[str, str]:
    c = p["colors"]
    # A dunstrc.d drop-in: later files override config/dunst/dunstrc key by key.
    text = f"""# {BANNER.format(slug=p['slug'])}
[global]
    frame_color = "{c['accent']}"

[urgency_low]
    background = "{c['background']}d9"
    foreground = "{c['foreground_dim']}"

[urgency_normal]
    background = "{c['background']}e0"
    foreground = "{c['foreground']}"

[urgency_critical]
    background = "{c['background']}e8"
    foreground = "{c['foreground']}"
    frame_color = "{c['red']}"
"""
    return {"dunst.conf": text}


def render_hyprlock(p: dict) -> dict[str, str]:
    c = p["colors"]
    values = {
        "lock_outer": c["accent"], "lock_inner": c["surface"],
        "lock_font": c["foreground"], "lock_check": c["green"],
        "lock_fail": c["red"], "lock_capslock": c["yellow"],
        "lock_text": c["foreground_bright"], "lock_subtext": c["foreground_dim"],
        "lock_shadow": mix(c["background_dim"], "#000000", 0.6),
    }
    body = "\n".join(f"${key} = rgb({strip(value)})" for key, value in values.items())
    return {"hyprlock.conf": f"# {BANNER.format(slug=p['slug'])}\n{body}\n"}


def render_waybar(p: dict) -> dict[str, str]:
    c, bg = p["colors"], p["colors"]["background"]
    # Same names as ~/.cache/wal/colors-waybar-semantic.css, so the waybar
    # stylesheets need only their @import line changed.
    names = {
        "wb_background": bg, "wb_foreground": c["foreground"],
        **{f"wb_grad{index}": readable(c[key], bg) for index, key in
           enumerate(("red", "orange", "yellow", "green", "cyan", "magenta"), start=1)},
        "wb_info": c["foreground"], "wb_muted": c["foreground_dim"],
        "wb_ok": readable(c["green"], bg), "wb_warning": readable(c["yellow"], bg),
        "wb_critical": readable(c["red"], bg),
        "theme_accent": c["accent"], "theme_surface": c["surface"], "theme_border": c["border"],
    }
    body = "\n".join(f"@define-color {key} {value};" for key, value in names.items())
    return {"waybar.css": f"/* {BANNER.format(slug=p['slug'])} */\n{body}\n"}


def render_tmux(p: dict) -> dict[str, str]:
    c = p["colors"]
    bg, fg, muted = c["background"], c["foreground"], c["foreground_dim"]
    active, accent = readable(c["accent"], bg), readable(c["cyan"], bg)
    # Same statements as sync-pywal-theme.py writes to colors-tmux.conf.
    lines = [
        f"# {BANNER.format(slug=p['slug'])}",
        f"set -g status-style 'fg={fg},bg=default'",
        f"set -g status-left '#[fg={active},bg=default,bold]❨ 󰆍 #S ❩ '",
        f"set -g status-right '#{{?client_prefix,#[fg={c['yellow']}]󰘳 PREFIX  ,}}#[fg={muted}]#{{b:pane_current_path}} #[fg={accent}]· #{{pane_current_command}} #[fg={muted}]· %H:%M '",
        f"setw -g window-status-style 'fg={muted},bg=default'",
        f"setw -g window-status-current-format '#[fg={active},bg=default,bold]❨ #I:#W#{{?window_zoomed_flag, 󰊓,}} ❩'",
        f"setw -g window-status-activity-style 'fg={c['yellow']},bg=default,bold'",
        f"setw -g window-status-bell-style 'fg={c['red']},bg=default,bold'",
        f"set -g pane-border-style 'fg={c['border']}'",
        f"set -g pane-active-border-style 'fg={active}'",
        f"set -g mode-style 'fg={bg},bg={active},bold'",
        f"set -g message-style 'fg={fg},bg={c['surface']}'",
        f"set -g message-command-style 'fg={accent},bg={c['surface']}'",
        f"set -g menu-style 'fg={fg},bg={bg}'",
        f"set -g menu-selected-style 'fg={bg},bg={active},bold'",
        f"set -g menu-border-style 'fg={muted}'",
        f"set -g popup-style 'fg={fg},bg={bg}'",
        f"set -g popup-border-style 'fg={active}'",
    ]
    return {"tmux.conf": "\n".join(lines) + "\n"}


def render_btop(p: dict) -> dict[str, str]:
    c = p["colors"]
    values = {
        "main_bg": "",  # keep the terminal's own (translucent) background
        "main_fg": c["foreground"], "title": c["foreground_bright"],
        "hi_fg": c["accent"], "selected_bg": c["selection_background"],
        "selected_fg": c["selection_foreground"], "inactive_fg": c["foreground_dim"],
        "graph_text": c["foreground_dim"], "meter_bg": c["surface_alt"],
        "proc_misc": c["cyan"], "cpu_box": c["accent"], "mem_box": c["green"],
        "net_box": c["magenta"], "proc_box": c["border"], "div_line": c["border"],
        "temp_start": c["green"], "temp_mid": c["yellow"], "temp_end": c["red"],
        "cpu_start": c["cyan"], "cpu_mid": c["accent"], "cpu_end": c["magenta"],
        "free_start": c["green"], "free_mid": c["cyan"], "free_end": c["accent"],
        "cached_start": c["cyan"], "cached_mid": c["accent"], "cached_end": c["magenta"],
        "available_start": c["yellow"], "available_mid": c["orange"], "available_end": c["red"],
        "used_start": c["green"], "used_mid": c["yellow"], "used_end": c["red"],
        "download_start": c["accent"], "download_mid": c["cyan"], "download_end": c["green"],
        "upload_start": c["magenta"], "upload_mid": c["orange"], "upload_end": c["red"],
        "process_start": c["green"], "process_mid": c["yellow"], "process_end": c["red"],
    }
    body = "\n".join(f'theme[{key}]="{value}"' for key, value in values.items())
    return {"btop.theme": f"# {BANNER.format(slug=p['slug'])}\n{body}\n"}


def render_shell(p: dict) -> dict[str, str]:
    c = p["colors"]
    fzf = ",".join(f"{key}:{value}" for key, value in {
        "fg": c["foreground"], "bg": "-1", "hl": c["accent"],
        "fg+": c["foreground_bright"], "bg+": c["surface_alt"], "hl+": c["accent"],
        "info": c["foreground_dim"], "prompt": c["accent"], "pointer": c["accent_alt"],
        "marker": c["green"], "spinner": c["accent_alt"], "header": c["foreground_dim"],
        "border": c["border"], "gutter": "-1",
    }.items())
    text = f"""# {BANNER.format(slug=p['slug'])}
# Sourced by interactive shells; safe to source repeatedly.
: "${{THEME_FZF_BASE=${{FZF_DEFAULT_OPTS-}}}}"
export THEME_FZF_BASE
export FZF_DEFAULT_OPTS="$THEME_FZF_BASE --color={fzf}"
# bat's ansi theme follows the terminal palette, which this theme already sets.
export BAT_THEME=ansi
export THEME_SLUG={p['slug']}
export THEME_MODE={p['mode']}
"""
    return {"shell.sh": text}


def render_delta(p: dict) -> dict[str, str]:
    c, bg = p["colors"], p["colors"]["background"]
    text = f"""# {BANNER.format(slug=p['slug'])}
[delta]
	{p['mode']} = true
	syntax-theme = ansi
	minus-style = syntax "{mix(bg, c['red'], 0.22)}"
	minus-emph-style = syntax "{mix(bg, c['red'], 0.45)}"
	plus-style = syntax "{mix(bg, c['green'], 0.22)}"
	plus-emph-style = syntax "{mix(bg, c['green'], 0.45)}"
	line-numbers-minus-style = "{c['red']}"
	line-numbers-plus-style = "{c['green']}"
	line-numbers-zero-style = "{c['foreground_dim']}"
	file-style = "{c['accent']}" bold
	file-decoration-style = "{c['border']}" ul
	hunk-header-style = "{c['foreground_dim']}"
	hunk-header-decoration-style = "{c['border']}" box
"""
    return {"delta.gitconfig": text}


def render_gtk(p: dict) -> dict[str, str]:
    c = p["colors"]
    bg, fg, accent = c["background"], c["foreground"], c["accent"]

    def glass(value: str, alpha: float) -> str:
        return f"rgba({rgb_csv(value)}, {alpha:.2f})"

    semantic = {
        "accent_color": accent, "accent_fg_color": c["on_accent"],
        "destructive_bg_color": c["red"], "destructive_fg_color": best_on(c["red"], bg, fg),
        "destructive_color": c["red"],
        "success_bg_color": c["green"], "success_fg_color": best_on(c["green"], bg, fg),
        "success_color": c["green"],
        "warning_bg_color": c["yellow"], "warning_fg_color": best_on(c["yellow"], bg, fg),
        "warning_color": c["yellow"],
        "error_bg_color": c["red"], "error_fg_color": best_on(c["red"], bg, fg),
        "error_color": c["red"],
        "window_fg_color": fg, "view_fg_color": fg, "headerbar_fg_color": fg,
        "sidebar_fg_color": fg, "card_fg_color": fg, "dialog_fg_color": fg,
        "popover_fg_color": fg,
    }
    # GTK4: alphas mirror config/gtk-4.0/gtk.css so the glass look survives.
    gtk4 = {
        "window_bg_color": glass(bg, 0.82), "headerbar_bg_color": glass(c["surface"], 0.78),
        "sidebar_bg_color": glass(c["background_dim"], 0.50),
        "secondary_sidebar_bg_color": glass(c["background_dim"], 0.50),
        "view_bg_color": glass(bg, 0.45), "card_bg_color": glass(c["surface"], 0.55),
        "popover_bg_color": glass(c["surface_alt"], 0.88),
        "dialog_bg_color": glass(c["surface_alt"], 0.85),
        "accent_bg_color": glass(accent, 0.85),
        **semantic,
    }
    # GTK3: opaque.  Classic names for ordinary themes plus the libadwaita
    # names that adw-gtk3 reads.
    gtk3 = {
        "theme_bg_color": bg, "theme_fg_color": fg,
        "theme_base_color": c["background_dim"], "theme_text_color": fg,
        "theme_selected_bg_color": accent, "theme_selected_fg_color": c["on_accent"],
        "insensitive_bg_color": c["surface"], "insensitive_fg_color": c["foreground_dim"],
        "insensitive_base_color": bg,
        "theme_unfocused_bg_color": bg, "theme_unfocused_fg_color": fg,
        "theme_unfocused_base_color": c["background_dim"], "theme_unfocused_text_color": fg,
        "theme_unfocused_selected_bg_color": accent,
        "theme_unfocused_selected_fg_color": c["on_accent"],
        "borders": c["border"], "unfocused_borders": c["border"],
        "window_bg_color": bg, "headerbar_bg_color": c["surface"],
        "sidebar_bg_color": c["background_dim"], "view_bg_color": c["background_dim"],
        "card_bg_color": c["surface"], "popover_bg_color": c["surface_alt"],
        "dialog_bg_color": c["surface_alt"], "accent_bg_color": accent,
        **semantic,
    }

    def sheet(names: dict[str, str]) -> str:
        body = "\n".join(f"@define-color {key} {value};" for key, value in names.items())
        return f"/* {BANNER.format(slug=p['slug'])} */\n{body}\n"

    return {"gtk3.css": sheet(gtk3), "gtk4.css": sheet(gtk4)}


def qt_roles(p: dict) -> dict[str, str]:
    c = p["colors"]
    return {
        "window": c["background"], "base": c["background_dim"], "alt_base": c["surface"],
        "button": c["surface"], "light": c["border"], "midlight": c["surface_alt"],
        "dark": mix(c["background_dim"], "#000000", 0.4), "mid": mix(c["background"], "#000000", 0.2),
        "text": c["foreground"], "bright_text": c["foreground_bright"],
        "disabled_text": mix(c["foreground"], c["background"], 0.55),
        "highlight": c["accent"], "inactive_highlight": mix(c["accent"], c["background"], 0.3),
        "highlight_text": c["on_accent"], "link": c["accent"], "link_visited": c["accent_alt"],
        "shadow": "#000000",
    }


def render_qt(p: dict) -> dict[str, str]:
    r = qt_roles(p)

    def row(text: str, highlight: str, highlight_text: str) -> str:
        # qt6ct role order: WindowText Button Light Midlight Dark Mid Text
        # BrightText ButtonText Base Window Shadow Highlight HighlightedText
        # Link LinkVisited AlternateBase ToolTipBase ToolTipText PlaceholderText Accent
        roles = [text, r["button"], r["light"], r["midlight"], r["dark"], r["mid"], text,
                 r["bright_text"], text, r["base"], r["window"], r["shadow"], highlight,
                 highlight_text, r["link"], r["link_visited"], r["alt_base"], r["window"],
                 r["text"], r["disabled_text"], highlight]
        return ", ".join(f"#ff{strip(value)}" for value in roles)

    text = "\n".join([
        f"# {BANNER.format(slug=p['slug'])}",
        "[ColorScheme]",
        f"active_colors={row(r['text'], r['highlight'], r['highlight_text'])}",
        f"disabled_colors={row(r['disabled_text'], r['inactive_highlight'], r['disabled_text'])}",
        f"inactive_colors={row(r['text'], r['inactive_highlight'], r['text'])}",
    ])
    return {"qt6ct.conf": text + "\n"}


KVANTUM_COLOR_KEYS = {
    "window.color": "window", "base.color": "base", "alt.base.color": "alt_base",
    "button.color": "button", "light.color": "light", "mid.light.color": "midlight",
    "dark.color": "dark", "mid.color": "mid", "highlight.color": "highlight",
    "inactive.highlight.color": "inactive_highlight", "text.color": "text",
    "window.text.color": "text", "button.text.color": "text",
    "disabled.text.color": "disabled_text", "tooltip.text.color": "text",
    "highlight.text.color": "highlight_text", "link.color": "link",
    "link.visited.color": "link_visited", "progress.indicator.text.color": "highlight_text",
}


def render_kvantum(p: dict, base_config: str) -> str:
    """Recolour the [GeneralColors] of an existing Kvantum theme's kvconfig."""
    roles, section, out = qt_roles(p), "", []
    for line in base_config.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
        key = stripped.split("=", 1)[0].strip()
        if section == "[GeneralColors]" and key in KVANTUM_COLOR_KEYS and "=" in stripped:
            line = f"{key}={roles[KVANTUM_COLOR_KEYS[key]]}"
        out.append(line)
    return f"# {BANNER.format(slug=p['slug'])}\n" + "\n".join(out) + "\n"


def nvim_choice(p: dict, plugins: set[str] | None = None) -> tuple[str, bool, str]:
    """(colourscheme, native?, note).  Falls back to recoloured tokyonight."""
    plugins = installed_nvim_plugins() if plugins is None else plugins
    scheme, plugin = NVIM_SCHEMES.get(p["slug"], (None, None))
    hinted = p["extras"].get("nvim_colorscheme", "")
    if not scheme:
        for prefix, owner in (("tokyonight", "tokyonight.nvim"), ("catppuccin", "catppuccin")):
            if hinted.startswith(prefix):
                scheme, plugin = hinted, owner
    if scheme and plugin in plugins:
        return scheme, True, f"native colourscheme {scheme}"
    wanted = scheme or hinted
    note = f"{wanted} needs plugin {plugin or '?'} (not installed); " if wanted else ""
    return "tokyonight", False, note + "tokyonight recoloured from the palette"


def render_nvim(p: dict) -> dict[str, str]:
    c = p["colors"]
    scheme, native, _note = nvim_choice(p)
    overrides = {} if native else {
        "bg": c["background"], "bg_dark": c["background_dim"], "bg_dark1": c["background_dim"],
        "bg_float": c["background_dim"], "bg_popup": c["background_dim"],
        "bg_sidebar": c["background_dim"], "bg_statusline": c["background_dim"],
        "bg_highlight": c["surface"], "bg_visual": c["selection_background"],
        "bg_search": mix(c["background"], c["accent"], 0.45),
        "border": c["background_dim"], "border_highlight": c["accent"],
        "fg": c["foreground"], "fg_dark": mix(c["foreground"], c["background"], 0.2),
        "fg_float": c["foreground"], "fg_sidebar": mix(c["foreground"], c["background"], 0.2),
        "fg_gutter": c["border"], "comment": c["foreground_dim"],
        "dark3": c["foreground_dim"], "dark5": mix(c["foreground_dim"], c["foreground"], 0.3),
        "terminal_black": p["ansi"][8],
        "blue": c["blue"], "blue1": c["cyan"], "blue2": c["cyan"], "blue5": c["cyan"],
        "cyan": c["cyan"], "teal": c["cyan"], "green": c["green"], "green1": c["cyan"],
        "magenta": c["magenta"], "purple": c["magenta"], "red": c["red"], "red1": c["red"],
        "orange": c["orange"], "yellow": c["yellow"],
        "error": c["red"], "warning": c["yellow"], "info": c["cyan"], "hint": c["green"],
    }

    def table(values: dict[str, str]) -> str:
        return "{ " + ", ".join(f'{key} = "{value}"' for key, value in values.items()) + " }"

    lines = [
        f"-- {BANNER.format(slug=p['slug'])}",
        "return {",
        f'  slug = "{p["slug"]}",',
        f'  background = "{p["mode"]}",',
        f'  colorscheme = "{scheme}",',
        f"  native = {'true' if native else 'false'},",
        f"  overrides = {table(overrides)},",
        f"  palette = {table({key: c[key] for key in COLOR_KEYS})},",
        "  ansi = { " + ", ".join(f'"{value}"' for value in p["ansi"]) + " },",
        "}",
    ]
    return {"nvim.lua": "\n".join(lines) + "\n"}


# --------------------------------------------------------------------------
# environment, wiring and reloads
# --------------------------------------------------------------------------

@dataclass
class Env:
    home: Path
    themes: Path = DEFAULT_THEMES
    live: bool = True      # may talk to the running session
    dry_run: bool = False

    @property
    def state_dir(self) -> Path:
        return self.home / ".local/state/theme"

    @property
    def generated(self) -> Path:
        return self.home / GENERATED_REL

    def state(self) -> dict:
        try:
            return json.loads((self.state_dir / "state.json").read_text())
        except (OSError, ValueError):
            return {}

    def save_state(self, **changes: object) -> None:
        state = {**self.state(), **changes}
        if not self.dry_run:
            write_if_changed(self.state_dir / "state.json", json.dumps(state, indent=2, sort_keys=True) + "\n")


def write_if_changed(path: Path, text: str) -> bool:
    """Atomic write that leaves an identical file (and its mtime) untouched."""
    try:
        if path.read_text() == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp{os.getpid()}")
    temporary.write_text(text)
    os.replace(temporary, path)
    return True


G = "~/" + GENERATED_REL  # how hand-written configs spell the generated directory


@dataclass(frozen=True)
class Wire:
    """One include that points a hand-written config at a generated file.

    kind 'line':    in ``target`` replace the line matching ``old`` with ``new``;
                    without a match, insert ``new`` after ``anchor`` (or at EOF).
    kind 'symlink': make ``target`` a symlink to generated file ``new``.
    kind 'file':    create ``target`` containing ``new`` when it does not exist.
    ``{home}`` in ``new`` expands to the home directory.
    """
    kind: str
    target: str            # path relative to the home directory
    new: str
    old: str = ""          # regex for the line being replaced
    anchor: str = ""       # regex of the line to insert after
    optional: bool = False  # skip silently when the target file is absent
    requires: str = ""     # generated file that must exist before wiring


@dataclass(frozen=True)
class Component:
    name: str
    render: Callable[[dict], dict[str, str]]
    wires: tuple[Wire, ...]
    reload: str            # human description of how the change reaches a running app
    binary: str = ""       # tool that must exist for the component to matter
    live: Callable[["Env", dict], list[list[str]]] | None = None


def _hyprland_batch(env: Env, _p: dict) -> list[list[str]]:
    lines = [line for line in (env.generated / "hyprland.conf").read_text().splitlines()
             if line and not line.startswith("#")]
    batch = " ; ".join("keyword " + line.replace(" = ", " ", 1) for line in lines)
    return [["hyprctl", "--batch", batch]]


def _noctalia_reload(_env: Env, p: dict) -> list[list[str]]:
    ipc = ["qs", "-c", "noctalia-shell", "ipc", "call"]
    return [[*ipc, "darkMode", "setDark" if p["mode"] == "dark" else "setLight"],
            [*ipc, "colorScheme", "set", SCHEME]]


COMPONENTS: tuple[Component, ...] = (
    Component("noctalia", render_noctalia,
              (Wire("symlink", f".config/noctalia/colorschemes/{SCHEME}", f"noctalia/{SCHEME}"),),
              "qs ipc colorScheme set (live; first use needs one Noctalia restart to list the scheme)",
              "qs", _noctalia_reload),
    Component("hyprland", render_hyprland,
              (Wire("line", ".config/hypr/hyprland.conf", f"source = {G}/hyprland.conf",
                    old=r"source = ~/\.cache/wal/colors-hyprland\.conf"),),
              "hyprctl --batch keyword (live, no compositor reload)", "hyprctl", _hyprland_batch),
    Component("kitty", render_kitty,
              (Wire("line", ".config/kitty/kitty.conf", f"include {G}/kitty.conf",
                    old=r"include ~/\.cache/wal/colors-kitty\.conf"),),
              "SIGUSR1 to kitty (live)", "kitty",
              lambda _e, _p: [["pkill", "-USR1", "-x", "kitty"]]),
    Component("alacritty", render_alacritty,
              (Wire("line", ".config/alacritty/alacritty.toml", f'  "{G}/alacritty.toml",',
                    old=r'\s*"~/\.cache/wal/colors-alacritty\.toml",'),),
              "automatic (live_config_reload watches imports)", "alacritty"),
    Component("rofi", render_rofi,
              (Wire("line", ".config/rofi/colors.rasi", f'@import "{G}/rofi.rasi"',
                    old=r'@import "~/\.cache/wal/colors-rofi-dark\.rasi"'),),
              "next launch", "rofi"),
    Component("dunst", render_dunst,
              (Wire("symlink", ".config/dunst/dunstrc.d/50-theme.conf", "dunst.conf"),),
              "dunstctl reload (live; clears shown notifications)", "dunst",
              lambda _e, _p: [["dunstctl", "reload"]]),
    Component("hyprlock", render_hyprlock,
              (Wire("line", ".config/hypr/hyprlock.conf", f"source = {G}/hyprlock.conf",
                    anchor=r"# theme:source.*"),),
              "next lock", "hyprlock"),
    Component("waybar", render_waybar,
              tuple(Wire("line", f".config/waybar/{name}",
                         '@import url("../../.local/state/theme/generated/waybar.css");',
                         old=r'@import url\("\.\./\.\./\.cache/wal/colors-waybar-semantic\.css"\);',
                         optional=True)
                    for name in ("style.css", "style-glass.css", "user-style.css")),
              "SIGUSR2 to waybar (live, when waybar runs)", "waybar",
              lambda _e, _p: [["pkill", "-USR2", "-x", "waybar"]]),
    Component("tmux", render_tmux,
              (Wire("line", ".tmux.conf", f"source-file -q {G}/tmux.conf",
                    old=r"source-file -q ~/\.cache/wal/colors-tmux\.conf"),),
              "tmux source-file (live)", "tmux",
              lambda e, _p: [["tmux", "source-file", str(e.generated / "tmux.conf")]]),
    Component("btop", render_btop,
              (Wire("symlink", ".config/btop/themes/unified.theme", "btop.theme"),
               Wire("line", ".config/btop/btop.conf", 'color_theme = "unified"',
                    old=r"color_theme\s*=.*")),
              "restart btop", "btop"),
    Component("shell", render_shell,
              (Wire("line", ".zshrc", f"[[ -r {G}/shell.sh ]] && source {G}/shell.sh"),),
              "new shells (fzf colours, BAT_THEME)", "zsh"),
    Component("delta", render_delta,
              (Wire("line", ".gitconfig", f"[include]\n\tpath = {G}/delta.gitconfig"),),
              "next git command", "delta"),
    Component("gtk", render_gtk,
              (Wire("file", ".config/gtk-3.0/gtk.css",
                    '@import url("file://{home}/' + GENERATED_REL + '/gtk3.css");\n'),
               Wire("line", ".config/gtk-4.0/gtk.css",
                    '@import url("file://{home}/' + GENERATED_REL + '/gtk4.css");')),
              "newly started GTK apps"),
    Component("qt", render_qt,
              (Wire("line", ".config/qt6ct/qt6ct.conf",
                    "color_scheme_path={home}/" + GENERATED_REL + "/qt6ct.conf",
                    old=r"color_scheme_path=.*"),
               Wire("line", ".config/qt5ct/qt5ct.conf",
                    "color_scheme_path={home}/" + GENERATED_REL + "/qt6ct.conf",
                    old=r"color_scheme_path=.*", optional=True),
               Wire("symlink", f".config/Kvantum/{SCHEME}", f"kvantum/{SCHEME}", optional=True),
               Wire("line", ".config/Kvantum/kvantum.kvconfig", f"theme={SCHEME}",
                    old=r"theme=.*", optional=True, requires=f"kvantum/{SCHEME}/{SCHEME}.kvconfig")),
              "qt6ct apps follow the file; Kvantum-styled apps on restart"),
    Component("nvim", render_nvim,
              (Wire("file", ".config/nvim/lua/plugins/theme.lua",
                    '-- Wired by `theme wire nvim`: follow the unified theme manager.\n'
                    'return require("theme_loader")\n'),),
              "next nvim start", "nvim"),
)
BY_NAME = {component.name: component for component in COMPONENTS}


def kvantum_base(env: Env) -> tuple[str, Path] | None:
    """The Kvantum theme to recolour: the one in use before wiring."""
    root = env.home / ".config/Kvantum"
    name = env.state().get("kvantum_base", "")
    if not name:
        found = re.search(r"^theme=(.+)$", _read_text(root / "kvantum.kvconfig"), re.M)
        name = found.group(1).strip() if found else ""
    name = name.rstrip("#")
    config = root / name / f"{name}.kvconfig"
    return (name, config) if name and name != SCHEME and config.is_file() else None


def render_all(env: Env, palette: dict) -> dict[str, str]:
    files: dict[str, str] = {}
    for component in COMPONENTS:
        files.update(component.render(palette))
    base = kvantum_base(env)
    if base:
        files[f"kvantum/{SCHEME}/{SCHEME}.kvconfig"] = render_kvantum(palette, base[1].read_text())
    files["current.json"] = json.dumps(
        {"slug": palette["slug"], "name": palette["name"], "mode": palette["mode"],
         "colors": palette["colors"], "ansi": palette["ansi"]}, indent=2) + "\n"
    return files


def wire_status(env: Env, wire: Wire) -> str:
    """'wired', 'unwired' or 'absent' (the target config does not exist)."""
    target = env.home / wire.target
    new = wire.new.replace("{home}", str(env.home))
    if wire.kind == "symlink":
        if target.is_symlink() and Path(os.readlink(target)) == env.generated / wire.new:
            return "wired"
        return "unwired" if target.parent.parent.exists() else "absent"
    if wire.kind == "file" and not target.exists():
        return "unwired" if target.parent.parent.exists() else "absent"
    if not target.exists():
        return "absent"
    present = {line.strip() for line in _read_text(target).splitlines()}
    return "wired" if all(line.strip() in present for line in new.strip().splitlines()) else "unwired"


def wire_states(env: Env, component: Component) -> list[str]:
    """Status of every wire that applies (optional wires for absent configs do not)."""
    pairs = [(wire, wire_status(env, wire)) for wire in component.wires]
    return [state for wire, state in pairs if not (wire.optional and state == "absent")]


def component_wired(env: Env, component: Component) -> bool:
    states = wire_states(env, component)
    return bool(states) and all(state == "wired" for state in states)


def apply_wire(env: Env, wire: Wire, undo: dict) -> str:
    target = env.home / wire.target
    new = wire.new.replace("{home}", str(env.home))
    status = wire_status(env, wire)
    if status == "wired":
        return f"ok        {wire.target} (already wired)"
    if status == "absent":
        return f"{'skipped' if wire.optional else 'MISSING'}   {wire.target} (no such config)"
    needs = env.generated / (wire.requires or (wire.new if wire.kind == "symlink" else "current.json"))
    if not needs.exists():
        if wire.optional:
            return f"skipped   {wire.target} (nothing generated for it)"
        return f"MISSING   {wire.target} (generate first: theme apply <slug>)"
    if wire.kind == "symlink":
        source = env.generated / wire.new
        if target.exists() and not target.is_symlink():
            return f"MISSING   {wire.target} (exists and is not a symlink; left alone)"
        if not env.dry_run:
            undo[wire.target] = {"kind": "symlink", "previous": os.readlink(target) if target.is_symlink() else None}
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            target.symlink_to(source)
        return f"wired     {wire.target} -> {source}"
    if wire.kind == "file" and not target.exists():
        if not env.dry_run:
            undo[wire.target] = {"kind": "created"}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new)
        return f"wired     {wire.target} (created)"
    lines = target.read_text().splitlines()
    replaced = None
    if wire.old:
        for index, line in enumerate(lines):
            if re.fullmatch(wire.old, line):
                replaced, lines[index] = line, new
                break
        if replaced is None:
            return f"MISSING   {wire.target} (expected line not found: {wire.old})"
    else:
        index = len(lines)
        if wire.anchor:
            index = next((i + 1 for i, line in enumerate(lines) if re.fullmatch(wire.anchor, line)), -1)
            if index < 0:
                return f"MISSING   {wire.target} (anchor not found: {wire.anchor})"
        elif wire.kind == "file":
            index = 0  # stylesheets want @import first
        lines[index:index] = [new.rstrip("\n")]
    if not env.dry_run:
        undo[wire.target] = {"kind": "line", "new": new.rstrip("\n"), "old": replaced}
        target.write_text("\n".join(lines) + "\n")
    return f"wired     {wire.target}: {new.strip().splitlines()[0]}"


def undo_wire(env: Env, wire: Wire, undo: dict) -> str:
    target = env.home / wire.target
    record = undo.get(wire.target)
    if not record:
        return f"skipped   {wire.target} (not wired by this tool)"
    if env.dry_run:
        return f"would unwire {wire.target}"
    if record["kind"] == "symlink":
        if target.is_symlink():
            target.unlink()
        if record.get("previous"):
            target.symlink_to(record["previous"])
    elif record["kind"] == "created":
        target.unlink(missing_ok=True)
    else:
        text = target.read_text()
        replacement = record["old"] + "\n" if record.get("old") is not None else ""
        target.write_text(text.replace(record["new"] + "\n", replacement, 1))
    del undo[wire.target]
    return f"unwired   {wire.target}"


def run_live(env: Env, commands: list[list[str]], log: list[str]) -> None:
    for command in commands:
        shown = " ".join(command) if len(" ".join(command)) < 160 else " ".join(command)[:157] + "..."
        if env.dry_run or not env.live:
            log.append(f"would run: {shown}")
            continue
        if not shutil.which(command[0]):
            log.append(f"skipped (not installed): {shown}")
            continue
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        log.append(f"{'ran' if result.returncode == 0 else 'FAILED'}: {shown}")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def list_themes(env: Env) -> list[str]:
    if not env.themes.is_dir():
        return []
    return sorted(path.parent.name for path in env.themes.glob("*/palette.toml"))


def wallpapers(env: Env, palette: dict) -> list[Path]:
    """A theme's own wallpapers/ directory wins over the imported location."""
    for directory in (env.themes / palette["slug"] / "wallpapers",
                      Path(palette["extras"].get("wallpapers", "/nonexistent"))):
        if directory.is_dir():
            found = sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
            if found:
                return found
    return []


def wallpaper_command(env: Env, image: Path) -> list[str]:
    """Hand the image to the repo's existing wallpaper tooling."""
    if shutil.which("qs") and env.live and not env.dry_run and subprocess.run(
            ["qs", "-c", "noctalia-shell", "ipc", "show"], capture_output=True, check=False).returncode == 0:
        return ["qs", "-c", "noctalia-shell", "ipc", "call", "wallpaper", "set", str(image), "all"]
    return [str(ROOT / "scripts/wallpaper-mode.sh"), "static", str(image)]


def apply_palette(env: Env, palette: dict, *, source: str, reload: bool = True,
                  wallpaper: bool = True, wallpaper_step: int = 0) -> list[str]:
    log: list[str] = []
    files = render_all(env, palette)
    for relative, text in files.items():
        path = env.generated / relative
        if env.dry_run:
            same = path.exists() and path.read_text() == text
            log.append(f"{'unchanged' if same else 'would write'} {path}")
        else:
            log.append(f"{'wrote    ' if write_if_changed(path, text) else 'unchanged'} {path}")
    base = kvantum_base(env)
    if base and not env.dry_run:
        link = env.generated / f"kvantum/{SCHEME}/{SCHEME}.svg"
        svg = base[1].with_suffix(".svg")
        if svg.is_file() and not link.is_symlink():
            link.symlink_to(svg)
        env.save_state(kvantum_base=base[0])
    stale = [p for p in env.generated.rglob("*") if p.is_file() and not p.is_symlink()
             and str(p.relative_to(env.generated)) not in files] if env.generated.is_dir() else []
    for path in stale:
        log.append(f"{'would remove' if env.dry_run else 'removed  '} {path}")
        if not env.dry_run:
            path.unlink()
    state = env.state()
    index = int(state.get("wallpaper_index", {}).get(palette["slug"], 0))
    images = wallpapers(env, palette) if source == "theme" else []
    if images:
        index = (index + wallpaper_step) % len(images)
    env.save_state(slug=palette["slug"], source=source,
                   wallpaper_index={**state.get("wallpaper_index", {}), palette["slug"]: index})
    if reload:
        for component in COMPONENTS:
            if component.live and component_wired(env, component):
                run_live(env, component.live(env, palette), log)
        if wallpaper and images:
            # State is saved first: the wallpaper hook must already see who owns the look.
            run_live(env, [wallpaper_command(env, images[index])], log)
    return log


def resolve_palette(env: Env, slug: str) -> dict:
    if slug == WALLPAPER_SLUG:
        colours = env.home / ".cache/wal/colors.json"
        if not colours.is_file():
            raise SystemExit(f"theme: no pywal palette at {colours}; set a wallpaper first")
        return normalise(parse_pywal(colours), name="Wallpaper", slug=WALLPAPER_SLUG)
    path = env.themes / slug / "palette.toml"
    if not path.is_file():
        raise SystemExit(f"theme: unknown theme {slug!r} (see `theme list`)")
    return load_palette(path)


def cmd_list(env: Env, _args: argparse.Namespace) -> int:
    current = env.state().get("slug")
    for slug in list_themes(env):
        palette = load_palette(env.themes / slug / "palette.toml")
        mark = "*" if slug == current else " "
        print(f"{mark} {slug:<28} {palette['mode']:<5} {palette['colors']['background']} "
              f"{palette['colors']['accent']}  {len(wallpapers(env, palette))} wallpapers")
    return 0


def cmd_current(env: Env, _args: argparse.Namespace) -> int:
    state = env.state()
    if not state.get("slug"):
        print("none (theme manager not activated; pywal flow is in charge)")
        return 1
    print(f"{state['slug']} (source: {state.get('source', 'theme')})")
    return 0


def cmd_apply(env: Env, args: argparse.Namespace) -> int:
    palette = resolve_palette(env, args.slug)
    source = "wallpaper" if args.slug == WALLPAPER_SLUG else "theme"
    for line in apply_palette(env, palette, source=source, reload=not args.no_reload,
                              wallpaper=not args.keep_wallpaper):
        print(line)
    return 0


def cmd_step(env: Env, args: argparse.Namespace) -> int:
    themes = list_themes(env)
    if not themes:
        raise SystemExit("theme: no themes imported")
    current = env.state().get("slug")
    step = 1 if args.command == "next" else -1
    index = (themes.index(current) + step) % len(themes) if current in themes else 0
    args.slug, args.no_reload, args.keep_wallpaper = themes[index], False, False
    return cmd_apply(env, args)


def pick_rows(env: Env) -> str:
    """rofi -dmenu input: one row per theme, with its preview as the icon."""
    rows = []
    for slug in list_themes(env):
        palette = load_palette(env.themes / slug / "palette.toml")
        preview = palette["extras"].get("preview", "")
        rows.append(f"{slug}\0icon\x1f{preview}" if preview and Path(preview).is_file() else slug)
    return "\n".join(rows)


def cmd_pick(env: Env, args: argparse.Namespace) -> int:
    if not env.live:
        raise SystemExit("theme: pick needs the live desktop (not available with --home)")
    chosen = subprocess.run(
        ["rofi", "-dmenu", "-i", "-p", "Theme", "-show-icons", "-theme-str",
         "element-icon { size: 6em; } listview { columns: 3; lines: 4; }"],
        input=pick_rows(env), capture_output=True, text=True, check=False).stdout.strip()
    if not chosen:
        return 0
    args.slug, args.no_reload, args.keep_wallpaper = chosen, False, False
    return cmd_apply(env, args)


def cmd_import(env: Env, args: argparse.Namespace) -> int:
    cache = Path(os.environ.get("THEME_IMPORT_CACHE", DEFAULT_IMPORT_CACHE))
    if args.all:
        sources = sorted(path for path in cache.iterdir() if path.is_dir()) if cache.is_dir() else []
        if not sources:
            raise SystemExit(f"theme: nothing to import in {cache}")
    elif args.source:
        candidate = Path(args.source).expanduser()
        sources = [candidate if candidate.exists() else cache / args.source]
    else:
        raise SystemExit("theme: import needs a path, a cache slug, or --all")
    failed = 0
    seen: dict[str, Path] = {}
    for source in sources:
        try:
            slug = args.slug if not args.all else slugify(source.name)
            if slug in seen:
                raise ValueError(f"slug {slug} already taken by {seen[slug].name}")
            seen[slug or source.name] = source
            record = import_theme(source, env.themes, slug=args.slug if not args.all else None,
                                  dry_run=env.dry_run)
            print(f"imported  {record['slug']:<28} {record['format']:<20} {record['commit'] or 'no commit recorded'}")
        except (ValueError, OSError, tomllib.TOMLDecodeError) as error:
            failed += 1
            print(f"FAILED    {source.name}: {error}", file=sys.stderr)
    return 1 if failed else 0


def cmd_wallpaper_mode(env: Env, args: argparse.Namespace) -> int:
    """Hand the look back to the wallpaper: pywal becomes the palette source."""
    args.slug, args.keep_wallpaper = WALLPAPER_SLUG, True
    args.no_reload = getattr(args, "no_reload", False)
    return cmd_apply(env, args)


def cmd_wallpaper(env: Env, args: argparse.Namespace) -> int:
    state = env.state()
    if state.get("source") != "theme":
        raise SystemExit("theme: no fixed theme is active")
    palette = resolve_palette(env, state["slug"])
    if not wallpapers(env, palette):
        raise SystemExit(f"theme: {state['slug']} has no wallpapers")
    log = apply_palette(env, palette, source="theme", reload=True,
                        wallpaper_step=1 if args.direction == "next" else -1)
    print("\n".join(line for line in log if "wallpaper" in line))
    return 0


def _undo_path(env: Env) -> Path:
    return env.state_dir / "wired.json"


def cmd_wire(env: Env, args: argparse.Namespace) -> int:
    names = [c.name for c in COMPONENTS] if args.all else args.components
    if not names:
        raise SystemExit("theme: name components to wire, or pass --all")
    unknown = [name for name in names if name not in BY_NAME]
    if unknown:
        raise SystemExit(f"theme: unknown component(s): {', '.join(unknown)}")
    undo_file = _undo_path(env)
    undo = json.loads(undo_file.read_text()) if undo_file.exists() else {}
    failed = False
    for name in names:
        for wire in BY_NAME[name].wires:
            line = (undo_wire if args.command == "unwire" else apply_wire)(env, wire, undo)
            failed |= line.startswith("MISSING")
            print(f"{name:<10}{line}")
    if not env.dry_run:
        write_if_changed(undo_file, json.dumps(undo, indent=2, sort_keys=True) + "\n")
    return 1 if failed else 0


def cmd_doctor(env: Env, _args: argparse.Namespace) -> int:
    state = env.state()
    print(f"theme: {state.get('slug', 'none')} (source: {state.get('source', 'pywal flow, manager inactive')})")
    print(f"generated: {env.generated}")
    print(f"{'component':<10} {'tool':<8} {'generated':<10} {'wired':<8} reload")
    palette = None
    if state.get("slug"):
        try:
            palette = resolve_palette(env, state["slug"])
        except SystemExit:
            pass
    sample = palette or normalise({"background": "#000000", "foreground": "#ffffff"}, name="x", slug="x")
    for component in COMPONENTS:
        tool = "-" if not component.binary else ("yes" if shutil.which(component.binary) else "MISSING")
        generated = all((env.generated / relative).is_file() for relative in component.render(sample))
        states = wire_states(env, component)
        wired = "yes" if component_wired(env, component) else ("partial" if "wired" in states else "no")
        print(f"{component.name:<10} {tool:<8} {'yes' if generated else 'no':<10} {wired:<8} {component.reload}")
    print("\nnot derivable from a palette:")
    icon = (palette or {}).get("extras", {}).get("icon_theme")
    if icon:
        installed = any((base / icon).is_dir() for base in
                        (Path("/usr/share/icons"), env.home / ".local/share/icons", env.home / ".icons"))
        print(f"  icon theme   theme suggests {icon!r}: {'installed' if installed else 'NOT installed (left unchanged)'}")
    else:
        print("  icon theme   no suggestion in this theme (left unchanged)")
    if palette:
        print(f"  neovim       {nvim_choice(palette)[2]}")
    print(f"  kvantum      {'recolouring ' + kvantum_base(env)[0] if kvantum_base(env) else 'no base Kvantum theme found; qt6ct palette only'}")
    print("  cursor theme, fonts, SDDM, p10k prompt segments, Zed/Tern/VS Code themes: unmanaged")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="theme", description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path, help="act on this directory instead of $HOME; never touches the session")
    parser.add_argument("--themes-dir", type=Path, default=DEFAULT_THEMES, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="print what would change; write and run nothing")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--themes-dir", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=lambda **kw: argparse.ArgumentParser(parents=[common], **kw))
    sub.add_parser("list", help="list themes").set_defaults(run=cmd_list)
    sub.add_parser("current", help="print the active theme").set_defaults(run=cmd_current)
    apply = sub.add_parser("apply", help="render a theme and reload wired components")
    apply.add_argument("slug")
    apply.add_argument("--no-reload", action="store_true", help="write files only")
    apply.add_argument("--keep-wallpaper", action="store_true", help="do not change the wallpaper")
    apply.set_defaults(run=cmd_apply)
    for name in ("next", "prev"):
        sub.add_parser(name, help=f"apply the {name} theme").set_defaults(run=cmd_step)
    sub.add_parser("pick", help="choose a theme in rofi").set_defaults(run=cmd_pick)
    imp = sub.add_parser("import", help="normalise an Omarchy theme directory (data only)")
    imp.add_argument("source", nargs="?", help="directory, pywal colors.json, or slug in the import cache")
    imp.add_argument("--all", action="store_true", help="import every theme in the cache")
    imp.add_argument("--slug", help="name to import as")
    imp.set_defaults(run=cmd_import)
    sub.add_parser("doctor", help="show what is generated and wired").set_defaults(run=cmd_doctor)
    mode = sub.add_parser("wallpaper-mode", help="derive the palette from the wallpaper (pywal)")
    mode.add_argument("--no-reload", action="store_true")
    mode.set_defaults(run=cmd_wallpaper_mode)
    wall = sub.add_parser("wallpaper", help="step through the active theme's wallpapers")
    wall.add_argument("direction", choices=("next", "prev"))
    wall.set_defaults(run=cmd_wallpaper)
    for name in ("wire", "unwire"):
        wire = sub.add_parser(name, help=f"{name} component configs to the generated directory")
        wire.add_argument("components", nargs="*")
        wire.add_argument("--all", action="store_true")
        wire.set_defaults(run=cmd_wire)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = Env(home=(args.home or Path.home()).resolve(), themes=args.themes_dir.resolve(),
              live=args.home is None and not os.environ.get("THEME_NO_LIVE"), dry_run=args.dry_run)
    return args.run(env, args)


if __name__ == "__main__":
    raise SystemExit(main())
