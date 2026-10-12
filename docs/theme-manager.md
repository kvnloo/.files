# Unified theme manager

One command, `theme`, gives every themable part of the desktop the same
palette. It is built but **not active**: nothing on the live machine changes
until the activation steps at the end of this page are run.

```
config/themes/<slug>/palette.toml      one normalised palette per theme (source of truth)
config/themes/themes.lock.json         where each imported theme came from (URL, commit)
        |
        |  theme apply <slug>          per-component renderers
        v
~/.local/state/theme/generated/        the only place a theme switch writes
        ^
        |  one include line each ("wire")
hand-written configs (kitty.conf, hyprland.conf, .tmux.conf, ...)
```

Switching a theme rewrites the generated directory and then asks each wired
component to reload. The hand-written configs in this repo are edited once, by
the wire step, and never again.

## Commands

| Command | What it does |
|---|---|
| `theme list` | Themes, with mode, background, accent and wallpaper count. `*` marks the active one. |
| `theme current` | Active theme and its source (`theme` or `wallpaper`). |
| `theme apply <slug>` | Render the theme, reload wired components, set its wallpaper. `--no-reload` writes files only; `--keep-wallpaper` leaves the wallpaper. |
| `theme next` / `theme prev` | Apply the next or previous theme in `theme list` order. |
| `theme pick` | Choose a theme in rofi, with each theme's `preview.png` as its icon. |
| `theme wallpaper next\|prev` | Step through the active theme's wallpapers. |
| `theme wallpaper-mode` | Hand the palette back to the wallpaper: pywal's `~/.cache/wal/colors.json` becomes the source and is rendered through the same renderers. |
| `theme import <path-or-slug>` | Normalise one Omarchy theme directory into `config/themes/`. A bare slug is looked up in `/mnt/zer0models/themes/omarchy` (override with `THEME_IMPORT_CACHE`). A pywal `colors.json` path is also accepted, with `--slug`. |
| `theme import --all` | Import every directory in the cache. |
| `theme doctor` | Per component: tool installed, file generated, wired, how it reloads. Also what a palette cannot provide. Read-only. |
| `theme wire <component...>\|--all` | Add the include line(s) for a component. Refuses until a theme has been applied. |
| `theme unwire <component...>\|--all` | Undo exactly what `wire` did (recorded in `~/.local/state/theme/wired.json`). |

Flags accepted anywhere: `--dry-run` (print, write nothing, run nothing) and
`--home <dir>` (act on a scratch home; never runs a reload or wallpaper
command). `THEME_NO_LIVE=1` has the same no-reload effect without changing the home.

## The palette

`palette.toml` holds `name`, `slug`, `mode` (`dark`/`light`), 21 semantic
colours under `[colors]`, sixteen terminal colours under `[ansi]`, and optional
`[extras]` (`icon_theme`, `nvim_colorscheme`, `wallpapers`, `preview`) and
`[overrides.noctalia]` (exact Noctalia roles, used by `groot-baseline`).
All colours are lowercase `#rrggbb`.

The normaliser needs only a background and a foreground and derives the rest.
Muted text is nudged until it has 5:1 contrast on the background (the same
routine `sync-pywal-theme.py` uses), and text on the accent is chosen for 4.5:1.

Import formats:

- **Omarchy 4.x** `colors.toml`, in both shapes found in the cache: named
  colours (`accent`, `red`, `bright_red`, `lighter_background`, ...) and indexed
  colours (`color0`..`color15`, `selection_background`, ...).
- **Omarchy legacy**: `alacritty.toml`, then `kitty.conf` for anything missing,
  with the accent read from the active-border line of `hyprland.conf`.
- **pywal** `colors.json`. Terminal slots stay the wallpaper's; red, green and
  yellow as *alert* colours are fixed so errors stay red on any wallpaper.

Third-party theme directories are read as data only. Nothing in them is
executed, sourced or installed; git is never run inside them (URL and commit
are read from `.git/config`, `.git/HEAD` and ref files as text); from
`neovim.lua` only the colourscheme *name* is taken with a regular expression.

