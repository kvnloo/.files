# Phone setup map: Detent + live wallpapers + an agent that can drive the phone

This is how my Android phone is set up, written so another person's coding agent can
reproduce it. Each step says what to install, the command, and how to prove it worked.
`scripts/phone-setup` (doctor) checks every step and prints the next one.

```
computer (Linux/macOS/Windows)                     Android phone (10+; tested on Galaxy S25 Ultra / S22+)
  adb ──────── USB or wireless debugging ───────▶  Developer options
  Hermes + phone-harness plugin ── phone_exec ──▶  taps, typing, screen tree
     └ uiautomator2 fast tree (this repo) ──────▶  /data/local/tmp/ph-u2/u2.jar (no APK, no root)
  Wallpaper Engine (Steam) ── .mpkg ────────────▶  Wallpaper Engine app = live wallpaper
  kvnloo/detent main ──── adb install ─────▶  Detent fork = home app
     ├ scripts/detent-live-themes ──────────────▶  one Detent theme per live wallpaper
     └ scripts/detent-sync-colors (optional) ───▶  Detent "hyprland" theme follows desktop colours
```

## For the agent doing this

- Run `scripts/phone-setup` first and after every step. Fix the first `miss`, re-run.
- Ask the human before anything that loses data: uninstalling an app, clearing app data,
  factory reset, changing the lock screen. Nothing in this guide needs any of those.
- Steps on the phone screen (accepting the adb prompt, Play Store install, the Wallpaper
  Engine check mark, choosing the home app) are the human's. Ask them to tap; don't fight
  them for the screen while they hold the phone.
- Never put passwords, pairing codes or tokens in chat or in files in this repo.
- Settings live in `~/.config/phone-setup/env` (from `config/phone-setup/env.example`),
  never in this repo.

## 0. Get this repo

```sh
git clone https://github.com/kvnloo/.files.git ~/src/kvnloo-files
cd ~/src/kvnloo-files && scripts/phone-setup
```

Tools on the computer: `adb`, `git`, `jq`, `uv`, `curl`, `unzip`; for building Detent also
JDK 17 or 21 and the Android SDK.

## 1. adb

Install platform-tools: Arch `pacman -S android-tools`, Debian/Ubuntu
`apt install adb`, macOS `brew install android-platform-tools`, Windows
`winget install Google.PlatformTools`.

On the phone: Settings > About phone > Software information > tap **Build number** 7 times.
Then Settings > Developer options:

- **USB debugging** on, plug in, accept the "Allow USB debugging" prompt (tick "always").
- Or **Wireless debugging** (same Wi-Fi or a Tailscale tailnet): Wireless debugging > Pair
  device with pairing code, then on the computer `adb pair IP:PAIR_PORT` (type the code
  when asked) and `adb connect IP:PORT` (the port on the Wireless debugging screen, which
  changes after reboots; scripts here find the phone by its hardware serial instead).
- Turn on **Disable adb authorization timeout**, or Android forgets the computer after 7
  days without a connection.

Then `scripts/phone-setup init` pins the phone's serial into `~/.config/phone-setup/env`.

Prove it: `adb devices -l` lists the phone as `device` (not `unauthorized`).

## 2. Hermes phone-harness

