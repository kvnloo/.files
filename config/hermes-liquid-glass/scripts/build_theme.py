#!/usr/bin/env python3
"""Build a Hermes Desktop liquid-glass theme from pywal colors.json.

Writes:
  ~/.cache/wal/hermes-liquid-glass-theme.json   — DesktopTheme payload
  ~/.cache/wal/hermes-liquid-glass-meta.json    — wallpaper path + mtime stamp

The Desktop runtime plugin (or apply.sh via CDP fallback) reads the theme JSON
and installs it as user theme ``liquid-glass-wal``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE = Path.home() / ".cache/wal"
COLORS_JSON = CACHE / "colors.json"
OUT_THEME = CACHE / "hermes-liquid-glass-theme.json"
OUT_META = CACHE / "hermes-liquid-glass-meta.json"
THEME_NAME = "liquid-glass-wal"
THEME_LABEL = "Liquid Glass (pywal)"

MIN_ACCENT_CONTRAST = 4.5
MIN_MUTED_CONTRAST = 4.5


def rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b)


def hex_color(channels: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{c:02x}" for c in channels)


def clamp_channel(n: float) -> int:
    return max(0, min(255, int(round(n))))


def mix(a: str, b: str, t: float) -> str:
    """Mix hex a→b by t (0=a, 1=b)."""
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    return hex_color(
        (
            clamp_channel(ar + (br - ar) * t),
            clamp_channel(ag + (bg - ag) * t),
            clamp_channel(ab + (bb - ab) * t),
        )
    )


def luminance(value: str) -> float:
    chans = []
    for channel in rgb(value):
        x = channel / 255.0
        chans.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def contrast(a: str, b: str) -> float:
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def ensure_contrast(fg: str, bg: str, minimum: float) -> str:
    if contrast(fg, bg) >= minimum:
        return fg
    target = (255, 255, 255) if luminance(bg) < 0.35 else (0, 0, 0)
    src = rgb(fg)
    for step in range(1, 25):
        t = step / 24
        cand = hex_color(
            (
                clamp_channel(src[0] + (target[0] - src[0]) * t),
                clamp_channel(src[1] + (target[1] - src[1]) * t),
                clamp_channel(src[2] + (target[2] - src[2]) * t),
            )
        )
        if contrast(cand, bg) >= minimum:
            return cand
    return hex_color(target)


def pick_accent(colors: dict[str, str], background: str) -> str:
    """Prefer chromatic pywal stops with enough contrast on the chrome."""
    candidates = [colors[f"color{i}"] for i in (4, 5, 6, 1, 2, 3, 9, 10, 11, 12, 13, 14)]
    ranked = sorted(
        candidates,
        key=lambda c: (contrast(c, background), abs(luminance(c) - 0.45)),
        reverse=True,
    )
    for cand in ranked:
        if contrast(cand, background) >= MIN_ACCENT_CONTRAST:
            return cand
    # Fall back: push best candidate toward white/black until readable.
    return ensure_contrast(ranked[0], background, MIN_ACCENT_CONTRAST)


def readable_on(bg: str) -> str:
    return "#0c0c0e" if luminance(bg) > 0.55 else "#f4f6f8"


def build_theme(palette: dict) -> dict:
    special = palette["special"]
    colors = palette["colors"]
    wallpaper = palette.get("wallpaper") or ""

    background = special["background"]
    foreground = ensure_contrast(special["foreground"], background, 7.0)
    muted_fg = ensure_contrast(colors.get("color8", foreground), background, MIN_MUTED_CONTRAST)
    accent = pick_accent(colors, background)
    accent_fg = readable_on(accent)

    # Layered frost stack — surfaces sit slightly above chrome so compositor
    # blur reads through gaps; not solid slabs.
    sidebar = mix(background, accent, 0.06)
    card = mix(background, accent, 0.09)
    popover = mix(background, accent, 0.11)
    muted = mix(background, accent, 0.08)
    secondary = mix(background, accent, 0.14)
    bubble = mix(background, accent, 0.12)
    border = mix(background, accent, 0.28)
    sidebar_border = mix(background, accent, 0.22)

    is_dark = luminance(background) < 0.45
    destructive = ensure_contrast("#e75e78" if is_dark else "#c72e4d", background, 3.0)

    colors_bag = {
        "background": background,
        "foreground": foreground,
        "card": card,
        "cardForeground": foreground,
        "muted": muted,
        "mutedForeground": muted_fg,
        "popover": popover,
        "popoverForeground": foreground,
        "primary": accent,
        "primaryForeground": accent_fg,
        "secondary": secondary,
        "secondaryForeground": foreground,
        "accent": mix(background, accent, 0.18),
        "accentForeground": foreground,
        "border": border,
        "input": mix(background, accent, 0.04),
        "ring": accent,
        "midground": accent,
        "composerRing": accent,
        "destructive": destructive,
        "destructiveForeground": readable_on(destructive),
        "sidebarBackground": sidebar,
        "sidebarBorder": sidebar_border,
        "userBubble": bubble,
        "userBubbleBorder": border,
    }

    # Single-mode palette mirrored so light/dark toggle stays faithful to wal.
    theme = {
        "name": THEME_NAME,
        "label": THEME_LABEL,
        "description": f"pywal liquid glass · {wallpaper or 'wallpaper'}",
        "colors": colors_bag,
        "darkColors": dict(colors_bag),
        "typography": {
            "fontSans": '"Segoe WPC", "Segoe UI", -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
            "fontMono": 'Menlo, Monaco, "SF Mono", "JetBrains Mono", monospace',
        },
        # Glass mix knobs consumed by the Desktop plugin (not native DesktopTheme).
        "hermesGlass": {
            "chrome": "48%" if is_dark else "78%",
            "sidebar": "62%" if is_dark else "90%",
            "card": "14%" if is_dark else "18%",
            "elevated": "18%" if is_dark else "24%",
            "bubble": "16%" if is_dark else "12%",
        },
        "hermesWal": {
            "wallpaper": wallpaper,
            "background": background,
            "foreground": foreground,
            "accent": accent,
            "isDark": is_dark,
            "builtAt": time.time(),
        },
    }
    return theme


def main() -> None:
    if not COLORS_JSON.is_file():
        raise SystemExit(f"missing {COLORS_JSON} — run wal first")

    palette = json.loads(COLORS_JSON.read_text())
    theme = build_theme(palette)
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT_THEME.write_text(json.dumps(theme, indent=2) + "\n")
    OUT_META.write_text(
        json.dumps(
            {
                "themePath": str(OUT_THEME),
                "wallpaper": palette.get("wallpaper"),
                "mtime": os.path.getmtime(COLORS_JSON),
                "builtAt": time.time(),
                "name": THEME_NAME,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "ok": True,
                "theme": str(OUT_THEME),
                "name": THEME_NAME,
                "accent": theme["hermesWal"]["accent"],
                "background": theme["hermesWal"]["background"],
                "wallpaper": theme["hermesWal"]["wallpaper"],
            }
        )
    )


if __name__ == "__main__":
    main()