Wallpapers and previews are **referenced**, not copied: `extras.wallpapers`
points at the cache's `backgrounds/` directory. A `config/themes/<slug>/wallpapers/`
directory, if you create one, takes precedence. If the cache moves, re-import.

## Components

"Today" is the state found on groot on 2026-10-11. No component is wired yet.

| Component | Colours today | Generated file | Wire (one line unless noted) | Reload | Reload safe? |
|---|---|---|---|---|---|
| Noctalia shell | Predefined scheme "Tokyo Night" (uncommitted); committed scheme is LiquidGlass-Forgotten | `noctalia/Unified/Unified.json` | symlink `~/.config/noctalia/colorschemes/Unified` | `qs -c noctalia-shell ipc call colorScheme set Unified` | Yes, in place. First use needs one Noctalia restart so the scheme is listed. |
| Hyprland borders, group bars, shadow, glass tint | `~/.cache/wal/colors-hyprland.conf` from 12 Sep, overridden live by Noctalia's template hook | `hyprland.conf` | `source =` line in `hyprland.legacy.conf` | `hyprctl --batch keyword ...` | Yes, no compositor reload. |
| kitty | `~/.cache/wal/colors-kitty.conf` (pywal) | `kitty.conf` | `include` line | `SIGUSR1` | Yes. |
| alacritty | `~/.cache/wal/colors-alacritty.toml` (pywal) | `alacritty.toml` | `import` entry | automatic | Yes. |
| rofi | `~/.cache/wal/colors-rofi-dark.rasi` via `colors.rasi` | `rofi.rasi` | `@import` in `colors.rasi` | next launch | n/a |
| dunst | Static `dunstrc`; pywal copy loaded by `dunstctl reload ~/.cache/wal/dunstrc` | `dunst.conf` | symlink `dunstrc.d/50-theme.conf` | `dunstctl reload` | Yes; notifications on screen are dismissed. |
| hyprlock | Literals in `hyprlock.conf` | `hyprlock.conf` (`$lock_*` variables) | `source =` line under the `# theme:source` marker | next lock | n/a |
| waybar (not running; Noctalia is the bar) | `~/.cache/wal/colors-waybar-semantic.css` | `waybar.css` | `@import` in three stylesheets | `SIGUSR2` | Yes. |
| tmux | Tokyo Night literals, then `~/.cache/wal/colors-tmux.conf` | `tmux.conf` | `source-file -q` line | `tmux source-file` | Yes. |
| btop | `Default` | `btop.theme` | symlink + `color_theme` in `btop.conf` | restart btop | n/a |
| fzf, bat | Defaults | `shell.sh` | `source` line at the end of `.zshrc` | new shells | n/a |
| delta | Defaults | `delta.gitconfig` | `[include]` in `.gitconfig` (two lines) | next git command | n/a |
| GTK 3 | Theme `cachyos-nord` (settings.ini); gsettings says `Adwaita` | `gtk3.css` | creates `~/.config/gtk-3.0/gtk.css` with one `@import` | newly started apps | n/a |
| GTK 4 / libadwaita | Hand-written glass colours in `config/gtk-4.0/gtk.css` | `gtk4.css` (same alphas) | `@import` appended to `gtk.css` | newly started apps | n/a |
| Qt | qt6ct palette `GlassDark`, style Kvantum `GlassDark`; qt5ct configured but not installed | `qt6ct.conf`, `kvantum/Unified/` | `color_scheme_path` in qt6ct/qt5ct, symlink + `theme=` for Kvantum | qt6ct watches its file; Kvantum on app restart | Yes. |
| Neovim | `tokyonight-moon` (LazyVim) | `nvim.lua` | creates `lua/plugins/theme.lua` (one `require`) | next start | n/a |
| Wallpaper | Noctalia wallpaper; Wallpaper Engine via `wallpaper-mode.sh` | none | none | `qs ... wallpaper set` if Noctalia answers, else `wallpaper-mode.sh static` | Yes (Noctalia fades). |

