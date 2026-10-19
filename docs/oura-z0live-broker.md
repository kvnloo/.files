# Oura broker dispatch (fork experiment)

Gesture detection now defaults to authenticated z0live broker dispatch rather than Carly.
Use a distinct z0live pairing token in a mode-0600 file:

```sh
python scripts/oura-gestures.py listen --address "$RING_ADDRESS" --key-file "$PRIVATE_RING_KEY_FILE" \
  --broker https://YOUR_BROKER --broker-token-file "$PRIVATE_Z0LIVE_TOKEN_FILE" --seconds 120
```

Replay is always dry-run. `--carly-fallback` enables the previous UI-only Carly action if broker dispatch fails; it is never claimed as voice/microphone capture. Double/triple tap alone are broker events. Each event contains gesture, authenticated source_device, Unix ts and UUID nonce, never raw motion or ring key. No automatic retry on ambiguous POST. A cooperative 1..300s broker listener lease is acquired before BLE and released after explicit OFF; it does not prove another listener's radio is OFF. The physical stream is bounded to at most 300s and OFF is attempted even if enable acknowledgement fails.

Use ONE listener: NOOP while phone owns the ring, this detector while the PC owns it. Switch only after witnessing OFF. Keep the existing private key and never reset/rekey. Disable the ring listener and Lawnchair Standby explicitly after the session.

Design, Android 14–16/One UI limits, context routing, desktop target and the owner acceptance script:
https://github.com/kvnloo/z0live/blob/feat/oura-context-routing/docs/GESTURES.md

Offline: 24 synthetic/mocked tests pass. Real ring calibration, Samsung capture, false positives, battery drain and acoustic latency are NOT RUN. No ADB, installs, live BLE or microphone have been used for this change.
