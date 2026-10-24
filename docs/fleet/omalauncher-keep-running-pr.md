# Draft upstream PR: keep Linux running (sticky service, start at boot, a supervised session)

Target: `SimonSchubert/omalauncher` (the source of `dev.omalauncher`).
Branch: `kvnloo/omalauncher` `feat/keep-linux-running` (based on upstream `main`).
Status: draft text only; not opened. (`derekross/omarchy-mobile` and its fork
`kvnloo/omandroid` are native Omarchy for Pixel phones on a mainline kernel; they
have no Android app and no `LinuxService`, so the fix does not belong there.)

---

**Title:** Keep Linux running: restart it after the app is killed, start it at boot, and supervise a user session script

**Problem**

People run services in the guest (sshd, tailscaled, `tern remote serve`, a
sync daemon) and lose them in two ways:

1. Every guest process lives only as long as the proot that started it
   (`--kill-on-exit`). `setsid`, `nohup` and double forks stay traced and die
   with it. The only proot that is not a window is PulseAudio's (and the widget
   shells), so a service started from a terminal dies when that window is closed
   or swiped from Recents.
2. `LinuxService` returns `START_NOT_STICKY` and only `MainActivity` calls
   `Runtime.start()`. When Android kills the process (lmkd `LOW_MEMORY` while
   the service runs, Samsung `AL_Kill`, a Recents swipe of the launcher, an APK
   update), Linux stays down until someone opens the launcher.

Today the only workaround is to shadow `pulseaudio` in `/usr/local/bin` with a
wrapper that starts a supervisor and then execs the real PulseAudio. It works
(we run it on two phones), but it depends on an implementation detail.

**Change (all opt-in, nothing changes without the flag/script):**

- `linux/GuestSession.kt`: if `~/.config/omalauncher/session` exists and is
  executable, run it in a proot of its own as soon as Linux is up (screen on or
  off, no window), and start it again with backoff when it exits, exactly like
  `AudioBridge.superviseDaemon`. Whatever it starts lives as long as it does: a
  supervisor such as runit, s6 or a plain loop. `Runtime.onLinuxReady` starts
  it next to `audio.start()`; `removeLinux` stops it next to `audio.stop()`.
- `LinuxService`: with `~/.config/omalauncher/keep-running`, return
  `START_STICKY` and call `Runtime.start()` (idempotent) from `onStartCommand`,
  so Android's restart of the service brings Linux, and with it the session,
  back. `startForeground` is wrapped: if Android 12+ refuses a background
  restart in the foreground (the app is not exempt from battery optimization),
  the service stops itself as before.
- `BootReceiver` (`BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`): with the same flag,
  start Linux after a reboot or an update. Both broadcasts may start a
  foreground service on Android 12+. Adds `RECEIVE_BOOT_COMPLETED`.

**Why a file flag and not a setting:** it lives in the guest's home like
`layout.toml` and `style.toml`, so it is scriptable and survives a reinstall of
the app data only if the guest does. A toggle in settings › linux can write the
same file later.

**Testing (to do on device):**
- `touch ~/.config/omalauncher/keep-running`; `printf '#!/bin/sh\nexec sleep infinity\n' > ~/.config/omalauncher/session; chmod +x` it.
- Force-stop is not a test (it disables restarts); kill the process with
  `adb shell am crash dev.omalauncher` (the way lmkd would, from the app's point
  of view): `LinuxService` restarts, and `ps` in the guest shows the session
  again with no window opened.
- Reboot: Linux and the session are up before the launcher is opened.
- Without the flag and the script: behaviour is unchanged (`START_NOT_STICKY`,
  no session proot).

**Notes for reviewers**
- Under proot, Go daemons can hang in a netlink `recvfrom` at startup
  (`syscall.NetlinkRIB` in tailscale's `netmon.New`), so a session script
  should time-box daemon startups; that is the script's business, not the
  launcher's.
- The session proot is one more always-on tracer; it costs nothing while its
  processes sleep (measured: 0 context switches in 10 minutes for an idle runit
  tree).

Compile check: see the PR branch; `./gradlew :app:compileDebugKotlin` with a JDK 17
toolchain.
