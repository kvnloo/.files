# Agent display (Groot)

Kevin explicitly authorized this arrangement: the existing Hyprland owns a virtual
`AGENT-1` output; a nested Sway (`WLR_BACKENDS=wayland`) owns the agent clients.
This is not a second Hyprland compositor and never opens a physical seat/VT.
Workspaces 1, 2 and 8, the host cursor and the signed-in host window are no-touch.

One controller, no services:

```sh
A=/workspace/.files/scripts/agent-display
$A start                    # idempotent while the owned Sway is alive
$A status                   # verified PID/socket, WL-1 and named seats
$A tern --dir /workspace    # NEW signed window; foreground process holds the lock
```

The Tern command uses Kevin's HOME, real config, unlocked user bus/keyring and
`/run/user/1000/tern/daemon.sock`. It does not copy credentials or simulate sign-in.
Only Sway's server runtime is private. Tern receives Kevin's normal
`XDG_RUNTIME_DIR=/run/user/1000` for native service discovery, together with the
**absolute** nested `WAYLAND_DISPLAY=/run/user/1000/agent-display/wayland-1`.
The explicit Wayland socket and owned SWAYSOCK prevent host GUI routing.
It defaults to `/workspace`, not the caller's potentially stalled Btrfs directory.
Pass `--dir /workspace/PATH` or the normal Tern launch arguments for a fixture.
The normal Tern launch can create a tab in the shared daemon; do not close or alter
other sessions/panes. Never stop the shared daemon.

**One signed run at a time:** `tern` acquires `/tmp/tern-signed-window.lock`
non-blockingly and keeps it until the actual window process exits. Do not remove
this lock file or bypass it.

Account loading is asynchronous: the successful corrected probe remained
`gate.phase=reading` for 24.5 seconds after its first state observation before
becoming `phase=off, signed_in=true`. Wait for that real condition; never simulate
sign-in. On quit, wait for the wrapper's process exit (not merely disappearance of
the view) before the next signed run; cleanup can exceed a minute under host load.

From another terminal during your run:

```sh
$A swaymsg -t get_tree
$A ctl state                # real window IPC, includes gate.signed_in and phase
$A screenshot /tmp/agent-tern.png   # grim -o WL-1 on the private Wayland socket
$A focus-proof              # compare physical workspaces/focus to startup baseline
$A ctl quit                 # close ONLY this controlled window; release signed lock
# Leave the display up for another lead. Stop only when nobody needs it:
$A stop                     # refuses active signed runs or mapped clients
```

Named-seat pointer input (nested Sway only):

```sh
$A swaymsg 'seat seat-agent1 cursor set 500 400'
$A swaymsg 'seat seat-agent1 cursor press button1'
$A swaymsg 'seat seat-agent1 cursor release button1'
# seat-agent2 also exists; replace the exact seat name if you own that seat.
# For the controlled Tern window, prefer its semantic keyboard interface:
$A ctl key Escape
```

Confirm the target view and its controls before clicks/keys. Pointer move on
`seat-agent1` was exercised; button/keyboard examples were not exercised in the
acceptance probe. `seat-agent2` exists but has no attached input device. This does
not claim independent named-seat virtual-keyboard coverage. Never use host
`hyprctl` for input, focusmonitor, focuswindow or workspace switching.

For an existing input/capture helper, `eval "$($A env)"` exports the verified private
routing plus private cache/font settings. It is **not** a substitute for the signed
window lock. The first-level client class is `wlroots`; persistent rules in
`hyprland.conf` route `sway|wlroots` silently to `name:agent`, on `AGENT-1`, with
`no_initial_focus` and `no_focus`. The live legacy config sources these rules;
the tracked Lua rule set has the equivalent routing. The output is created on
demand, never by a new service.

## Proven receipt (2026-10-23)

Runtime/evidence: `/run/user/1000/agent-display/`.

- `state.json`: owned Sway PID/socket and nested Wayland socket.
- `signed-tree.json`: mapped `so.stencil.tern`, view 5, PID 3572305.
- `signed-ctl-state.json`: real `ctl state`, `ok=true`, gate phase `off`,
  `signed_in=true` (Kevin's existing account).
- `signed-tern.png`: grim capture of the real signed-in Tern interface, no gate.
- `host-placement.json`: `wlroots` on workspace `agent`, monitor 2 (`AGENT-1`).
- `focus-proof.json`: before/after active window `0x564783948e20`, DP-1 workspace 1
  focused, DP-2 workspace 2, unchanged through probe closure.
- `after-close-tree.json`: zero remaining views; Sway/output left running.

Latest corrected-runtime proof: `keyring-runtime-proof/` contains `tree.json`
(view 12, PID 241512), `signed-state.json` (`signed_in=true`, phase `off`),
`gate-observations.json`, `window.png` and `receipt.json`. The fresh before/after
focus matches, the controlled window exited 0, zero views remain and the lock is
free. Both GNOME_KEYRING_CONTROL and SSH_AUTH_SOCK were absent in the surviving
original launcher environment; no fabricated value or credential change was added.
This one-window proof establishes the corrected configuration works, not a
controlled causal comparison against the earlier slow keyring reads.

Startup deliberately uses Sway's pixman renderer, Tern's documented `STENCIL_GPU=cpu`,
a bounded font catalog, and a RAM-backed private XDG cache. The original launch
hung during GPU/font initialization; a subsequent signed process was blocked in
kernel filesystem I/O (`wait_current_trans`/`folio_wait_bit_common`). Kevin's normal
`~/.cache` resolves onto `/mnt/zer0models` Btrfs, whose I/O pressure was above 90%.
Private cache + `/workspace` launch + CPU rendering produced the mapped window.
This recipe avoids that path; it does not change Kevin's normal GPU/settings/cache.