[phone-harness](https://github.com/ShawnPana/phone-harness) gives Hermes one tool,
`phone_exec`: the model writes a short Python script (`screen()`, `tap_text()`,
`type_text()`, `screenshot()`, ...) and it runs against the phone over adb.

```sh
hermes plugins install ShawnPana/phone-harness/integrations/hermes   # enable it when asked
```

Restart Hermes (tools load per session). Optional: export `PHONE_HARNESS_PLATFORM=android`
in the environment Hermes runs in so it never picks another phone. With several adb
devices, set `ANDROID_SERIAL`.

Prove it: in a new Hermes chat, ask for `phone_exec` with
`ensure_device(); print([o["text"] for o in screen()][:10])`. You get the visible labels.

## 3. uiautomator2 fast tree

Stock phone-harness starts a new `uiautomator dump` for every screen read (~2 s, and it
fails on screens that never go idle). This add-on keeps the openatx uiautomator2 server
running on the phone instead: ~25 ms a read, same output. Details and switches:
[`config/phone-harness/agent-workspace/README.md`](../../config/phone-harness/agent-workspace/README.md).

```sh
scripts/phone-setup fast-tree
```

It installs into every Hermes profile that has the plugin, fetches `u2.jar` from the
`uiautomator2==3.7.0` wheel on PyPI (sha256-checked), and keeps a backup of
`agent_helpers.py`. You do not need `pip install uiautomator2` or its APKs.

Prove it: the same `phone_exec` with `print(fast_tree_status())` reports the server up,
and `screen()` returns in well under a second.

## 4. Wallpaper Engine on the phone

1. Own [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam (the
   wallpapers come from it) and install the free **Wallpaper Engine** companion app from
   the Play Store (`io.wallpaperengine.weclient`).
2. Get wallpapers onto the phone:
   - **Windows:** in desktop Wallpaper Engine use the phone/"Mobile" button and pair with the
     app; it sends any wallpaper over Wi-Fi.
   - **Linux** (no desktop app; scenes come from Steam's workshop folder, e.g. with
     [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)): put your
     wallpapers in `~/.config/wallpapers/live.json` (copy the shape of
     [`config/wallpapers/live.json`](../../config/wallpapers/live.json), which is my list),
     then `scripts/phone-setup wallpapers`. It converts each scene with
     `scripts/wallpaper-pkg2mpkg.py`, pushes it, and opens it in the app.
   - **Already on the phone, need the `.mpkg` on the computer** (for step 6): in the app,
     long-press the wallpaper > Share > "QR code or link", open the link on the computer and
     download the file that starts with `PKGM00`. Save it as `<workshop id>.mpkg` in
     `WE_MPKG_STORE`.
3. Apply one: the check mark in the app's preview > OK > "Set wallpaper" > **Home and lock
   screens**.

Don't publish converted `.mpkg` files: they are the workshop authors' work.

Prove it: `adb shell dumpsys wallpaper | grep WEWallpaperService` prints a line.

## 5. Detent (fork) as the home app

[Detent](https://github.com/bjarneo/detent) is a dial launcher. My fork (`main`)
adds a transparent theme that sits over the live wallpaper, live themes, folders and
swipe gestures. Build notes: [kvnloo/detent docs/FORK.md](https://github.com/kvnloo/detent/blob/main/docs/FORK.md).

```sh
scripts/phone-setup detent     # clones to ~/src/detent, debug build, adb install -r
```

It uses `DETENT_PACKAGE` from your settings (default `app.detent.launcher.fork`), so it
installs next to any stock Detent instead of replacing it. Keep building on the same
computer: the debug key is in `~/.android/debug.keystore`, and a different key means
`INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Never uninstall to fix that (it wipes the dial).

On the phone: open Detent, go through the setup, tap **set as home app** on the last step.
Hold the clock or empty space to reopen setup. Mine: custom dial on the left, a live theme,
glass off, `tap opens` on.

Prove it: `scripts/phone-setup` shows `Detent is the home app`.

## 6. Detent themes from the live wallpapers

```sh
scripts/phone-setup live-themes
```

For each wallpaper in your list it takes colours from the preview image, copies
`themes.json` and the `.mpkg` files into Detent (`run-as`, so the debug build matters) and
reloads. Pick one under setup > theme: Detent recolours and hands that wallpaper to
Wallpaper Engine; tap its check mark once.

Prove it: `scripts/phone-setup` shows `Detent live themes installed`.

## 7. Optional: Detent follows the desktop colours (Linux, Hyprland + Noctalia)

```sh
scripts/phone-setup color-sync
```

Links `detent-sync-colors` and a systemd user `.path` unit that fires whenever Noctalia's
`colors.json` changes (pywal fills it from the desktop wallpaper) and sends the colours to
Detent's `hyprland` theme over adb. Event-driven, no polling. Other desktops: call
`scripts/detent-sync-colors` from whatever hook your theme tool has, with
`DETENT_COLORS` pointing at a JSON file with `mSurface`, `mOnSurface`, `mPrimary`.

## Done when

`scripts/phone-setup` prints `all set`, and a Hermes `phone_exec` screen read returns fast.
