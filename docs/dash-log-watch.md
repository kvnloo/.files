# Dash log watch

Report-only sidecar. It follows **existing** Dash bridge and three Metro user journals; it never restarts or modifies them. Healthy logs use zero inference calls. No new timer or general agent loop.

## Reboot-persistent Dash runtime

`scripts/install-dash-services --dash-repo /path/to/dash --activate` installs
`dash-bridge.service`, `dash-metro.service` and `dash-metro-relay.service`, all
wanted by `default.target`.
Code is archived to `/mnt/zer0models/releases/dash/<git-sha>/`, linked from
`~/.local/lib/dash/<git-sha>/` to keep dependency payloads off the root disk;
helpers are content-stamped under `~/.local/lib/dash-services/`. No service runs
from a worktree. Dependency installation uses frozen locks and disables scripts;
it does not compile or bundle JavaScript on groot.

The phone-qualified bridge is `f0362444cbb885d25e30f2818a1be78990690df1`;
the installed development-client APK last loaded app
`d5c4c17e50a22eef71c821663d07072c113f0ecf` from port 8212. This APK needs Metro
after a phone/app restart; port 8108 is an older preview, not this launch route.
Metro itself listens only on loopback port 18212. A bounded TCP relay exposes
port 8212 only on the tailnet address, and Expo's original-environment proxy URL
keeps generated manifests pointed at that same address. No user-manager BPF
firewall support is assumed.
The bridge binds only groot's tailnet address on 4747, retaining native
`~/.dash/token` and `bootstrap-token` authentication. Tracked environment files
contain only non-secret settings, not inherited desktop credential snapshots.
Each start waits for the tailnet address; failure retries after ten seconds.
The system tailscaled service must be enabled, and user lingering must remain
enabled for startup before login. User units cannot order the system manager's
tailscaled unit; the address gate is the cross-manager readiness contract.

The bridge provides chat/control independently of the optional voice broker and
artifact-stage viewer. Restoring those optional surfaces is not implied by a
healthy authenticated bridge. Existing phone pairing and app data are preserved.


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

The watchdog does not wait for the Store lock. It sends pings only while the
last completed scan is at most 90 seconds old, with the same startup grace.
A blocked scan cannot renew that deadline. After the deadline, the watcher
withholds pings so systemd can restart it. `status.json` records
`scan_completed_at`; status and heartbeat checks use that completion timestamp,
not process liveness or the start of an unfinished scan.

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
independent heartbeat timer checks completed-scan freshness. A separate ten-second
systemd watchdog thread takes no database/model lock: a slow scan or model cannot
starve the process liveness signal. Model calls remain on the dedicated triage
worker (HTTP 40-second, subscription 55-second deadlines); journal snapshots use
selector-based wall deadlines even when the child emits no newline.
The watcher never compiles or runs test suites on groot.

The single deployment source is the unified `deploy/live` checkout at
`/mnt/zer0models/worktrees/files-live`, not any task worktree. Live binaries and
unit links must resolve into content-stamped copies, never into the checkout.
Guard/reaper binaries and units use `scripts/install-z0-guard.sh`.
The three z0int live services receive `Z0INT_LIVE_HOME=%h/.z0int` through
`30-live-home.conf`, installed by `core-links`; a daemon reload reads the drop-ins
without restarting the router. The guard installer archives the committed
backend `src` from `Z0INT_BACKEND_REPO` (default `bend-policy-laws`) into the
release and records `backend-head`; runtime does not depend on that worktree.
O10 Git hooks are installed by `scripts/setup-phone-caps-hooks.sh` into
`~/.local/lib/files-hooks/<content-sha256>/`; both checks derive the committing
repository with `git rev-parse --show-toplevel`, never from the hook location
or a temporary extraction tree.
`uniichat-luna.service` preserves the live transient server's environment,
resource limits, slice and port 8798 as a permanent enabled user service.
O10 receives the actual checkout root and scans its scripts and registry.
When these IaC PRs merge into `dev`, replace the deployment with `/workspace/.files`,
switch the links together and build the guard release from that canonical tree.

`z0int-policy.timer` declares a fifteen-minute discovery/ingest/compile cadence
from the policy-only immutable release at `~/.local/lib/z0int-policy/current`.
The approved fleet declaration enables it. It first runs
`python -m z0int.policy.autoeval tick`, then `python -m z0int.cli policy`
ingest and compile only on success,
with a five-minute wall limit and bounded resources. The tick only reads cached
identities; uncached weights report `identity_pending` with capacity zero.
`z0int-model-identity.service` populates stat-keyed digests and metadata at nice
19 / idle I/O priority, separately from policy compilation. Its path unit
watches model directories and the serving registry; a daily timer is the
backstop. Discovery reads `$Z0INT_HOME/config/choice-ladder.json`; absent
configuration is a no-op.
Configured missing or near-expiry model scopes enqueue separate transient user
services so evaluation survives completion of the timer's oneshot. Those
workers use Kueue `bench` admission or the configured `groot-admit` CUDA lane;
the timer itself does not perform inference. The policy-only pointer must target
a content-stamped source release with its immutable Python runtime before
activation. It does not repoint the shared shadow release or restart model/loop
services. Real scorer/corpus/runtime digests and the exact serving `/props`
build_info belong in the private `choice-ladder.json` configuration.
During a schema cutover, keep the timer stopped until one manual
`systemctl --user start z0int-policy.service` succeeds and the published policy
matches the new contract. Only then start the timer. `enabled` alone does not
prove that a timer is active. The 2026-10-24 19:37:12 SIGTERM was the explicit
agent stop used to prevent a publication race, not evidence of an OOM kill;
matching MemoryPeak and MemoryMax alone must not trigger a cap increase.
The loop, intelligence and policy services declare `Z0INT_LIVE_HOME=%h/.z0int`
through drop-ins; installing these does not restart active model/loop units.
ServiceWatch checks contract-v1 policy files once per discovery cycle: policy
age over two hours only while new findings exist; source digest changes without
ingest for 24 hours; and positive `counts.o12_offload_obligation` in a fresh
`z0.policy_guard.v1` report. `available=false`, missing/malformed evidence or
oversized source artifacts are explicitly UNAVAILABLE, never zero violations.
Source hashing is cached by inode/mtime/size and bounded to 8 MiB per source and
16 MiB of fresh hashing per cycle. Findings sampling is bounded to 1000 rows/2 MiB.
Only finite codes and numeric counts enter triage; source paths and guard explanations stay local.

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

