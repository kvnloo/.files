# phone-harness Android fast tree

An add-on for the [phone-harness](https://github.com/ShawnPana/phone-harness) Hermes plugin.
It makes every screen read on an Android phone about 80 times faster, without forking
phone-harness and without installing an APK or rooting the phone.

`scripts/phone-setup fast-tree` installs it. It copies these files into the plugin's agent
workspace (`~/.hermes/[profiles/<name>/]plugin-data/phone-harness/agent-workspace`),
fetches `u2.jar` from the `uiautomator2==3.7.0` wheel on PyPI (checked by sha256), and
appends `agent_helpers.fast-tree.py` to that workspace's `agent_helpers.py` once.

| piece | stock phone-harness | with the add-on |
|---|---|---|
| tree read (`screen()`, `ui()`, `find_text`, `tap_text`, `tap_ui`, `wait_for_text`) | new `uiautomator dump` every call: ~2 s, or ~10 s and a failure on screens that never go idle | JSON-RPC to a persistent uiautomator2 jar server: ~25 ms, never waits for idle |
| lock check | two `adb shell dumpsys` calls | one |
| `wait_stable` | pulls a ~2 MB PNG per poll | `screencap \| md5sum` on the phone, ~0.16 s |

Output is unchanged: the same node dicts in the same order.

## On the phone

- `/data/local/tmp/ph-u2/u2.jar`: the openatx uiautomator2 server jar (MIT, see
  `vendor/u2.jar.LICENSE`, sha256 `0b74e83c55f443539a9f76f5ce023a51466b764b1100e4097a897053fdfc0eb6`).
  It runs as the shell user through `app_process`, exactly like `uiautomator dump`.
- `/data/local/tmp/ph-u2/run.sh` (`vendor/ph-u2-run.sh`): starts the server, writes pid files,
  stops it after 300 s without a client.
- An `adb forward tcp:<random> tcp:9118` on the computer.

## Rules that matter

- The server sets `uiAutomationFlags=1`. Without it, the phone's accessibility services
  stay unbound for as long as the server runs.
- The server does not wait for idle, so a read within 1.5 s of an input re-reads until two
  dumps agree.
- While the server runs, any other `uiautomator dump` (Maestro, Appium, a phone-harness run
  from a workspace without this add-on) is killed by Android. Call `fast_tree_stop()` first.
- Any error falls back to the stock dump and writes the reason to `.fast_tree_failed`
  (stock is used for 10 minutes after that; delete the file to retry sooner).
- Remote adb server (`ADB_SERVER_SOCKET` through an SSH tunnel): `adb forward` binds on the
  remote host, so the add-on talks to the server with `curl` on the phone instead
  (~0.16 s a read). Force it with `PH_FAST_TREE_VIA=adb`.

Per command switches: `PH_FAST_TREE=0` (stock tree), `PH_FAST_WAIT=0` (stock `wait_stable`),
`PH_FAST_TREE_IDLE=<s>`, `PH_FAST_TREE_PORT=<device port>`, `PH_FAST_TREE_ALL_WINDOWS=1`.
In a script: `fast_tree_status()`, `fast_tree_stop()`, `fast_tree_uninstall()`,
`fast_tree_last_xml()`.

## Measured (Galaxy S25 Ultra, adb over Tailscale)

| call | stock | fast |
|---|---|---|
| `screen()` | 2.05 s | 0.025 s |
| `find_nodes()` | 2.07 s | 0.022 s |
| one-shot script `print(len(screen()))`, wall | 2.35 s | 0.30 s (0.76 s cold) |
| `wait_stable()` on a still screen | 1.2-1.5 s | 0.7 s |
| never-idle screen | 11.6 s, then `TreeUnavailable` | 0.025 s |
