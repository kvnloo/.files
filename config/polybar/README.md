# Polybar Configuration

Modern polybar setup with Material Design theme and multiple theme options.

## Features

- 🎨 **12 Professional Themes** - Access to adi1090x's polybar-themes collection
- 🔄 **Theme Selector** - Switch themes with rofi menu
- 🌐 **Network Status** - Ethernet and WiFi with auto-hide when offline
- 🎵 **System Monitoring** - CPU, memory, temperature, volume
- ⌨️ **i3 Integration** - Workspace indicators and controls

## Installation

### 1. Install polybar-themes collection

The themes are available as a submodule in `../polybar-themes/`:

```bash
cd config/polybar-themes
./setup.sh
# Select option 1 for Simple themes
```

This will:
- Install all themes to `~/.config/polybar/`
- Install required fonts to `~/.local/share/fonts/`
- Backup existing config to `~/.config/polybar.old`

### 2. Setup theme selector

Copy the theme selector script:

```bash
cp config/polybar/scripts/theme-selector.sh ~/.config/polybar/
chmod +x ~/.config/polybar/theme-selector.sh
```

Copy the desktop entry (optional, for rofi app launcher):

```bash
mkdir -p ~/.local/share/applications
cp config/polybar/polybar-theme-selector.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

### 3. Add i3 keybinding (optional)

Add to your `~/.config/i3/config`:

```
bindsym $mod+Shift+t exec --no-startup-id ~/.config/polybar/theme-selector.sh
```

## Usage

### Switch Themes

**Via Rofi:**
- Open rofi app launcher (`$mod+d`)
- Search for "Polybar Theme Selector"

**Via Command:**
```bash
~/.config/polybar/theme-selector.sh
```

**Via Keybinding:**
- Press `$mod+Shift+t` (if configured)

### Available Themes

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
- 📋 **Panels** - Panel-based layout
- 🎛️ **Pwidgets** - Widget style

### Manual Theme Launch

```bash
~/.config/polybar/launch.sh --material
~/.config/polybar/launch.sh --shapes
~/.config/polybar/launch.sh --hack
# ... etc
```

## Customization

### Network Interfaces

Edit the network module in your chosen theme's `modules.ini`:

```ini
[module/network]
interface = wlp5s0  # Change to your WiFi interface

[module/ethernet]
interface = enp4s0  # Change to your Ethernet interface
```

Find your interfaces with:
```bash
ip -br link show
```

### Colors

Each theme has a color switcher script:

```bash
~/.config/polybar/material/scripts/color-switch.sh
```

This cycles through different color schemes for the theme.

## Credits

- Base themes: [adi1090x/polybar-themes](https://github.com/adi1090x/polybar-themes)
- Theme selector and customizations: Custom additions
