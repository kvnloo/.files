# Dash log watch

Report-only sidecar. It follows **existing** Dash bridge and three Metro user journals; it never restarts or modifies them. Healthy logs use zero inference calls. No new timer or general agent loop.

## Install and qualify

`core-links` in `scripts/onboard` links `dash-log-watch` and its user unit, but does **not** enable it or copy a machine-specific config. Inspect the example and install an explicit private `~/.config/dash-log-watch/config.json`. Its exact native package, hardware serial, provider, model and four actual unit IDs are mandatory. The shared OAuth helper is reused at an explicitly SHA-256-pinned path; preserve that worktree or deliberately re-qualify a new helper path.

```
dash-log-watch qualify   # bounded synthetic real OAuth request + fresh catalog
dash-log-watch check
systemctl --user daemon-reload
systemctl --user enable --now dash-log-watch.service
systemctl --user status dash-log-watch.service
dash-log-watch status
```

The qualification receipt records a real inference and fresh catalog at qualification time. There are no idle model/catalog probes: availability is explicitly last-verified health, not a claim of current quota. Every new incident response revalidates the exact returned model. `gpt-6-luna` is the only bare model allowed, on native `openai-codex`, official ChatGPT endpoint, tool list empty, storage disabled and SDK retries disabled. Native response identity is checked by the existing helper. No Nous fallback.

## Gates and sources

* ADB endpoint comes from the existing private `z0live/phone-adb.json` state and hardware is verified before subscribing. Recovery invokes existing `phone-adb reconnect`, with capped exponential retry on transport failure; no device/host scan or arbitrary fallback.
* Subscribe to Android activity event tags before a read-only initial top-resumed activity snapshot, rejecting events older than the device-clock watermark. Only exact `app.dash.mobile` top-resumed identity admits reviews; Expo Go, websocket presence and similar package names do not. Top-resumed loss/pause/stop close admission immediately.
* `adb track-devices` is a separate event-driven, length-framed transport-loss signal. Lost/failed transport is `UNKNOWN`, never active. Actual network-loss detection latency still depends on ADB/TCP; this is not an instant physical-network oracle.
* Journal follows the four exact configured **actual** units. Cursors persist in SQLite. First start tails from now, recovery accepts at most two minutes since cursor, invalid/vacuumed cursor resets to now and increments a gap counter. Foreground is always re-established before new reviews; skipped background errors are not queued for later.
* App-PID logcat is deliberately **not enabled** in this version. The runtime seat reviews Metro errors; Android activity metadata is the only phone stream. No screenshots/UI/audio/package installation/phone settings.

## Privacy and admission

No raw log line, chat, prompt, URL, stack trace, path, token or personal text reaches inference or local reports. Instead of guessing which strings need redaction, classification emits only finite error-code enums, allowlisted source labels, timestamps and SHA-256 evidence IDs. Model facts include at most eight events/6000 characters; local reports preserve all admitted burst hashes and exact journal cursors, not raw content. The evidence hash is SHA-256 of `json.dumps(record, sort_keys=True)` for the projected journal JSON record; the hash is not a guarantee that journald still retains that entry.

Two-second non-extending debounce; pending burst max24; fingerprint dedup persists for one hour. Single-source app/Metro errors route to runtime, bridge-only errors to bridge. Mixed bridge/runtime or critical signatures route to **one** correlation review, not three redundant copies. At most three concurrent one-shot subprocesses, six starts/hour persisted before spawn, 30,000 reserved estimated tokens/hour (5,000/request). Refusal/timeout/mismatch charges the admission, records a local report, marks review unavailable, and suppresses new calls for five minutes. The next new eligible error after cooldown may try the same model. No idle retries.

The reservation is a **conservative admission estimate**, not a hard provider-billed token ceiling: Codex does not support `max_output_tokens` on this route; hidden reasoning usage cannot be capped exactly here. Output is locally bounded by the reused helper (4096 characters), structured schema, a 45-second overall subprocess deadline and process-group kill. Queued excess/concurrency/budget events are not silently sent later. Some are deduplicated for the hour even when suppressed; counters/local suppression reports explain this loss. Unknown signatures are intentionally ignored, so generic app-specific errors outside the finite classifier can be missed.

Already-admitted bounded requests may complete after the phone backgrounds; **no new admissions** occur then. Cancellation during service stop kills helper process groups; systemd also owns the entire cgroup.

## Reports/status and retention

Protected local only: `~/.local/state/dash-log-watch/status.json`, `state.sqlite`, `incidents/*.json`. Directory0700/files0600; max200 reports and seven-day age pruning on subsequent incident writes. Cursor/seen/admission state survives restart; counters describe the current process. Status is updated on events, not a liveness heartbeat. Check `systemctl --user is-active dash-log-watch.service` with status readback; a file alone cannot prove a running daemon.

Critical incidents are structured and ready for a parent/Dash adapter, but **no supported notification/inbox delivery path was proven in the served bridge**, so this watcher sends nothing externally. `notification_delivery=local_reports_only`; never claim the owner saw a report. CLI is the supported status path for now; no unauthenticated HTTP server was added.

## Verification

CPU suite must run through MBP:

```
fleet-build --node mbp --light -- /usr/bin/python3 -m unittest discover -s tests -p test_dash_log_watch.py -v
```

`replay --journal-file FILE --state OWNED_FIXTURE_DIR --config CONFIG` is an explicitly synthetic offline journal replay. Only that CLI command overrides foreground and labels all outputs `fixture=true`; it never joins the live state directory. Feed only an owned synthetic journal unit, not private logs. A successful replay is **not** proof of a live phone foreground transition, real production fault, provider concurrency or notification delivery.
