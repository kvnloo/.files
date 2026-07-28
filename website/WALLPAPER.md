# Site wallpaper: Forgotten Ruins

Public pages use an **adaptive** Forgotten Ruins backdrop (Wallpaper Engine Scene
`2133182232`):

| Tier | When | What |
|------|------|------|
| **A – Reactive** | WebGL OK, motion allowed | Thin WebGL1 player (base + water passes + light particles) |
| **B – Video** | Opt-in / lab only (`allowVideoFallback`) | `forgotten-ruins.webm` loop |
| **C – Static** | reduced-motion, Save-Data, weak device, no WebGL | Poster WebP/JPG (LCP) |

Poster always paints first. WebGL mounts after idle and crossfades in.

Architecture: [`docs/WALLPAPER_ARCHITECTURE.md`](docs/WALLPAPER_ARCHITECTURE.md).
Debug: `/lab/wallpaper`.

## Local reactive textures

Workshop-derived WebPs are **gitignored**. For a local spike:

```sh
python3 website/scripts/unpack-wallpaper.py \
  --src /path/to/unpacked/forgotten-ruins \
  --out website/public/media/ruins
```

Without those files the player still runs using the shipped poster as the base plate
and white/procedural masks (motion demo only).

**Do not commit** `scene.pkg`, `.tex`, or extracted workshop art. Public shipping needs
owned / re-authored / licensed base art.

## Refresh poster

```sh
./scripts/export-website-wallpaper.sh --poster-only
```

Requires Hyprland + grim + ImageMagick.
