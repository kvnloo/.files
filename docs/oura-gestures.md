# Oura Gen 3 → Carly in Tern (experimental)

Direct, **opt-in**, local BLE motion gestures for the Oura Ring Gen 3 on Linux.
No factory reset, pairing, cloud requests, background mic, or automatic startup.

## Actions

| Gesture | Default | Notes |
| --- | --- | --- |
| Double tap on ring | `tern ctl carly open` | Opens Carly in an existing Tern window; **not** microphone PTT |
| Triple tap | `tern ctl carly close` | Closes Carly's UI |
| Four taps | Unbound | Optional `carly new` (resets conversation), see TOML |
| Shake | Unbound | Experimental; disable if it fires during ordinary activity |
| Single tap | Ignored | Avoid accidental activations |
| Touch-and-hold | Unsupported | Gen 3 has no confirmed contact/pressure sensor |

Gesture thresholds are **starting estimates**, not hardware-calibrated results.
Only the detector's offline tests have been verified; no Oura ring was available to validate this PR.

## Setup (manual; no system changes are performed by checkout)

1. Install Python 3.11+, BlueZ/Bluetooth, and Python packages in a virtual environment:

   ```sh
   cd ~/workspace/.files
   python -m venv .venv
   .venv/bin/python -m pip install bleak cryptography
   .venv/bin/python scripts/oura-gestures.py scan
   ```

2. Use **your existing ring application-auth key**. `open_oura` documents extraction from a rooted Android device with an already-onboarded ring; this implementation never extracts, resets, rekeys, or pairs. Never copy a published example key; it cannot authenticate your ring. The key must remain **outside the Git repository**:

   ```sh
   mkdir -p ~/.config/oura-gestures
   chmod 700 ~/.config/oura-gestures
   # Save your own 32-hex-digit key as ~/.config/oura-gestures/key.hex
   chmod 600 ~/.config/oura-gestures/key.hex
   ```

3. Run Tern with the scriptable control socket enabled in the actual **desktop window**, e.g. `tern --control /tmp/tern.sock`, or use its existing configured endpoint. Verify before linking:

   ```sh
   tern ctl state
   tern ctl carly open
   ```

   A `tern serve` headless instance is **not** an interactive Carly session. Carly commands are desktop-only in Tern's published scripting interface. No Tern process will be launched by this tool.

4. Stream for two minutes with no actions, adjust threshold after observing real traces:

   ```sh
   .venv/bin/python scripts/oura-gestures.py listen \
     --address 'RING_BLE_ADDRESS' \
     --key-file ~/.config/oura-gestures/key.hex \
     --seconds 120 --dry-run \
     --capture ~/.local/state/oura-gestures/taps.jsonl
   ```

   When double and triple taps are distinguishable from ordinary motions:

   ```sh
   .venv/bin/python scripts/oura-gestures.py listen \
     --address 'RING_BLE_ADDRESS' \
     --key-file ~/.config/oura-gestures/key.hex \
     --tap-threshold 450 --seconds 120
   ```

Use a new `--capture` filename for each session (it refuses overwrite, creates `0600` files, and rejects paths inside the Git checkout). Replay a private trace with `python scripts/oura-gestures.py replay ~/.local/state/oura-gestures/taps.jsonl`; replay never runs actions. Keep recordings private because motion traces are personal data.

`--address` comes from `scan`. Raise `--tap-threshold` if incidental hand motion fires; lower it if deliberate taps are ignored. *Do not share actual auth keys, ring MACs, or raw BLE captures publicly.* The ring may allow only one active peripheral connection, so a phone connection can block desktop access. Linux pairing/link encryption may still be required by BlueZ before using GATT even with the application key; this tool deliberately does not initiate pairing.

## Replay and tests

JSON Lines replay (timestamp seconds, raw signed counts):

```json
{"t": 0.0, "x": 0, "y": 0, "z": 1000}
{"t": 0.02, "x": 700, "y": 0, "z": 1000}
```

```sh
python -m pytest -q tests/test_oura_gestures.py
python scripts/oura-gestures.py replay path/to/trace.jsonl
```

Replay **always dry-runs actions**, regardless of CLI flags. Commands are argv arrays in [`config/oura-gestures/actions.toml`](../config/oura-gestures/actions.toml); never passed to a shell. A successful `tern ctl` exit is checked for its `{ "ok": true }` reply. No command is mapped for a missing or unrecognized gesture.

## Safety and limitations

- Each listen invocation auto-stops after **at most 60 minutes** and always attempts a realtime-OFF write in `finally`. The finite duration is also embedded in the ring's request. On abrupt process kill/connection loss, firmware's timeout is the fallback.
- This approach consumes additional ring battery and may interfere with usual Oura sync. **No auto-start service** until battery impact, reliability, and reconnection are characterized.
- PTT here means gesture **launches Carly**. `carly voice listening` in Tern's script harness only sets simulated UI state; it does not start microphone capture. Do not confuse these. Actual start/stop/cancel mic routing must use a verified voice backend and explicit lifecycle contract.
- Continuous real-world tap accuracy, BLE reconnection, sensor sample interval jitter, and Linux Tern Carly support still require device-based verification.

## Provenance

BLE service UUID, 0x33 live ACM frames, 0x06 time-boxed measurement request, AES nonce challenge and OFF request were researched from [Th0rgal/open_oura](https://github.com/Th0rgal/open_oura) (Gen 3 Horizon live measurements). Carly's `tern ctl carly open|close|new` and the control socket are documented by [Stencil's Tern scripting SDK](https://docs.stencil.so/tern/scripts/carly.html). This implementation is independently written for `.files`, with offline packet and gesture tests; no hardware effectiveness is claimed.
