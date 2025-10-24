# Polybar + Pywal Usage Guide

## How It Works Now ✅

Your theme selector now **automatically applies pywal colors** when switching themes!

### The Flow:
1. You set a wallpaper with pywal: `wal -i /path/to/wallpaper.jpg`
2. Switch themes with: `~/.config/polybar/theme-selector.sh`
3. **Automatically**: The script runs that theme's `pywal.sh` with your current wallpaper
4. **Result**: Theme switches AND gets your wallpaper colors applied

## Quick Start

### First Time Setup

1. **Set your wallpaper with pywal:**
   ```bash
   wal -i ~/Pictures/Wallpapers/your-wallpaper.jpg
   ```

   This generates colors and sets them in `~/.cache/wal/`

2. **Switch themes:**
   ```bash
   ~/.config/polybar/theme-selector.sh
   ```

   Select any theme - it will automatically use your wallpaper colors!

### Daily Usage

**Change wallpaper:**
```bash
wal -i ~/Pictures/new-wallpaper.jpg
```

**Switch theme style (keeps wallpaper colors):**
```bash
~/.config/polybar/theme-selector.sh
# Select: Material, Shades, Hack, etc.
```

**Both at once:**
```bash
wal -i ~/Pictures/wallpaper.jpg
~/.config/polybar/theme-selector.sh
```

## Available Themes

All themes will use your wallpaper colors:

- 📱 **Material** - Material Design aesthetic
- 🌈 **Shades** - Gradient color schemes
- 💻 **Hack** - Hacker/terminal aesthetic
- 🎪 **Docky** - macOS-like dock style
- ✂️ **Cuts** - Angular cut design
- 🔶 **Shapes** - Geometric shapes
- ▫️ **Grayblocks** - Grayscale blocks
- ▪️ **Blocks** - Colorful blocks
- 🌈 **Colorblocks** - Vibrant color blocks
- 🌲 **Forest** - Nature-inspired

## Add Keybinding (Optional)

Add to `~/.config/i3/config`:

```bash
# Theme selector with pywal colors
bindsym $mod+Shift+t exec --no-startup-id ~/.config/polybar/theme-selector.sh
```

Reload i3: `$mod+Shift+r`

## Troubleshooting

### "No wallpaper set with pywal" error

You need to set a wallpaper first:
```bash
wal -i /path/to/wallpaper.jpg
```

### Colors don't match wallpaper

1. **Check pywal generated colors:**
   ```bash
   cat ~/.cache/wal/colors.sh | head -20
   ```

2. **Manually run pywal script for current theme:**
   ```bash
   # Example for material theme
   bash ~/.config/polybar/material/scripts/pywal.sh "$(cat ~/.cache/wal/wal)"
   ~/.config/polybar/launch.sh --material
   ```

### Theme doesn't change

1. **Check if theme exists:**
   ```bash
   ls ~/.config/polybar/material/
   ```

2. **Manually launch theme:**
   ```bash
   ~/.config/polybar/launch.sh --material
   ```

## How Theme Switching Works

When you select a theme, the script:

1. ✅ Gets your current wallpaper path from `~/.cache/wal/wal`
2. ✅ Runs that theme's `pywal.sh` script: `bash ~/.config/polybar/THEME/scripts/pywal.sh WALLPAPER`
3. ✅ The pywal.sh script:
   - Reads colors from `~/.cache/wal/colors.sh`
   - Updates the theme's `colors.ini` file with those colors
4. ✅ Launches the theme with `~/.config/polybar/launch.sh --THEME`

## Manual Color Updates (Advanced)

If you want to manually update a theme's colors:

```bash
# Update material theme with specific wallpaper
bash ~/.config/polybar/material/scripts/pywal.sh /path/to/wallpaper.jpg

# Update shades theme with current wallpaper
bash ~/.config/polybar/shades/scripts/pywal.sh "$(cat ~/.cache/wal/wal)"
```

## Auto-Start on Login

Add to `~/.config/i3/config` or your WM startup file:

```bash
# Restore last wallpaper and colors
exec_always --no-startup-id wal -R

# Launch polybar with your default theme
exec_always --no-startup-id ~/.config/polybar/launch.sh --material
```

## What Changed

**Before:**
- Switching themes → hardcoded default colors
- Wallpaper colors ignored ❌

**Now:**
- Switching themes → automatically applies current wallpaper colors
- Seamless integration with pywal ✅

## Tips

1. **Organize wallpapers** in `~/Pictures/Wallpapers/` for easy access
2. **Try different themes** - they all adapt to your wallpaper now
3. **Use rofi launcher** - type "Polybar Theme Selector" in rofi
4. **Experiment** - switch between themes to see which style you prefer

Enjoy your color-matched polybar themes! 🎨
