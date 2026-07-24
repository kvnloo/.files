# Site wallpaper: Forgotten Ruins

Public pages use a **static poster** of Wallpaper Engine Scene `2133182232` (Forgotten Ruins) under liquid-glass UI.

Video/WebM playback is **off** for now. A native Wallpaper Engine ↔ website bridge is being researched separately; until that lands, keep the clean still image.

## Desktop vs web

| Context | How it renders |
|--------|----------------|
| Linux desktop | `linux-wallpaperengine` OpenGL Scene runtime parses `scene.pkg` |
| This website | Static poster (`public/media/forgotten-ruins-poster.jpg|.webp`) |

## Refresh poster

```sh
./scripts/export-website-wallpaper.sh --poster-only
```

Requires Hyprland + grim + ImageMagick. Uses an empty workspace so windows are not recorded.

A full WebM bake still exists in the export script for archival, but the site does not play it.

Do **not** commit Steam workshop trees or `scene.pkg`.