## Deterministic worktree cleanup

`z0-guard worktrees --inventory` records the checkout classification without
removal. `--apply` immediately archives and removes eligible non-LIVE checkouts;
`--daily` applies the age policy (SAFE at least 3 days, WIP at least 14 days).
LIVE checkouts are never removed. The classifier lives in
`scripts/worktree-reaper.py`; other `z0-guard` commands retain their existing
external ops-plane dispatcher.
The LIVE collector scans all symlinks under `$HOME`, including dangling targets.
It also scans the agent configuration roots and `/workspace/hermes-home`.
Installed plugin, extension, and skill directories are live code sources.
The shared `symlink_references(home=None, extra_roots=None, out=None)` collector
builds one process-local link index. It retains only directory and symlink names,
not regular-file inventories. Each recheck validates directory identity, timestamps
and accessibility, rescans changed directories, and resolves current link targets.
New nested links and retargeted links therefore invalidate cleanup decisions.
`installed-link-scan-latest.json` records completion and errors without dumping the
index into tool output. Run HOME scans outside the orchestrator scope in a bounded
background slice; archive and removal checks reuse the same process-local index.
Unreadable link inventories block removals, except `EACCES` on a foreign-owned
directory with no group/other read or execute bits. The scan receipt records
that exclusion as `unreadable_foreign_owner`. A traversable directory such as
mode `0711` still fails closed. A verified archive does not permit removing a
checkout that still serves an installed link.
Every removal, including SAFE linked worktrees and standalone clones, requires a
verified local bundle receipt first. Linked worktrees share an immutable full
base bundle per common Git store; WIP delta bundles preserve each checkout's
additional state without duplicating the complete history. The manifest's
`restore_command` records both base and delta restoration when needed. A base
clone remains when needed by LIVE linked worktrees. Archive errors prevent the
affected removal and remain visible in the operational records.
Absorbed submodules use a `.git` file without being linked worktrees. The reaper
preserves their Git state in a verified bundle before removing their directory.
It retains any common object store that still serves another linked checkout.
The checkout baseline validates real Git roots and excludes generated Git
fixtures beneath run, artifact, cache, and test-output containers; those fixtures
are not checkouts and do not contribute to the watcher threshold.
Generated containers include `runs`, `artifacts`, `cache`/`.cache`, `wiring`,
`_check`, byte-matrix output, nested `tmp`, test-output directories and pytest
temporary roots. The configured scan root itself (including `~/tmp`) remains a
real checkout container, not a generated-output exclusion.

The manifest and latest machine-readable counts are stored under
`/mnt/zer0models/workspace/zer0/data/operations/worktree-reaper/`.
The service watcher consumes `latest.json` for its worktree invariant.
A dedicated single-flight worker inventories actual checkouts using the reaper's
shared discovery function, then waits five minutes before refreshing again.
Discovery never holds the Store lock or blocks scans, model triage, or watchdog
pings. Each scan consumes its in-memory snapshot: digest and `status.json` expose
count refresh age, refresh-in-flight state, and explicit unavailable status before
the first result, after an error, or when the last result is over ten minutes old.
Failures preserve the last observed count rather than inventing zero checkouts.
Its
`--checkout-threshold` defaults to 200; repeatable `--checkout-root` overrides
the shared default roots, and `--reaper-status` overrides the latest-record path.
The invariant digest includes the latest cleanup counts, removals, and errors.
`core-links` runs `scripts/install-z0-guard.sh`, copying the launcher, classifier,
committed backend source, and `worktree-reaper.service`/`.timer` into
`~/.local/lib/z0-guard/<content-sha256>/`. Binary links, unit links, and an
existing timer-wants link point only into that stable version, never the source
task checkout. The installer leaves `service-watch` deployment untouched.
Groot's `fleet.toml` declares the timer. For explicit activation, run
`scripts/install-z0-guard.sh --activate`; this reloads systemd and enables/starts
the timer. Plain installation does not enable it. The persistent daily timer
catches missed runs, with up to 30 minutes of randomized delay.
Automatic cleanup is requested active. To suspend it, disable and stop only
`worktree-reaper.timer` and preserve archives and operational records. The
reaper's `PAUSED` marker also blocks mutating startup and the next removal-item
boundary; only the explicit owner resumes cleanup by clearing that marker.
