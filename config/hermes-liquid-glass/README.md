# hermes-liquid-glass

**Linux-native liquid glass theme bridge** for [Hermes Desktop](https://github.com/NousResearch/hermes-agent):

`Wallpaper Engine / swww` → **pywal** → **Hyprland frost** → **Hermes Desktop plugin**

When your wallpaper changes, the Desktop accent/chrome follow automatically.

> Privacy: the included trailer uses a **synthetic preview chat only** — no real sessions, paths, or personal content.

## What you get

| Piece | Path |
|-------|------|
| Theme builder | `scripts/build_theme.py` |
| Apply hook | `scripts/apply.sh` |
| Desktop runtime plugin | `plugin/plugin.js` |
| Hyprland opacity fragment | `hypr/liquid-glass.conf` |
| Trailer (Remotion) | `trailer/` |

## Requirements

- Linux + [Hyprland](https://hyprland.org/)
- [pywal](https://github.com/dylanaraps/pywal) (`wal`)
- [Hermes Desktop](https://github.com/NousResearch/hermes-agent) (packaged or dev)
- Optional: Wallpaper Engine (`linux-wallpaperengine`) or any wallpaper tool that feeds pywal

## Install

```bash
git clone https://github.com/kvnloo/hermes-liquid-glass.git
cd hermes-liquid-glass

# Desktop plugin
mkdir -p ~/.hermes/desktop-plugins
ln -sfn "$PWD/plugin" ~/.hermes/desktop-plugins/liquid-glass-wal

# Hyprland — source the fragment (and enable blur ignore_opacity)
# in ~/.config/hypr/hyprland.conf:
#   source = /absolute/path/to/hermes-liquid-glass/hypr/liquid-glass.conf
#
# decoration {
#   blur {
#     enabled = true
#     ignore_opacity = true
#     ...
#   }
# }

# Build theme from current wal colors
./scripts/apply.sh
```

In Hermes Desktop: **Cmd/Ctrl-K → Reload desktop plugins**, then  
**Liquid Glass: sync from pywal now**.

### Wire into pywal (recommended)

After `wal` + your terminal sync, call:

```bash
/path/to/hermes-liquid-glass/scripts/apply.sh
```

If you use the [kvnloo/.files](https://github.com/kvnloo/.files) desktop stack, this is already hooked from `scripts/apply-pywal-theme.sh`.

## How it works

1. `build_theme.py` reads `~/.cache/wal/colors.json`
2. Emits a Hermes `DesktopTheme` (+ glass mix knobs) to:
   - `~/.cache/wal/hermes-liquid-glass-theme.json`
   - `~/.hermes/liquid-glass-wal/theme.json`
3. Runtime plugin polls the file, installs skin `liquid-glass-wal`, paints CSS seeds **without** full window reload
4. Hyprland `opacity` + `blur:ignore_opacity` provide the frost see-through

## Palette commands

| Command | Action |
|---------|--------|
| Liquid Glass: sync from pywal now | Force rebuild apply + one reload |
| Liquid Glass: toggle auto-apply… | Enable/disable wallpaper auto-theme |

## Trailer

Privacy-safe Remotion trailer (demo UI only):

```bash
cd trailer
npm install
npx remotion render src/index.tsx LiquidGlassTrailer out/liquid-glass-trailer.mp4 \
  --browser-executable="$(command -v chromium || command -v google-chrome-stable)"
```

Output: `trailer/out/liquid-glass-trailer.mp4`

## License

MIT — see [LICENSE](./LICENSE)
