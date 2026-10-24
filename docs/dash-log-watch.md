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

## Host-wide service watch

`scripts/service-watch.py` generalizes this sidecar's atomic status files, SQLite
cursor/dedup state and finite log signatures. Dash's
foreground gate remains unchanged; host service failures must not be gated on a
phone foreground state. Install its `service-watch` link and four user units from
`config/systemd/user`, create
`/mnt/zer0models/workspace/zer0/data/operations/service-watch` with mode 0700,
then enable `service-watch.service` and `service-watch-heartbeat.timer`.
`fleet.toml` declares both on groot. `core-links` links but does not enable them.

The watch list combines active/failed user and readable system services, sockets
and timers with HostHygiene's `units.json` (KEEP/FIX/STOP plus structured health
invariants). New live units are discovered each minute. User OnFailure drop-ins
are generated without replacing existing hooks. System journals/state are
read-only: system-wide hooks in `config/systemd/{service,timer,socket}.d` and the
system notifier template require separate root approval. No new groups or ACLs.
STOP invariants suppress normal health checks, not an actually triggered failure
hook; no service is stopped, reset-failed, restarted or repaired by this watcher.

Every 15 seconds the deterministic lane checks failed state, restart deltas over
five minutes (three restarts), journal error windows (at least five errors and
25%), timer last-success age/result, file freshness, receipt error share and growth.
Successful inactive timer-service exits checkpoint a wall-clock success time;
new failed attempts cannot refresh it. A missing success checkpoint is explicitly
unavailable, not an invented stale age or a healthy result.
The built-in loop check uses actual `rows_added.shadow_decisions` in tick receipts:
three consecutive zero ticks, not a misleading success log line. Cognition-shadow
checks include `shadow[].error`/`parse_error`; an error-dominated file over 32MiB or
growing by over 64KiB in a sample is severe. File samples are bounded to 2MiB/1000
rows. Unknown/missing invariant evidence is warning/unavailable, never healthy.
First-start journal lookback is two minutes; `service-watch seed` streams the
last seven days (bounded to three minutes per journal) and historical tick
receipts, recording partial/unavailable coverage explicitly.

The recurring `phone_caps` deterministic invariant calls
`z0-guard phone-caps --root ROOT` in enforce mode. ROOT follows the resolved
installed `fleet` executable's checkout (or the watcher checkout if absent).
Inventory `health_invariant: {"kind": "phone_caps", "root": "/path/to/files"}`
can select an explicit checkout. Resource-cap findings produce the severe
finite code `phone_resource_caps`; a missing scanner, invalid response or
unreadable policy source produces `invariant_unavailable`, not a clean pass.
Only the finding count crosses the model projection; paths/source text stay
local. This check does not change limits, pause jobs or remediate anything.

The model worker cannot block deterministic checks. It batches each anomalous
unit window, sends bounded raw excerpts **only** to the host-owned Qwen router
endpoint (its IP must appear in live interface addresses), then sends finite signature/numeric projections to the router's
validated zero-cost Groq route. Potential severe incidents additionally use the
installed pi-ai SDK via `service-watch-confirm.ts`. The existing Dash Hermes
OAuth transport remains unchanged: host confirmation uses the requested
`~/.omp/agent/agent.db` instead, strictly read-only, with credentials in memory
only. No token refresh, credential copying or account writes. If no unexpired
subscription credential is available, confirmation is unavailable rather than
silently using a paid fallback. The helper independently validates the closed
vocabulary and can capture its actual SDK request payload (never headers) with
`--capture-request=PATH` for privacy audits. No auth data belongs in a receipt.
Qwen uses a constrained JSON schema, including nonempty integer evidence indices.
Seed/replayed windows recover at most twelve local journal excerpts preceding
the observation; raw excerpts are never persisted.
Provider errors keep the
deterministic report and record unavailable tier evidence, not an invented model
decision. Local model free text is discarded: neither persisted nor forwarded.
Redirects and environment HTTP proxies are disabled. All arbitrary text is
withheld before remote tiers, including secrets, emails, addresses, coordinates,
device IDs, home paths and local summaries; reports store withheld line/character
counts, SHA-256 evidence line IDs and finite classifications, not replacement
strings which might miss street/city information.

The first twenty raw-excerpt windows get a paired Qwen projection-only ablation.
`local_quality` records severity/cause sensitivity and cross-tier agreement, not
ground-truth accuracy. This measures dependence on private context without
exporting that context or local summaries.

Definite deterministic severe conditions notify immediately (without waiting for
model availability); other model-only severe decisions are confirmed by Luna.
Notifications carry unit, cause and `service-watch details ID`. SQLite admission
is cross-process atomic: one reservation per fingerprint/six hours, five total
per hour, reserved before delivery to prevent crash/retry spam. A failed delivery
is explicitly recorded; exactly-once delivery under a crashing notification daemon
is not claimed. Desktop-only: no verified phone path is assumed.

`service-watch status` is one line and exits nonzero for stale heartbeat.
`service-watch details ID` gives evidence/model/latency/confidence. Daily digests
are `service-watch/digests/YYYY-MM-DD.md`; `triage.jsonl` contains deterministic
and final model decisions, redacted windows and per-tier measurements suitable
for shadow learning. Units use Nice=15, MemoryMax=256M and CPUQuota=15%; the
independent heartbeat timer plus systemd watchdog detect watcher failures/hangs.
The watcher never compiles or runs test suites on groot.

Behavioral and captured-request privacy checks:

```
SERVICE_WATCH_TEST_EVIDENCE=service-watch-request-proof.json \
  fleet-build --node mbp --light --local-data --fetch service-watch-request-proof.json \
  -- env SERVICE_WATCH_TEST_EVIDENCE=service-watch-request-proof.json \
  /usr/bin/python3 -m unittest discover -s tests -p test_service_watch.py -v
```

Rollback: disable/stop only `service-watch.service` and
`service-watch-heartbeat.timer`; remove only generated
`*/90-service-watch.conf` user drop-ins and the watcher unit/bin links; run
`systemctl --user daemon-reload`. Preserve the report directory. If root hooks
were separately approved, remove only the three installed type-wide hook files
and `service-watch-system-failure@.service`, then `sudo systemctl daemon-reload`.
