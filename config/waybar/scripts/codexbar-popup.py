#!/usr/bin/env python3
"""GTK4 popover for CodexBar Linux CLI.

Mirrors the upstream macOS CodexBar menu popover: a wide rounded lavender
panel, large provider icon tabs, stacked usage sections, thin progress bars,
and the same lower action rows as the reference design.

Anchored top-right via gtk4-layer-shell. Reads the cached last.json for
instant paint, then refetches in the background.
"""

from __future__ import annotations

import datetime
import json
import os
import signal
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Thread

# gtk4-layer-shell must load before libwayland-client; re-exec with LD_PRELOAD.
# Override the lib location with CODEXBAR_LAYER_SHELL_LIB if needed.
_LAYER_SHELL_LIB_CANDIDATES = [
    os.environ.get("CODEXBAR_LAYER_SHELL_LIB", ""),
    "/usr/lib/libgtk4-layer-shell.so",                   # Arch
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",  # Debian / Ubuntu
    "/usr/lib64/libgtk4-layer-shell.so",                 # Fedora
    "/usr/lib/aarch64-linux-gnu/libgtk4-layer-shell.so",
]
_LAYER_SHELL_LIB = next((p for p in _LAYER_SHELL_LIB_CANDIDATES if p and os.path.exists(p)), "")
if os.environ.get("CODEXBAR_POPUP_PRELOADED") != "1" and _LAYER_SHELL_LIB:
    env = dict(os.environ)
    existing = env.get("LD_PRELOAD", "")
    env["LD_PRELOAD"] = f"{_LAYER_SHELL_LIB}:{existing}" if existing else _LAYER_SHELL_LIB
    env["CODEXBAR_POPUP_PRELOADED"] = "1"
    os.execve(sys.executable, [sys.executable, *sys.argv], env)

import re  # noqa: E402

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import GLib, Gtk, Gtk4LayerShell  # noqa: E402


def resolve_codexbar_bin() -> str:
    override = os.environ.get("CODEXBAR_BIN")
    if override:
        return override
    found = shutil.which("codexbar")
    return found or str(Path.home() / ".local/bin/codexbar")


CODEXBAR = resolve_codexbar_bin()
CACHE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "codexbar-waybar"
LAST_GOOD = CACHE / "last.json"
SCRIPT_DIR = Path(__file__).resolve().parent
WRAPPER = SCRIPT_DIR / "codexbar.sh"

PROVIDER_NAMES = {
    "codex": "Codex",
    "claude": "Claude",
    "gemini": "Gemini",
    "copilot": "Copilot",
    "cursor": "Cursor",
    "droid": "Droid",
    "factory": "Droid",
    "vertexai": "Vertex AI",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "kimik2": "Kimi K2",
    "antigravity": "Antigravity",
}

REFERENCE_PROVIDER_ORDER = ("codex", "claude", "cursor", "factory", "gemini", "copilot")

WINDOW_LABELS = {
    "primary": "Session",
    "secondary": "Weekly",
    "tertiary": "Monthly",
}

PROVIDER_STATUS_URLS = {
    "codex": "https://status.openai.com",
    "openai": "https://status.openai.com",
    "claude": "https://status.anthropic.com",
    "gemini": "https://status.cloud.google.com",
    "vertexai": "https://status.cloud.google.com",
    "copilot": "https://www.githubstatus.com",
    "droid": "https://status.factory.ai",
    "factory": "https://status.factory.ai",
}

# Provider id → icon filename (without the "ProviderIcon-" prefix and ".svg").
# Most providers map to their own id; a few share an icon upstream.
PROVIDER_ICON_ALIAS = {
    "openai": "codex",
    "droid": "factory",
    "moonshot": "kimi",
    "kimik2": "kimi",
}

MENU_GLYPHS = {
    "add-account": "\uf084",       # nf-fa-key
    "dashboard": "\uf080",         # nf-fa-bar_chart
    "status": "\uf21e",            # nf-fa-heartbeat
}

# Providers that have at least one non-web Linux path (OAuth, API key, CLI,
# local probe). Everything else either requires browser cookies or is gated to
# macOS in the upstream CLI.
LINUX_SUPPORTED = {
    "codex", "claude", "gemini", "copilot", "cursor", "droid", "factory", "kilo", "openrouter", "deepseek",
    "moonshot", "codebuff", "zai", "warp", "venice", "crof", "minimax",
    "kimik2", "vertexai", "antigravity",
}