Design decisions:

- **pywal** is kept as a palette source, not a second theming system.
  `apply-pywal-theme.sh` still runs `wal` and `sync-pywal-theme.py` on every
  wallpaper change. Before activation it behaves exactly as before. After
  activation it stops pushing colours itself: with a fixed theme it exits, in
  wallpaper mode it calls `theme wallpaper-mode`.
- **Noctalia** gets one generated scheme, `Unified`, with the same colours
  under `dark` and `light`; the theme's `mode` sets Noctalia's dark switch.
  Noctalia then rewrites its own `colors.json` and `settings.json`
  (tracked files in this repo) as it does for any scheme change. Its template
  hook pushes Hyprland border colours; `hyprland.conf` uses the same mapping, so
  the two always agree.
- **GTK** uses colour overrides only, no theme build. GTK 4/libadwaita apps
  follow them fully. GTK 3 follows them fully only under a theme that reads the
  libadwaita names, such as adw-gtk3, which is **not installed**; under
  `cachyos-nord` only widgets using the classic `theme_*` names change.
- **Qt** gets a qt6ct palette and, when a Kvantum theme is in use, a copy of
  that theme's `.kvconfig` with `[GeneralColors]` recoloured and its SVG linked.
  Widget artwork drawn from the SVG (GlassDark's frames and gradients) keeps
  its original colours.
- **Neovim** uses the theme's own colourscheme when its plugin is in
  `lazy-lock.json` (today: tokyonight, catppuccin). Otherwise tokyonight is
  recoloured from the palette through `on_colors`. `theme doctor` says which.

Not themable from a palette, and left alone:

- **Icon packs.** A theme may name one (`extras.icon_theme`); `theme doctor`
  reports whether it is installed. Nothing is installed or switched. The
  configured `char-white` is itself not installed.
- **Cursor theme, fonts, SDDM** (needs root; its theme is one of three stock ones).
- **p10k prompt** (119 hard-coded 256-colour indexes; they follow the terminal
  palette only loosely), **zsh syntax highlighting** (uses terminal colours).
- **Zed, Tern, VS Code** (own theme files; Omarchy's `vscode.json` would mean
  installing an extension).
- **Hermes liquid-glass** keeps following the pywal cache through its own `apply.sh`.
- **Noctalia plugins** (keybind cheatsheet, codexbar, workspace-copilot HUD)
  follow Noctalia's colours, except about 40 hex literals in plugin QML.
- **Hyprland Lua config** (not deployed): no generated Lua file yet.

## Adding a component

1. Write `render_<name>(palette) -> {relative path: text}` in
   `scripts/theme_manager.py`. Use `palette["colors"]` and `palette["ansi"]`.
2. Add a `Component(...)` to `COMPONENTS`: its `Wire`s (`line`, `symlink` or
   `file`), a one-line reload description, the binary it needs, and optionally a
   function returning the live reload command(s).
3. Add the generated file name to the list in `tests/test_theme_manager.py`.

`render_all` and `theme doctor` pick the component up from the table.

## Activation on the live machine

Run from `/workspace/.files` after this branch is merged or checked out there.
`~/.config/*` mostly symlinks into the repo, so wire steps show up as
uncommitted edits in the checkout.

### Safe at any time (nothing visible changes)

1. `ln -s /workspace/.files/scripts/theme ~/.local/bin/theme` (or re-run `scripts/onboard`).
2. `theme doctor` and `theme list`. Both are read-only.
3. `theme apply tokyo-night --dry-run`. Prints the files and commands; writes nothing.

### Changes the live look

4. `theme apply tokyo-night --no-reload --keep-wallpaper`
   Writes `~/.local/state/theme/`. Nothing is wired yet, so nothing is visible,
   **but from now on wallpaper changes no longer recolour terminals, borders
   and dunst** (the pywal hook defers to the manager). Undo: `rm -r ~/.local/state/theme`.
5. Wire and reload one component at a time, checking each. Suggested order,
   least to most visible; `theme apply tokyo-night --keep-wallpaper` after each
   wire performs that component's reload.

   | Step | Command | You will see | Undo |
   |---|---|---|---|
   | a | `theme wire tmux` | tmux status bar takes the theme | `theme unwire tmux` then `tmux source-file ~/.tmux.conf` |
   | b | `theme wire kitty alacritty` | open terminals recolour (alacritty by itself, kitty on apply) | `theme unwire kitty alacritty` |
   | c | `theme wire shell delta btop rofi` | new shells, next `git diff`, next btop and rofi launch | `theme unwire ...` |
   | d | `theme wire hyprlock` | next lock screen. **Lock once (`hyprlock`) to confirm it still starts**: hyprlock itself was not run in testing. | `theme unwire hyprlock` |
   | e | `theme wire dunst` | notification colours; shown notifications are dismissed on reload | `theme unwire dunst`, `dunstctl reload` |
   | f | `theme wire hyprland` | window borders and group bars. Confirm with `hyprctl configerrors` (expect none). | `theme unwire hyprland`, `hyprctl reload` |
   | g | `theme wire noctalia`, then restart Noctalia once (`scripts/bar-mode.sh restore`) | bar disappears for about a second, comes back; apply then recolours bar, launcher and panels | `theme unwire noctalia`; pick the old scheme in Noctalia settings |
   | h | `theme wire gtk qt` | GTK and Qt apps started afterwards; open qt6ct apps recolour | `theme unwire gtk qt` |
   | i | `theme wire nvim` | next `nvim` start | `theme unwire nvim` |
   | j | `theme wire waybar` | only if you switch back to waybar | `theme unwire waybar` |

   `theme wire --all` does all of this in one go.
6. `theme apply <slug>` without `--keep-wallpaper` also sets the theme's
   wallpaper: through Noctalia if it answers on IPC, otherwise through
   `wallpaper-mode.sh static`, which stops Wallpaper Engine.
7. Commit the wired configs in `/workspace/.files` when satisfied.

Step f changes the `source =` line that the Hyprland Lua migration inventory
and ownership map pin (`tests/test_hypr_lua_ownership_map.py`,
`tests/test_hyprland_lua_migration.py`). Regenerate them with
`scripts/build-hypr-lua-inventory` and `scripts/build-hypr-lua-ownership-map`,
and mirror the line into `config/hyprland/hyprland.conf`.

Full undo at any point: `theme unwire --all`, `rm -r ~/.local/state/theme`,
then `hyprctl reload`, `dunstctl reload`, `tmux source-file ~/.tmux.conf`.
The pywal flow is in charge again as soon as the state directory is gone.

To return to wallpaper-derived colours while staying wired: `theme wallpaper-mode`.

### Proposed key bindings

None of these is bound in `hyprland.legacy.conf` or `phantomat.legacy.conf`
(checked in the files, including the uncommitted edits). They sit beside the
existing wallpaper binds, which use Super+Shift with the same keys.

```
bind = $mod CTRL, T, exec, $HOME/workspace/.files/scripts/theme pick
bind = $mod CTRL, period, exec, $HOME/workspace/.files/scripts/theme next
bind = $mod CTRL, comma, exec, $HOME/workspace/.files/scripts/theme prev
bind = $mod CTRL SHIFT, period, exec, $HOME/workspace/.files/scripts/theme wallpaper next
bind = $mod CTRL SHIFT, comma, exec, $HOME/workspace/.files/scripts/theme wallpaper prev
```

They are not added by this branch: new binds also need
`scripts/build-hypr-lua-binds` and the inventory regenerated.

## Testing

`tests/test_theme_manager.py` covers the normaliser, both Omarchy import
formats, idempotent import and apply, `--home` isolation, the wire/unwire round
trip, wallpaper mode and the pywal hook hand-over. Everything runs against a
temporary home with stubbed session tools.

Known gaps: hyprlock, rofi, dunst, btop, GTK and Qt have no offline checker, so
their generated files were checked for syntax only and have not been seen on
screen. Noctalia's reload and `theme pick` have not been run at all.