def resolve_config_path() -> Path:
    override = os.environ.get("CODEXBAR_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    xdg_config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    xdg_path = xdg_config_home / "codexbar" / "config.json"
    legacy_path = Path.home() / ".codexbar" / "config.json"
    if xdg_path.exists() or not legacy_path.exists():
        return xdg_path
    return legacy_path


CONFIG_PATH = resolve_config_path()
STATE_PATH = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "codexbar-waybar" / "state.json"
ICONS_DIR = Path(
    os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
) / "codexbar-waybar" / "icons"


def _env_float(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _env_int(name: str, default: int, *, min_value: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, value)


POPUP_SCALE = _env_float("CODEXBAR_POPUP_SCALE", 0.50, min_value=0.35, max_value=1.25)


def sx(value: int | float) -> int:
    return max(1, int(round(float(value) * POPUP_SCALE)))


POPUP_WIDTH = _env_int("CODEXBAR_POPUP_WIDTH", sx(620), min_value=280)
POPUP_EDGE = os.environ.get("CODEXBAR_POPUP_EDGE", "bottom").strip().lower()
if POPUP_EDGE not in {"top", "bottom"}:
    POPUP_EDGE = "bottom"
POPUP_RIGHT_MARGIN = _env_int("CODEXBAR_POPUP_RIGHT_MARGIN", sx(52), min_value=0)
POPUP_TOP_MARGIN = _env_int("CODEXBAR_POPUP_TOP_MARGIN", sx(63), min_value=0)
POPUP_BOTTOM_MARGIN = _env_int("CODEXBAR_POPUP_BOTTOM_MARGIN", 38, min_value=0)

# CSS mirrors the macOS menu popover reference at 2x screenshot pixels.
# The panel is painted as an averaged lavender material so desktop text does
# not bleed through when the compositor cannot provide macOS-style vibrancy.
BASE_CSS = """
/* The window itself stays transparent so the root box can paint rounded corners. */
window.codexbar-popup {
    background-color: transparent;
    background-image: none;
}

.codexbar-root {
    background-color: #c9ccff;
    background-image: linear-gradient(145deg, #d1cfff 0%, #d5d0fb 25%, #c5c9ff 62%, #c2c6ff 100%);
    color: #1f1c2d;
    font-family: "SFNS Display", "Noto Sans", sans-serif;
    border-radius: 21px;
    border: 1px solid rgba(255,255,255,0.62);
    padding: 0;
    min-width: 620px;
}

.codexbar-root > * {
    background-color: transparent;
    background-image: none;
}

/* --- Tab strip --- */
.codexbar-tabbar {
    background-color: transparent;
    padding: 8px 31px 4px 31px;
    border-bottom: 1px solid #ccbbe6;
    border-top-left-radius: 21px;
    border-top-right-radius: 21px;
}

.codexbar-tab {
    padding: 7px 13px;
    border-radius: 10px;
    color: #69657a;
    font-size: 20px;
    font-weight: 500;
    background-color: transparent;
}
.codexbar-tab:hover {
    background-color: rgba(255,255,255,0.20);
    color: #292638;
}
.codexbar-tab.active,
.codexbar-tab.active:hover {
    background-color: #2f7df4;
    color: #ffffff;
}
.codexbar-tab label { color: inherit; font-size: 20px; font-weight: 500; }

.codexbar-provider-tab {
    padding: 8px 5px 6px 5px;
    border-radius: 10px;
    color: #6e6a82;
    background-color: transparent;
    min-width: 64px;
    min-height: 57px;
}
.codexbar-provider-tab:hover {
    background-color: rgba(255,255,255,0.20);
}
.codexbar-provider-tab.active,
.codexbar-provider-tab.active:hover {
    background-color: #2f7df4;
    color: #ffffff;
}
.codexbar-provider-tab label {
    color: inherit;
    font-size: 18px;
    font-weight: 500;
}

.codexbar-iconbtn {
    padding: 5px 9px;
    border-radius: 8px;
    color: #6e6a82;
    font-size: 13px;
    background-color: transparent;
}
.codexbar-iconbtn:hover {
    background-color: rgba(255,255,255,0.20);
    color: #292638;
}
.codexbar-iconbtn label { color: inherit; font-size: 13px; }

/* --- Body --- */
.codexbar-body {
    background-color: transparent;
    padding: 30px 31px 0 31px;
}

.codexbar-provider-title {
    font-size: 26px;
    font-weight: 700;
    color: #242130;
}
.codexbar-plan {
    font-size: 20px;
    font-weight: 500;
    color: #6d687d;
}
.codexbar-subtitle {
    font-size: 20px;
    color: #6d687d;
}
.codexbar-divider {
    background-color: #b4b6e5;
    min-height: 1px;
    margin: 17px 0 26px 0;
}
.codexbar-divider.codexbar-header-divider {
    margin: 11px 0 32px 0;
}
.codexbar-divider.codexbar-after-cost-divider {
    margin-bottom: 8px;
}
.codexbar-divider.codexbar-before-footer-divider {
    margin-bottom: 20px;
}
.codexbar-section-title {
    font-size: 26px;
    font-weight: 700;
    color: #242130;
    margin-bottom: 11px;
}
.codexbar-extra-title {
    margin-bottom: 23px;
}
.codexbar-usage-section {
    margin-bottom: 26px;
}
.codexbar-section-detail-left {
    font-size: 20px;
    color: #201e2d;
    font-feature-settings: "tnum";
}
.codexbar-section-detail-right {
    font-size: 20px;
    color: #6d687d;
}
.codexbar-pace {
    font-size: 20px;
    color: #6d687d;
    margin-top: 10px;
}
.codexbar-credits {
    font-size: 20px;
    color: #201e2d;
    font-feature-settings: "tnum";
    font-weight: 500;
}
.codexbar-credits-label {
    font-size: 20px;
    color: #6d687d;
}
.codexbar-error {
    font-size: 20px;
    color: #c53030;
}

.codexbar-menu-row {
    padding: 0 0;
    color: #201e2d;
    background-color: transparent;
    min-height: 49px;
}
.codexbar-menu-row:hover {
    background-color: rgba(255,255,255,0.20);
}
.codexbar-menu-row label {
    color: inherit;
    font-size: 26px;
    font-weight: 400;
}
.codexbar-menu-icon {
    color: #201e2d;
    font-family: "JetBrainsMono Nerd Font", "Iosevka Nerd Font", "Noto Sans Symbols", monospace;
    font-size: 21px;
    min-width: 32px;
    margin: 0 14px 0 2px;
}
.codexbar-chevron {
    color: #69657a;
    font-size: 31px;
}
.codexbar-cost-row {
    margin-top: 3px;
}
.codexbar-cost-last-row {
    margin-top: 12px;
    margin-bottom: 30px;
}
.codexbar-extra-row {
    margin-top: 12px;
}

/* --- Settings view --- */
.codexbar-settings-title {
    font-size: 22px;
    font-weight: 600;
    color: #242130;
}
.codexbar-bar-picker {
    background-color: transparent;
    padding: 4px 0 8px 0;
}
.codexbar-provider-icon {
    margin: 0 2px;
}
.codexbar-settings-list {
    background-color: transparent;
}
.codexbar-settings-row {
    padding: 8px 0;
    border-bottom: 1px solid rgba(126,122,171,0.22);
}
.codexbar-settings-row.disabled .codexbar-settings-name {
    color: #8d879f;
}
.codexbar-settings-name {
    font-size: 20px;
    font-weight: 600;
    color: #242130;
}
.codexbar-settings-hint {
    font-size: 16px;
    color: #8d879f;
}
.codexbar-settings-group {
    font-size: 16px;
    font-weight: 600;
    color: #6d687d;
    padding: 14px 0 4px 0;
}

/* --- Progress bars: rounded muted lavender tracks, warm usage fill --- */
levelbar.codex-usage {
    background-color: transparent;
}
levelbar.codex-usage trough {
    background-color: transparent;
    background-image: none;
    padding: 0;
    min-height: 12px;
    border: none;
}
levelbar.codex-usage block.filled {
    background-color: #c9835a;
    background-image: none;
    min-height: 12px;
    border-radius: 6px;
    border: none;
}
levelbar.codex-usage.warning block.filled  { background-color: #c9835a; }
levelbar.codex-usage.critical block.filled { background-color: #c9835a; }
levelbar.codex-usage block.empty {
    background-color: rgba(174,173,220,0.66);
    background-image: none;
    min-height: 12px;
    border-radius: 6px;
    border: none;
}

levelbar.codex-tab-meter {
    background-color: transparent;
}
levelbar.codex-tab-meter trough {
    background-color: transparent;
    background-image: none;
    padding: 0;
    min-height: 6px;
    border: none;
}
levelbar.codex-tab-meter block.filled {
    background-color: #6abcb5;
    background-image: none;
    min-height: 6px;
    border-radius: 4px;
    border: none;
}
levelbar.codex-tab-meter block.empty {
    background-color: rgba(135,131,170,0.48);
    background-image: none;
    min-height: 6px;
    border-radius: 4px;
    border: none;
}
.codexbar-provider-tab.active levelbar.codex-tab-meter {
    opacity: 0;
}
"""


def build_css() -> bytes:
    css = BASE_CSS
    replacements = {
        "border-radius: 21px;": f"border-radius: {sx(21)}px;",
        "border-top-left-radius: 21px;": f"border-top-left-radius: {sx(21)}px;",
        "border-top-right-radius: 21px;": f"border-top-right-radius: {sx(21)}px;",
        "min-width: 620px;": f"min-width: {POPUP_WIDTH}px;",
        "padding: 8px 31px 4px 31px;": f"padding: {sx(8)}px {sx(31)}px {sx(4)}px {sx(31)}px;",
        "padding: 7px 13px;": f"padding: {sx(7)}px {sx(13)}px;",
        "border-radius: 10px;": f"border-radius: {sx(10)}px;",
        "font-size: 20px;": f"font-size: {sx(20)}px;",
        "font-size: 18px;": f"font-size: {sx(18)}px;",
        "padding: 8px 5px 6px 5px;": f"padding: {sx(8)}px {sx(5)}px {sx(6)}px {sx(5)}px;",
        "min-width: 64px;": f"min-width: {sx(64)}px;",
        "min-height: 57px;": f"min-height: {sx(57)}px;",
        "padding: 5px 9px;": f"padding: {sx(5)}px {sx(9)}px;",
        "border-radius: 8px;": f"border-radius: {sx(8)}px;",
        "font-size: 13px;": f"font-size: {sx(13)}px;",
        "padding: 30px 31px 0 31px;": f"padding: {sx(30)}px {sx(31)}px 0 {sx(31)}px;",
        "font-size: 26px;": f"font-size: {sx(26)}px;",
        "font-size: 21px;": f"font-size: {sx(21)}px;",
        "min-width: 32px;": f"min-width: {sx(32)}px;",
        "margin: 17px 0 26px 0;": f"margin: {sx(17)}px 0 {sx(26)}px 0;",
        "margin: 11px 0 32px 0;": f"margin: {sx(11)}px 0 {sx(32)}px 0;",
        "margin-bottom: 11px;": f"margin-bottom: {sx(11)}px;",
        "margin-bottom: 23px;": f"margin-bottom: {sx(23)}px;",
        "margin-bottom: 26px;": f"margin-bottom: {sx(26)}px;",
        "margin-top: 10px;": f"margin-top: {sx(10)}px;",
        "min-height: 49px;": f"min-height: {sx(49)}px;",
        "margin: 0 14px 0 2px;": f"margin: 0 {sx(14)}px 0 {sx(2)}px;",
        "font-size: 31px;": f"font-size: {sx(31)}px;",
        "margin-top: 3px;": f"margin-top: {sx(3)}px;",
        "margin-top: 12px;": f"margin-top: {sx(12)}px;",
        "margin-bottom: 30px;": f"margin-bottom: {sx(30)}px;",
        "margin-bottom: 8px;": f"margin-bottom: {sx(8)}px;",
        "margin-bottom: 20px;": f"margin-bottom: {sx(20)}px;",
        "font-size: 22px;": f"font-size: {sx(22)}px;",
        "padding: 4px 0 8px 0;": f"padding: {sx(4)}px 0 {sx(8)}px 0;",
        "margin: 0 2px;": f"margin: 0 {sx(2)}px;",
        "padding: 8px 0;": f"padding: {sx(8)}px 0;",
        "font-size: 16px;": f"font-size: {sx(16)}px;",
        "padding: 14px 0 4px 0;": f"padding: {sx(14)}px 0 {sx(4)}px 0;",
        "min-height: 12px;": f"min-height: {sx(12)}px;",
        "min-height: 6px;": f"min-height: {sx(6)}px;",
        "border-radius: 6px;": f"border-radius: {sx(6)}px;",
        "border-radius: 4px;": f"border-radius: {sx(4)}px;",
    }
    for old, new in replacements.items():
        css = css.replace(old, new)
    return css.encode()


CSS = build_css()


def load_cached() -> list:
    if LAST_GOOD.exists():
        try:
            return json.loads(LAST_GOOD.read_text())
        except json.JSONDecodeError:
            return []
    return []


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


_ICON_CACHE: dict[tuple[str, str], Path] = {}


def resolve_icon_path(pid: str, color: str = "#6e6a82") -> Path | None:
    """Return a recoloured copy of the provider SVG for the current tab state.
    Upstream SVGs use `fill=\"white\"`; we substitute that with the requested
    theme colour and cache the generated file."""
    name = PROVIDER_ICON_ALIAS.get(pid, pid)
    cache_key = (name, color)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]
    src = ICONS_DIR / f"ProviderIcon-{name}.svg"
    if not src.exists():
        return None
    out_dir = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "codexbar-waybar" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = color.lstrip("#").lower()
    out = out_dir / f"{name}-{suffix}.svg"
    try:
        svg = src.read_text()
        recoloured = svg.replace('fill="white"', f'fill="{color}"') \
                        .replace("fill='white'", f"fill='{color}'") \
                        .replace('fill="#ffffff"', f'fill="{color}"') \
                        .replace('fill="#FFFFFF"', f'fill="{color}"') \
                        .replace('stroke="white"', f'stroke="{color}"') \
                        .replace("stroke='white'", f"stroke='{color}'") \
                        .replace('stroke="#ffffff"', f'stroke="{color}"') \
                        .replace('stroke="#FFFFFF"', f'stroke="{color}"')
        out.write_text(recoloured)
        _ICON_CACHE[cache_key] = out
        return out
    except OSError:
        return None


def make_icon(pid: str, size: int = 18, color: str = "#6e6a82") -> Gtk.Widget | None:
    path = resolve_icon_path(pid, color)
    if path is None:
        return None
    img = Gtk.Image.new_from_file(str(path))
    img.set_pixel_size(size)
    img.add_css_class("codexbar-provider-icon")
    return img


_RESET_SPACE_AFTER = re.compile(r"^([Rr]esets)(?=\S)")
_RESET_SPACE_BEFORE_PAREN = re.compile(r"(?<=\S)\(")
_RESET_SPACE_AFTER_COMMA = re.compile(r",(?=\S)")
_RESET_SPACE_BEFORE_AMPM = re.compile(r"(?<=\d)(?=[AaPp][Mm]\b)")
_RESET_STARTS_WITH_RESETS = re.compile(r"^[Rr]esets")
_RESET_RELATIVE = re.compile(r"^[Rr]esets in ")

RESET_FORMATS = ("provider", "local", "utc")


def normalize_reset_description(text: str) -> str:
    """Mirror codexbar.sh's reset normalisation. Handles both Claude OAuth
    (\"May 17 at 6:20AM\") and Claude CLI (\"Resets6:20am(Europe/Paris)\")
    by inserting the spaces the providers omit."""
    if not text:
        return text
    text = _RESET_SPACE_AFTER.sub(r"\1 ", text)
    text = _RESET_SPACE_BEFORE_PAREN.sub(" (", text)
    text = _RESET_SPACE_AFTER_COMMA.sub(", ", text)
    text = _RESET_SPACE_BEFORE_AMPM.sub(" ", text)
    return text


def current_reset_format(state: dict | None = None) -> str:
    """Resolve the active reset time format. Env var overrides state.json;
    unknown values fall back to `provider` (current behavior)."""
    env = os.environ.get("CODEXBAR_RESET_TIME_FORMAT")
    if env in RESET_FORMATS:
        return env
    if state is None:
        state = load_state()
    value = state.get("resetTimeFormat")
    return value if value in RESET_FORMATS else "provider"


def _from_description(desc: str) -> str:
    if not desc:
        return ""
    return desc if _RESET_STARTS_WITH_RESETS.match(desc) else f"Resets {desc}"


def format_reset_label(window: dict, mode: str) -> str:
    """Render the reset label for a usage window in the chosen format.

    Mirrors `reset_phrase` in codexbar.sh so the popover and tooltip never
    drift. Returns a string like "Resets 6:12 PM CDT" or "" for no info.
    Relative phrases ("Resets in 2 hours") are preserved even in absolute
    modes, since "in 2 hours" is more useful than a wall-clock time.
    """
    clean = normalize_reset_description(window.get("resetDescription") or "")
    from_desc = _from_description(clean)
    if mode == "provider":
        return from_desc
    if _RESET_RELATIVE.match(clean):
        return from_desc
    resets_at = window.get("resetsAt")
    if not resets_at:
        return from_desc
    try:
        ts = datetime.datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return from_desc
    if mode == "utc":
        ts = ts.astimezone(datetime.timezone.utc)
        tz_suffix = "UTC"
    else:
        ts = ts.astimezone()
        tz_suffix = ts.tzname() or ""
    now = datetime.datetime.now(ts.tzinfo)
    if ts.date() == now.date():
        body = ts.strftime("%-I:%M %p")
    elif ts.year == now.year:
        body = ts.strftime("%b %-d at %-I:%M %p")
    else:
        body = ts.strftime("%b %-d %Y at %-I:%M %p")
    return f"Resets {body} {tz_suffix}".rstrip()


def fetch_fresh() -> list:
    try:
        subprocess.run([str(WRAPPER)], check=False, capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return load_cached()


def max_pct(entry: dict) -> int:
    if entry.get("error"):
        return 0
    usage = entry.get("usage") or {}
    pcts = [
        (usage.get(k) or {}).get("usedPercent")
        for k in ("primary", "secondary", "tertiary")
    ]
    pcts = [p for p in pcts if isinstance(p, (int, float))]
    return int(max(pcts)) if pcts else 0


def default_provider(data: list) -> str | None:
    """Pick the provider with the highest used% as the initial tab."""
    if not data:
        return None
    healthy = [e for e in data if not e.get("error")]
    pool = healthy or data
    return max(pool, key=max_pct).get("provider")


def load_full_config() -> dict:
    """Returns the canonical config (every provider known to the CLI, with the
    current enabled flag merged in). Uses `codexbar config dump` so the schema
    stays in sync with the CLI version that's actually installed."""
    try:
        result = subprocess.run(
            [CODEXBAR, "config", "dump"],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    # Fallback: read whatever's on disk.
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"providers": [], "version": 1}


def save_config(enabled: dict[str, bool]) -> None:
    """Write only the providers we want enabled. The CLI fills in defaults for
    any provider missing from the file, so we don't need to list disabled ones."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "providers": [{"id": pid, "enabled": True} for pid, on in enabled.items() if on],
        "version": 1,
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def open_text_file(path: str) -> None:
    """Open a file in a real text editor.

    Resolution order (first hit wins):
      1. $CODEXBAR_EDITOR — explicit override (graphical command line).
      2. $VISUAL / $EDITOR — terminal editor, opened in a detected terminal.
      3. Common GUI editors discovered on PATH.
      4. xdg-open as a last resort (which is what was wrong before — it sends
         JSON to the browser on most setups).
    """
    explicit = os.environ.get("CODEXBAR_EDITOR")
    if explicit:
        subprocess.Popen([*explicit.split(), path])
        return

    gui_editors = [
        "code", "codium", "code-oss",
        "zed",
        "gnome-text-editor", "gedit", "kate", "mousepad", "xed", "leafpad",
        "sublime_text", "subl",
    ]
    for editor in gui_editors:
        which = subprocess.run(["which", editor], capture_output=True, text=True)
        if which.returncode == 0 and which.stdout.strip():
            subprocess.Popen([editor, path])
            return

    terminal_editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if terminal_editor:
        terminals = [
            ("kitty", ["kitty", "-e"]),
            ("alacritty", ["alacritty", "-e"]),
            ("foot", ["foot"]),
            ("wezterm", ["wezterm", "start", "--"]),
            ("gnome-terminal", ["gnome-terminal", "--"]),
            ("konsole", ["konsole", "-e"]),
            ("xterm", ["xterm", "-e"]),
        ]
        for term, cmd in terminals:
            which = subprocess.run(["which", term], capture_output=True, text=True)
            if which.returncode == 0:
                subprocess.Popen([*cmd, *terminal_editor.split(), path])
                return

    # Last resort. Usually opens the browser for .json — which is exactly what
    # we were trying to avoid — but better than silently failing.
    subprocess.Popen(["xdg-open", path])


class CodexBarPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.codexbar.linux.popup")
        self.window: Gtk.Window | None = None
        self.data: list = []
        self.active_pid: str | None = None
        self.tab_buttons: dict[str, Gtk.Widget] = {}
        self.view: str = "usage"             # "usage" | "settings"
        self.settings_switches: dict[str, Gtk.Switch] = {}

    def do_activate(self):  # noqa: N802
        if self.window is None:
            self.window = self.build_window()
        self.window.present()

    def _reference_tabs_enabled(self) -> bool:
        return os.environ.get("CODEXBAR_POPUP_REFERENCE_TABS", "1") not in {"0", "false", "False"}

    def _tab_entries(self) -> list[dict]:
        by_provider = {entry.get("provider"): entry for entry in self.data}
        ordered: list[dict] = []
        seen: set[str] = set()

        if self._reference_tabs_enabled():
            for pid in REFERENCE_PROVIDER_ORDER:
                entry = by_provider.get(pid)
                if entry is None and pid == "factory":
                    entry = by_provider.get("droid")
                if entry is None:
                    entry = {"provider": pid, "usage": {}, "_placeholder": True}
                ordered.append(entry)
                seen.add(entry.get("provider", pid))
                seen.add(pid)
                if pid == "factory":
                    seen.add("droid")

        for entry in self.data:
            pid = entry.get("provider", "")
            if pid and pid not in seen:
                ordered.append(entry)
                seen.add(pid)
        return ordered

    def _make_pill(self, label: str, css_classes: list[str], on_click,
                   *, icon_pid: str | None = None) -> Gtk.Widget:
        """A clickable pill made from Gtk.Box + Gtk.Label so we bypass
        Gtk.Button styling. Optionally prefixes a provider SVG icon."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_css_classes(css_classes)
        if icon_pid:
            icon = make_icon(icon_pid, size=sx(14))
            if icon is not None:
                box.append(icon)
        lbl = Gtk.Label(label=label)
        box.append(lbl)
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda _g, _n, _x, _y: on_click())
        box.add_controller(gesture)
        return box

    def _make_provider_tab(self, entry: dict) -> Gtk.Widget:
        pid = entry.get("provider", "")
        active = pid == self.active_pid
        tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        classes = ["codexbar-provider-tab"]
        if active:
            classes.append("active")
        tab.set_css_classes(classes)
        tab.set_size_request(sx(80), sx(57))
        tab.set_halign(Gtk.Align.CENTER)

        icon = make_icon(pid, size=sx(28), color="#ffffff" if active else "#6e6a82")
        if icon is not None:
            icon.set_halign(Gtk.Align.CENTER)
            tab.append(icon)

        label = Gtk.Label(label=PROVIDER_NAMES.get(pid, pid.title()))
        label.set_halign(Gtk.Align.CENTER)
        tab.append(label)

        meter = self._meter(max_pct(entry), ["codex-tab-meter"])
        meter.set_size_request(sx(70), sx(6))
        tab.append(meter)

        if not entry.get("_placeholder"):
            gesture = Gtk.GestureClick()
            gesture.connect("released", lambda _g, _n, _x, _y, p=pid: self._select(p))
            tab.add_controller(gesture)
        return tab

    def _meter(self, pct: int | float | None, css_classes: list[str]) -> Gtk.LevelBar:
        bar = Gtk.LevelBar()
        for css_class in css_classes:
            bar.add_css_class(css_class)
        bar.set_min_value(0)
        bar.set_max_value(100)
        bar.set_mode(Gtk.LevelBarMode.CONTINUOUS)
        bar.set_value(float(pct) if isinstance(pct, (int, float)) else 0)
        return bar

    def _menu_icon(self, glyph: str) -> Gtk.Widget:
        icon = Gtk.Label(label=glyph, xalign=0.5)
        icon.add_css_class("codexbar-menu-icon")
        return icon

    def _menu_row(self, label: str, on_click, *,
                  glyph: str | None = None,
                  chevron: bool = False) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("codexbar-menu-row")
        row.set_size_request(-1, sx(49))
        row.set_valign(Gtk.Align.CENTER)
        if glyph:
            row.append(self._menu_icon(glyph))
        text = Gtk.Label(label=label, xalign=0.0, hexpand=True)
        row.append(text)
        if chevron:
            arrow = Gtk.Label(label="›", xalign=1.0)
            arrow.add_css_class("codexbar-chevron")
            row.append(arrow)
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda _g, _n, _x, _y: on_click())
        row.add_controller(gesture)
        return row

    def build_window(self) -> Gtk.Window:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gtk.Window().get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = Gtk.Window(application=self)
        win.add_css_class("codexbar-popup")
        win.set_decorated(False)
        win.set_resizable(False)
        win.set_default_size(POPUP_WIDTH, 1)

        Gtk4LayerShell.init_for_window(win)
        Gtk4LayerShell.set_namespace(win, "codexbar-popup")
        Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, POPUP_EDGE == "top")
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.BOTTOM, POPUP_EDGE == "bottom")
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.RIGHT, True)
        Gtk4LayerShell.set_margin(
            win, Gtk4LayerShell.Edge.TOP, POPUP_TOP_MARGIN if POPUP_EDGE == "top" else 0)
        Gtk4LayerShell.set_margin(
            win, Gtk4LayerShell.Edge.BOTTOM, POPUP_BOTTOM_MARGIN if POPUP_EDGE == "bottom" else 0)
        Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.RIGHT, POPUP_RIGHT_MARGIN)
        Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_key)
        win.add_controller(ctrl)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.add_css_class("codexbar-root")
        win.set_child(root)

        self.tabbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.tabbar.add_css_class("codexbar-tabbar")
        root.append(self.tabbar)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.body.add_css_class("codexbar-body")
        root.append(self.body)

        self.data = load_cached()
        requested_pid = os.environ.get("CODEXBAR_INITIAL_PROVIDER")
        if requested_pid and any(e.get("provider") == requested_pid for e in self.data):
            self.active_pid = requested_pid
        else:
            self.active_pid = default_provider(self.data)
        if os.environ.get("CODEXBAR_INITIAL_VIEW") == "settings":
            self.view = "settings"
        self.render()
        if os.environ.get("CODEXBAR_DISABLE_REFRESH") != "1":
            self.refresh(background=True)
        return win

    def _on_key(self, _ctl, keyval, _kc, _state):
        if keyval == 0xff1b:  # Escape
            self.quit()
            return True
        return False

    def _on_settings_call(self):
        self.view = "settings"
        self.render()

    def _on_about_call(self):
        subprocess.Popen(["xdg-open", "https://codexbar.app"])

    def _on_settings_back(self):
        self.view = "usage"
        self.render()

    def _on_settings_save(self):
        enabled = {pid: sw.get_active() for pid, sw in self.settings_switches.items()}
        save_config(enabled)
        self.view = "usage"
        self.render()
        self.refresh(background=True)
        # Nudge waybar so the bar reflects the new provider list without
        # waiting for the next interval. The signal is wired up in codexbar.jsonc.
        subprocess.Popen(["pkill", "-RTMIN+8", "waybar"])

    def refresh(self, *, background: bool):
        def worker():
            new_data = fetch_fresh()
            GLib.idle_add(self._apply_refresh, new_data)
        if background:
            Thread(target=worker, daemon=True).start()
        else:
            self._apply_refresh(fetch_fresh())

    def _apply_refresh(self, new_data: list) -> bool:
        self.data = new_data
        if self.active_pid is None or not any(e.get("provider") == self.active_pid for e in new_data):
            self.active_pid = default_provider(new_data)
        self.render()
        return False

    def render(self):
        self._clear(self.tabbar)
        self._clear(self.body)
        if self.view == "settings":
            self._render_settings_header()
            self._render_settings_body()
            return
        self._render_usage_header()
        self._render_usage_body()

    def _render_usage_header(self):
        if not self.data:
            loading = Gtk.Label(label="Loading…")
            loading.add_css_class("codexbar-subtitle")
            self.tabbar.append(loading)
            return
        self.tab_buttons.clear()
        for entry in self._tab_entries():
            pid = entry.get("provider", "")
            tab = self._make_provider_tab(entry)
            self.tabbar.append(tab)
            self.tab_buttons[pid] = tab

    def _render_usage_body(self):
        if not self.data:
            return
        active = next((e for e in self.data if e.get("provider") == self.active_pid), None)
        if active is None:
            return
        self._render_provider(active)

    def _render_settings_header(self):
        back = self._make_pill("← Back", ["codexbar-tab"], self._on_settings_back)
        self.tabbar.append(back)
        title = Gtk.Label(label="Settings", xalign=0.0, hexpand=True)
        title.add_css_class("codexbar-settings-title")
        self.tabbar.append(title)
        save = self._make_pill("Save", ["codexbar-tab", "active"], self._on_settings_save)
        self.tabbar.append(save)

    def _render_settings_body(self):
        self.settings_switches.clear()
        cfg = load_full_config()
        existing = {p.get("id"): bool(p.get("enabled")) for p in cfg.get("providers", [])}

        # --- Section: which provider shows in the bar ---
        bar_title = Gtk.Label(label="Show in bar", xalign=0.0)
        bar_title.add_css_class("codexbar-section-title")
        self.body.append(bar_title)
        bar_hint = Gtk.Label(
            label="Pick a provider to pin to the bar (session • weekly), or leave on Highest.",
            xalign=0.0, wrap=True, max_width_chars=44)
        bar_hint.add_css_class("codexbar-subtitle")
        self.body.append(bar_hint)
        self.body.append(self._build_bar_provider_picker(existing))

        # Divider between sections.
        self.body.append(self._divider())

        # --- Section: reset time format ---
        reset_title = Gtk.Label(label="Reset times", xalign=0.0)
        reset_title.add_css_class("codexbar-section-title")
        self.body.append(reset_title)
        reset_hint = Gtk.Label(
            label="How to render the “Resets …” label. Provider keeps the raw "
                  "string each backend emits; Local/UTC reformat the reset "
                  "timestamp with an explicit timezone.",
            xalign=0.0, wrap=True, max_width_chars=44)
        reset_hint.add_css_class("codexbar-subtitle")
        self.body.append(reset_hint)
        self.body.append(self._build_reset_format_picker())

        # Divider between sections.
        self.body.append(self._divider())

        # --- Section: enabled providers ---
        section_title = Gtk.Label(label="Providers", xalign=0.0)
        section_title.add_css_class("codexbar-section-title")
        self.body.append(section_title)
        section_hint = Gtk.Label(
            label="Toggle which providers feed the bar and the popup.",
            xalign=0.0, wrap=True)
        section_hint.add_css_class("codexbar-subtitle")
        self.body.append(section_hint)

        # Scrollable list.
        scroller = Gtk.ScrolledWindow()
        scroller.set_min_content_height(sx(280))
        scroller.set_propagate_natural_width(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        list_box.add_css_class("codexbar-settings-list")
        scroller.set_child(list_box)
        self.body.append(scroller)

        # Linux-supported first, alphabetised; then unsupported with hint.
        provider_ids = [p.get("id") for p in cfg.get("providers", [])]
        supported = sorted(p for p in provider_ids if p in LINUX_SUPPORTED)
        unsupported = sorted(p for p in provider_ids if p not in LINUX_SUPPORTED)

        for pid in supported:
            list_box.append(self._settings_row(pid, existing.get(pid, False), enabled_ui=True))

        if unsupported:
            divider_label = Gtk.Label(label="macOS-only providers", xalign=0.0)
            divider_label.add_css_class("codexbar-settings-group")
            list_box.append(divider_label)
            for pid in unsupported:
                list_box.append(self._settings_row(pid, existing.get(pid, False), enabled_ui=False))

        # Footer note.
        note = Gtk.Label(
            label=f"Config: {CONFIG_PATH}",
            xalign=0.0, wrap=True)
        note.add_css_class("codexbar-subtitle")
        self.body.append(note)

    def _build_bar_provider_picker(self, existing: dict[str, bool]) -> Gtk.Widget:
        wrap = Gtk.FlowBox()
        wrap.add_css_class("codexbar-bar-picker")
        wrap.set_selection_mode(Gtk.SelectionMode.NONE)
        wrap.set_homogeneous(False)
        wrap.set_max_children_per_line(8)
        current = load_state().get("barProvider")

        def make_chip(pid: str | None, label: str):
            classes = ["codexbar-tab"]
            if pid == current or (pid is None and not current):
                classes.append("active")
            chip = self._make_pill(
                label, classes,
                lambda p=pid: self._on_bar_provider_change(p),
                icon_pid=pid)
            return chip

        wrap.append(make_chip(None, "Highest"))
        enabled_pids = [pid for pid, on in existing.items() if on and pid in LINUX_SUPPORTED]
        for pid in enabled_pids:
            wrap.append(make_chip(pid, PROVIDER_NAMES.get(pid, pid.title())))
        return wrap

    def _on_bar_provider_change(self, pid: str | None):
        state = load_state()
        if pid is None:
            state.pop("barProvider", None)
        else:
            state["barProvider"] = pid
        save_state(state)
        # Re-render so the active chip highlight tracks the click.
        self.render()
        # Nudge waybar so the bar text updates immediately.
        subprocess.Popen(["pkill", "-RTMIN+8", "waybar"])

    def _build_reset_format_picker(self) -> Gtk.Widget:
        wrap = Gtk.FlowBox()
        wrap.add_css_class("codexbar-bar-picker")
        wrap.set_selection_mode(Gtk.SelectionMode.NONE)
        wrap.set_homogeneous(False)
        wrap.set_max_children_per_line(8)
        current = current_reset_format()
        labels = (("provider", "Provider"), ("local", "Local"), ("utc", "UTC"))
        for value, label in labels:
            classes = ["codexbar-tab"]
            if value == current:
                classes.append("active")
            wrap.append(self._make_pill(
                label, classes,
                lambda v=value: self._on_reset_format_change(v)))
        return wrap

    def _on_reset_format_change(self, value: str):
        state = load_state()
        if value == "provider":
            state.pop("resetTimeFormat", None)
        else:
            state["resetTimeFormat"] = value
        save_state(state)
        # Re-render the Settings view so the chip highlight tracks the click,
        # and signal waybar so the tooltip picks up the new format on its
        # next refresh.
        self.render()
        subprocess.Popen(["pkill", "-RTMIN+8", "waybar"])

    def _settings_row(self, pid: str, enabled: bool, *, enabled_ui: bool) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("codexbar-settings-row")
        if not enabled_ui:
            row.add_css_class("disabled")

        icon = make_icon(pid, size=sx(18))
        if icon is not None:
            row.append(icon)

        name = Gtk.Label(label=PROVIDER_NAMES.get(pid, pid.title()), xalign=0.0, hexpand=True)
        name.add_css_class("codexbar-settings-name")
        row.append(name)

        if not enabled_ui:
            hint = Gtk.Label(label="macOS only", xalign=1.0)
            hint.add_css_class("codexbar-settings-hint")
            row.append(hint)

        switch = Gtk.Switch()
        switch.set_active(enabled)
        switch.set_sensitive(enabled_ui)
        switch.set_valign(Gtk.Align.CENTER)
        row.append(switch)
        self.settings_switches[pid] = switch
        return row

    def _select(self, pid: str):
        if pid == self.active_pid:
            return
        self.active_pid = pid
        self.render()

    def _provider_plan_label(self, pid: str, usage: dict, identity: dict) -> str:
        for source in (usage, identity):
            for key in ("planName", "plan", "subscription", "tier", "accountType"):
                value = source.get(key)
                if value:
                    return str(value).title()
        if pid == "claude":
            return "Max"
        login_method = identity.get("loginMethod") or usage.get("loginMethod")
        if login_method and str(login_method).lower() not in {"oauth", "cli", "api_key"}:
            return str(login_method).title()
        return ""

    def _window_title(self, pid: str, key: str, window: dict) -> str:
        for field in ("title", "name", "label", "model"):
            value = window.get(field)
            if value:
                return str(value).title()
        if pid == "claude" and key == "tertiary":
            return "Sonnet"
        return WINDOW_LABELS.get(key, key.title())

    def _usage_windows(self, pid: str, usage: dict) -> list[tuple[str, dict]]:
        keys = ["primary", "secondary"]
        if usage.get("tertiary") or pid == "claude":
            keys.append("tertiary")
        return [(key, usage.get(key) or {}) for key in keys]

    def _find_number(self, source: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = source.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                cleaned = value.replace("$", "").replace(",", "").strip()
                try:
                    return float(cleaned)
                except ValueError:
                    continue
        return None

    def _format_money(self, value: float | None) -> str:
        return f"$ {float(value or 0):.2f}"

    def _format_tokens(self, value) -> str:
        if isinstance(value, str) and value.strip():
            text = value.strip()
            return text if "token" in text.lower() else f"{text} tokens"
        if not isinstance(value, (int, float)):
            return "0 tokens"
        amount = float(value)
        if amount >= 1_000_000_000:
            text = f"{amount / 1_000_000_000:.1f}".rstrip("0").rstrip(".") + "B"
        elif amount >= 1_000_000:
            text = f"{amount / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
        elif amount >= 1_000:
            text = f"{amount / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
        else:
            text = str(int(amount))
        return f"{text} tokens"

    def _extra_usage(self, entry: dict) -> tuple[float, float, float]:
        usage = entry.get("usage") or {}
        sources = [
            entry.get("extraUsage") or {},
            usage.get("extraUsage") or {},
            usage.get("extra") or {},
            entry.get("credits") or {},
        ]
        used = limit = None
        for source in sources:
            if not isinstance(source, dict):
                continue
            used = self._find_number(source, ("used", "usedUsd", "spent", "current", "usage"))
            limit = self._find_number(source, ("limit", "limitUsd", "budget", "maximum", "total"))
            remaining = self._find_number(source, ("remaining", "remainingUsd", "balance"))
            if used is None and remaining is not None and limit is not None:
                used = max(0.0, limit - remaining)
            if used is not None or limit is not None:
                break
        used = float(used or 0)
        limit = float(limit or 2000)
        pct = 0 if limit <= 0 else max(0, min(100, used / limit * 100))
        return used, limit, pct

    def _cost_usage(self, entry: dict) -> tuple[float, object, float, object]:
        usage = entry.get("usage") or {}
        cost = entry.get("cost") or usage.get("cost") or usage.get("costs") or {}
        if not isinstance(cost, dict):
            cost = {}

        today = cost.get("today") if isinstance(cost.get("today"), dict) else {}
        last30 = (
            cost.get("last30Days")
            or cost.get("last30")
            or cost.get("lastThirtyDays")
        )
        last30 = last30 if isinstance(last30, dict) else {}

        today_cost = self._find_number(today, ("cost", "usd", "amount"))
        today_cost = today_cost if today_cost is not None else self._find_number(
            cost, ("todayCost", "todayUsd", "costToday"))
        today_tokens = (
            today.get("tokens")
            or today.get("tokenCount")
            or cost.get("todayTokens")
            or cost.get("tokensToday")
        )

        last30_cost = self._find_number(last30, ("cost", "usd", "amount"))
        last30_cost = last30_cost if last30_cost is not None else self._find_number(
            cost, ("last30DaysCost", "last30Cost", "lastThirtyDaysCost"))
        last30_tokens = (
            last30.get("tokens")
            or last30.get("tokenCount")
            or cost.get("last30DaysTokens")
            or cost.get("last30Tokens")
            or cost.get("lastThirtyDaysTokens")
        )
        return float(today_cost or 0), today_tokens, float(last30_cost or 0), last30_tokens

    def _open_url(self, url: str) -> None:
        subprocess.Popen(["xdg-open", url])

    def _on_add_account(self):
        self._on_settings_call()

    def _on_usage_dashboard(self):
        self._open_url("https://codexbar.app")

    def _on_status_page(self):
        pid = self.active_pid or ""
        self._open_url(PROVIDER_STATUS_URLS.get(pid, "https://codexbar.app"))

    def _render_provider(self, entry: dict):
        pid = entry.get("provider", "?")
        usage = entry.get("usage") or {}
        identity = usage.get("identity") or {}

        # Header row.
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label=PROVIDER_NAMES.get(pid, pid.title()), xalign=0.0, hexpand=True)
        title.add_css_class("codexbar-provider-title")
        header.append(title)
        plan_text = self._provider_plan_label(pid, usage, identity)
        if plan_text:
            plan = Gtk.Label(label=plan_text, xalign=1.0)
            plan.add_css_class("codexbar-plan")
            header.append(plan)
        self.body.append(header)

        # Subtitle line (status / updated / stale).
        sub_text = "Updated just now"
        if entry.get("stale"):
            sub_text = "Cached — last refresh failed"
        elif entry.get("error"):
            sub_text = "Refresh failed"
        sub = Gtk.Label(label=sub_text, xalign=0.0)
        sub.add_css_class("codexbar-subtitle")
        self.body.append(sub)
        self.body.append(self._divider("codexbar-header-divider"))

        if entry.get("error"):
            err = Gtk.Label(
                label=entry["error"].get("message", "Unknown error"),
                xalign=0.0,
                wrap=True,
                max_width_chars=44)
            err.add_css_class("codexbar-error")
            self.body.append(err)
            return

        # Usage windows.
        for key, window in self._usage_windows(pid, usage):
            if not window and key != "tertiary":
                continue
            self.body.append(self._section(self._window_title(pid, key, window), window, key=key))

        self.body.append(self._divider())
        self._render_extra_usage(entry)

        self.body.append(self._divider())
        self._render_cost(entry)

        self.body.append(self._divider("codexbar-after-cost-divider"))
        self._render_actions()

    def _divider(self, *classes: str) -> Gtk.Widget:
        d = Gtk.Box()
        d.add_css_class("codexbar-divider")
        for class_name in classes:
            d.add_css_class(class_name)
        return d

    def _section(self, title: str, window: dict, *, key: str = "") -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("codexbar-usage-section")
        t = Gtk.Label(label=title, xalign=0.0)
        t.add_css_class("codexbar-section-title")
        box.append(t)

        pct = window.get("usedPercent")
        bar = self._meter(pct, ["codex-usage"])
        if isinstance(pct, (int, float)):
            if pct >= 90:
                bar.add_css_class("critical")
            elif pct >= 70:
                bar.add_css_class("warning")
        box.append(bar)

        details = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left_text = (
            f"{int(pct)}% used"
            if isinstance(pct, (int, float))
            else "—"
        )
        left = Gtk.Label(label=left_text, xalign=0.0, hexpand=True)
        left.add_css_class("codexbar-section-detail-left")
        details.append(left)

        reset_text = format_reset_label(window, current_reset_format())
        if reset_text:
            r = Gtk.Label(label=reset_text, xalign=1.0)
            r.add_css_class("codexbar-section-detail-right")
            details.append(r)
        box.append(details)

        pace = self._pace_text(window)
        if pace:
            p = Gtk.Label(label=pace, xalign=0.0)
            p.add_css_class("codexbar-pace")
            box.append(p)
        return box

    def _pace_text(self, window: dict) -> str:
        for key in ("paceDescription", "paceText", "paceLabel"):
            value = window.get(key)
            if value:
                return str(value)
        pace = window.get("pace")
        if isinstance(pace, dict):
            label = pace.get("label") or pace.get("status")
            pct = pace.get("percent") or pace.get("deltaPercent")
            tail = pace.get("outcome") or pace.get("description")
            parts = []
            if label:
                body = str(label)
                if isinstance(pct, (int, float)):
                    body += f" ({pct:+.0f}%)"
                parts.append(body)
            if tail:
                parts.append(str(tail))
            if parts:
                return "Pace: " + " · ".join(parts)
        return ""

    def _render_extra_usage(self, entry: dict) -> None:
        used, limit, pct = self._extra_usage(entry)
        title = Gtk.Label(label="Extra usage", xalign=0.0)
        title.add_css_class("codexbar-section-title")
        title.add_css_class("codexbar-extra-title")
        title.set_margin_bottom(sx(5))
        self.body.append(title)
        self.body.append(self._meter(pct, ["codex-usage"]))

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("codexbar-extra-row")
        row.set_margin_bottom(sx(26))
        left = Gtk.Label(
            label=f"This month: {self._format_money(used)} / {self._format_money(limit)}",
            xalign=0.0,
            hexpand=True)
        left.add_css_class("codexbar-section-detail-left")
        row.append(left)
        right = Gtk.Label(label=f"{int(round(pct))}% used", xalign=1.0)
        right.add_css_class("codexbar-section-detail-right")
        row.append(right)
        self.body.append(row)

    def _render_cost(self, entry: dict) -> None:
        today_cost, today_tokens, last30_cost, last30_tokens = self._cost_usage(entry)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Cost", xalign=0.0, hexpand=True)
        title.add_css_class("codexbar-section-title")
        heading.append(title)
        arrow = Gtk.Label(label="›", xalign=1.0)
        arrow.add_css_class("codexbar-chevron")
        heading.append(arrow)
        self.body.append(heading)

        today = Gtk.Label(
            label=f"Today: {self._format_money(today_cost)} · {self._format_tokens(today_tokens)}",
            xalign=0.0)
        today.add_css_class("codexbar-section-detail-left")
        today.add_css_class("codexbar-cost-row")
        self.body.append(today)

        last = Gtk.Label(
            label=f"Last 30 days: {self._format_money(last30_cost)} · {self._format_tokens(last30_tokens)}",
            xalign=0.0)
        last.add_css_class("codexbar-section-detail-left")
        last.add_css_class("codexbar-cost-last-row")
        self.body.append(last)

    def _render_actions(self) -> None:
        self.body.append(self._menu_row(
            "Add Account...",
            self._on_add_account,
            glyph=MENU_GLYPHS["add-account"]))
        self.body.append(self._menu_row(
            "Usage Dashboard",
            self._on_usage_dashboard,
            glyph=MENU_GLYPHS["dashboard"]))
        self.body.append(self._menu_row(
            "Status Page",
            self._on_status_page,
            glyph=MENU_GLYPHS["status"]))
        self.body.append(self._divider("codexbar-before-footer-divider"))
        self.body.append(self._menu_row("Settings...", self._on_settings_call))
        self.body.append(self._menu_row("About CodexBar", self._on_about_call))
        self.body.append(self._menu_row("Quit", self.quit))

    def _clear(self, container: Gtk.Box):
        child = container.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            container.remove(child)
            child = nxt


def main():
    pidfile = CACHE / "popup.pid"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            pidfile.unlink(missing_ok=True)
            return 0
        except (ValueError, ProcessLookupError, PermissionError):
            pidfile.unlink(missing_ok=True)

    CACHE.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(str(os.getpid()))
    try:
        app = CodexBarPopup()
        return app.run([])
    finally:
        pidfile.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
