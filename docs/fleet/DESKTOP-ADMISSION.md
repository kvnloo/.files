# Interactive desktop admission

CPU-only builds, tests, renders and encodes belong on MBP or a worker-only Kueue flavor. Unsafe/unavailable workers return 75 or remain queued; they do not authorize a groot fallback. A `render` label is not proof of GPU use.

## Installed seams

- `fleet run` checks persisted pause state even for `--node`; fresh thermal/health/memory admission happens before transfer and again on MBP after transfer. Missing/nonfinite thermal readings fail closed. The fleet health timer closes `z0.dev/cpu-admit` on the first unsafe sample, independent of cordon strike hysteresis.
- `factory` and `lanes` have only `node-mbp` CPU placement. Its flavor requires `z0.dev/cpu-admit=true`. `45-interactive-cpu-placement.yaml` denies unpinned/groot CPU-heavy pods in factory/lanes/z0. Real NVIDIA resource allocation permits GPU placement on groot with explicit bounded CPU and memory. A <=200m/64Mi one-container infrastructure exception preserves the existing gateway.
- `hermes-worker-.scope.d` is a systemd dashed-prefix drop-in for future tool scopes. It does NOT match Hermes gateway/core services. Workers enter `agent.slice` at launch, inheriting limits before children execute. The classifier is recovery for recognized agent descendants, not the primary admission path; desktop/browser/audio and CLI control roots are excluded.
- `/dev/sdb` is an SSD. Agent IO has no `io.max` bandwidth cap, because an 8/4 MB/s cap stalled every agent tool and MCP server. Memory uses only hard `MemoryMax` limits, because `MemoryHigh` throttling livelocks over-budget jobs. Tool scopes carry `RuntimeMaxSec=8h`, so forgotten background jobs are reaped.
- `z0-worker-supervision` keeps its existing timer. Operational mode reads a primary-key-bounded message window, performs no repository discovery/status scans, and carries older unresolved evidence as explicit holds. Full replay remains an on-demand operation. This is bounded replay, not a fully incremental historical index.

## Install and verify

Run from the intended isolated integration tree; the installer symlinks exact owned files and backs up replaced targets. It does not merge, push, restart the gateway/compositor/k3s, or install ctx's staged restart configuration.

```sh
python3 scripts/install-desktop-admission --apply --receipts /mnt/zer0models/workspace/zer0/data/operations/desktop-lag/20261022
KUBECONFIG=$HOME/.kube/k3s.yaml kubectl apply -f config/k3s/manifests/45-interactive-cpu-placement.yaml
KUBECONFIG=$HOME/.kube/k3s.yaml kubectl apply -f config/k3s/kueue/queues.yaml
python3 scripts/verify-desktop-admission
fleet-build --node mbp --wait 0 -- python3 tests/test_desktop_admission.py
```

Inspect `/sys/fs/cgroup/.../cpu.max` and `io.max`, not just configured systemd properties. API dry runs prove admission, not running pods. Check real Job `spec.nodeName`, completion and logs separately. Never uncordon a hot worker just to get green evidence.

The placement binding covers every namespace selectable by the configured
ClusterQueues: `factory`, `lanes`, `fleet-mbp`, and `z0`. The z0 `cpu` flavor
deliberately has no node labels so its CPU quota can accompany the GPU flavor;
it does not bypass pod admission. The verifier exercises all seven placement
cases in each namespace plus full MBP lane acceptance and GPU/nodeName bypass
rejection (30 server dry runs). The trusted
`fleet-mbp` namespace retains its Kueue-owned 4-CPU/10441814016-byte budget only
when explicitly selecting MBP; groot's per-container limits remain unchanged.
Factory's GPU case is denied by its zero-GPU ResourceQuota. Keep queue namespace
selectors and this binding aligned when adding queues.

## Canonical film continuation

`fleet-fframes-delivery --out NEW_DIRECTORY --wait 0` uses the canonical script and exact picture/soundtrack input files. It extends existing `fleet-build` with exact `--input FILE:RELATIVE_PATH`, retains the remote job with `--keep`, and fetches only final encodes/logs. It refuses to overwrite the paused source artifact tree. Direct canonical `deliver_v2.py encode` fails with 75 on groot; MBP execution must prove an effective fleet scope CPU/memory ceiling. Genuine GPU film rendering remains local within the agent envelope.

Do not resume an old in-memory delivery parent locally: its imported functions predate the guard. Coordinate the original task owner, preserve partial files, and use a new remote output directory. A transport failure after source transfer can leave a retained partial job; inspect its exact ID before retrying. Do not blindly replay a job that already received an ID.

## Limits

This is owned-workflow admission, not a same-user security sandbox: a user/admin can deliberately bypass wrappers or create workloads in other namespaces. Kube-system/control-plane services are not throttled by this policy. Health labels are observations, not continuous thermal guarantees for already-running jobs. Prefix limits protect native Hermes scopes only while its systemd backend is available; classifier recovery is best-effort for other launch paths. No sustained no-lag claim follows from a short probe.

The ctx resource policy is owned by `config/systemd/user/ctx.service.d/50-resource-policy.conf`.
Install it with `python3 scripts/apply-ctx-policy --apply` from the intended
integration tree. The installer backs up and removes only its five exact
`user.control` property overrides, links an immutable content-stamped drop-in,
and reloads systemd without restarting ctx. It leaves ctx's generated unit,
supervisor environment, source databases and indexing mode untouched.
The hard ceiling remains 5 GiB resident/cgroup memory plus 2 GiB swap; there is
no `MemoryHigh` reclaim throttle. `OOMPolicy=stop` and a bounded restart rate
prevent a partial daemon or rapid crash loop. This budget is a desktop safety
ceiling, not a guarantee that every corpus fits. Do not raise it without a
measured refresh peak and host headroom.

The older single-preparation-worker drop-in remains staged and is not installed
by this policy: ctx 2.2.8 already defaults to one preparation worker. Its
`ExecStart` override is not needed for the resource fix. Preserve the generated
`env -i` launch contract rather than installing that redundant override.

## Report-only host drift

`config/host/groot.toml` inventories managed live paths and tracked sources.
`scripts/host-drift` prints JSON on stdout and a short summary on stderr:
exit 0 is clean, 1 is observed drift, and 2 means at least one observation is
unknown (observed drift remains in the report). No outcome authorizes repair.
The checker compares bytes, mutable-checkout symlinks, managed systemd resource
properties, tracked sysctl values, package `.pacnew` files and both persistent
and runtime `user.control` drop-ins. Optional manifest `effective` values
override derived scalar systemd directives when systemd exposes a different
property representation. Managed paths are processed in lexical drop-in order.
An `owned-upstream` classification and issue URL explain drift, never exempt it.
An explicit `mask=true` declaration requires a `/dev/null` unit symlink.
`secret="private-exception"` verifies only current-user ownership/mode 0600
and the tracked nonsecret declaration; it never reads credential bytes and
always reports private-content provenance as unknown.
The optional `[budget]` inventory names `desktop="session.slice"` and bounded
`groups=[{scope="user",unit="agent.slice"}, ...]`. Every audit compares physical
RAM minus effective desktop `MemoryMin` with the largest single sibling group's
effective `MemoryMax`. Named nested children are not double-counted. Missing or
unbounded non-desktop groups are unknown, never discarded; finite shortfalls
are drift. This does not claim that summed budgets fit RAM or prevent global
OOM; memory.min is reclaim protection, not an OOM exemption.

Run `python3 scripts/install-host-drift` to preview, then add `--apply` to
snapshot the complete tracked source closure and enable `host-drift.timer`.
Reinstall after any manifest/source change; the installed checker never reads a
mutable worktree. The timer runs every 30 minutes with Nice 19, idle IO and a
256 MiB hard memory limit. It writes `~/.local/state/host-drift/latest.json`.
ServiceWatch records finite drift/unknown counts through its existing one-hour
incident dedupe, six-hour notification dedupe and five-notifications/hour ceiling;
inspect the local JSON for exact paths.
No watched desktop, gateway or agent service is restarted.
The installer also links the tracked, stamped `config/host/z0-guard-state.json`
to the default guard inventory. Its `host_drift` binding enables law I against
this receipt; code activation is separate from the live z0intelligence service.
The same installer stamps ServiceWatch's heartbeat/failure helper and units.
A healthy heartbeat reads only its status receipt, without opening the incident
database. Missing, malformed, stale or future heartbeats still alert through
the normal store. Tiny reporting helpers retain nice/idle IO and hard memory
limits, but not the old 5%/10% CPU throttles; their 90-second deadline no longer
expires before SQLite's 30-second lock wait plus notification work. The retained
2026-10-24 23:05–23:06 journal showed both the heartbeat and its failure handler
timing out at the old 20-second deadline. This fixes the avoidable reporting
path contention; it does not prove unlimited IO-stall resilience.
The structured `~/.z0int/loop/last-tick.json` summary records exit-3 degraded or
partial-measurement ticks as deterministic deduplicated warnings in the existing
digest, with no model escalation or desktop notification. Exact
`Z0INT_LOOP_TICK` JSON warning lines are not generic journal errors, and declared
degraded full tick rows are not silent no-ops. Real failures and legacy
unclassified no-op rows retain their existing failure paths. This receipt
describes the latest outcome; existing timer health checks own freshness.

Template and dashed-prefix resource policies compare only loaded matching
instances. A policy with no loaded instances is explicitly not applicable,
not a fabricated effective unit. Device latency directives are checked against
the real unit cgroup's `io.latency`, not a nonexistent scalar systemctl property.
External observations share a 120-second deadline; exhausted observations are
unknown instead of monopolizing the reporting timer.

The package-file inventory is bounded to `/etc` and 16 directory descents
(20,000 entries maximum); it never walks home/model volumes or follows directory
symlinks. Unreadable directories or exceeded bounds yield unknown, not clean. An admin must
review inaccessible package configuration separately. Extra bounded roots can be
given with repeated `--pacnew-root`. This is not an unrestricted package audit.

A temporary control drop-in needs a local lease in
`~/.local/state/host-drift/leases/SHA256_OF_ABSOLUTE_PATH.json` containing
`schema="host-drift.lease.v1"`, exact `path`, nonempty `owner`, future epoch
`expires_at` and the drop-in's `sha256`. A changed or expired lease does not
exempt the file. The checker never creates leases. Persistent changes belong in
the tracked source and stamped installer, not `systemctl --user set-property`.


## Foreground activation gate (do not call this complete early)

Native background terminal tools were exercised inside `agent.slice` with CPU max
`100000 100000`. Native foreground calls were independently found still launching
inside `hermes-core.scope` without a CPU ceiling: the prefix drop-in alone is NOT
proof of complete protection. The isolated Hermes branch
`repair/foreground-resource-admission-20261022` carries the small
`LocalEnvironment._run_bash` entry hook. It calls installed `agent-tool-run` before
payload execution. The wrapper owns its conservative shell parser in this
checkout and uses the native systemd scope manager; it needs no external z0int
checkout or private home state. It holds known CPU builds/tests/encodes, exempts
explicit single interactive application/CLI launches from workload throttling,
and never falls back to direct execution if parsing or scope creation fails.

`python3 scripts/verify-hermes-foreground-entry` exercised the exact patched method
body in isolation using real subprocesses and kernel cgroups; only environment
resolvers were injected. It observed an immediate 1-CPU agent scope and a cargo
build hold (75). It is NOT a live-gateway turn test. The parent must integrate the
Hermes source patch, checkpoint active sessions, perform its owned gateway restart,
and re-run the actual foreground terminal cgroup probe before declaring all future
launches protected. Do not throttle the gateway/core to hide that activation gap.

## Groot user-layer configuration audit (2026-10-25 UTC)

`scripts/inventory-host-user` is a read-only, bounded inventory of configured
units/drop-ins, enabled links/timers, lingering, manager overrides, environment
paths, service executable provenance, resource properties and per-cgroup memory/IO
PSI. It never exports environment values or full command arguments. Run it in a
1 GiB `background.slice` scope with idle CPU/IO scheduling; retain JSON outside git.
The initial observation had 428 configured paths and 298 loaded services/scopes/
slices. These are time-bounded counts, not a claim that every service is healthy.
Linger was enabled. `user@1000.service` used packaged delegate/login-barrier
drop-ins; no local user manager configuration drop-in was present.

`config/host/groot.toml` records kept declarations and their installer. Existing
activation is preserved, including inactive services and timers: adoption does
not approve their historical purpose or start them. Native `.local/bin` binaries
remain application-managed; `config/host/user-executables.json` records observed
hashes/paths, not reproducible binary builds. Stamped helpers include their local
import/config closure. Dunst's existing `/dev/null` mask is preserved.

Install from the intended merged tree:

```sh
python3 scripts/apply-agent-oom --user-layer
python3 scripts/apply-agent-oom --user-layer --apply
```

This reuses the agent installer's content-stamped release implementation. It
backs up replaced paths and exact inventoried unleased `user.control` files,
rejects changed files/controls rather than overwriting a possible new lease,
atomically links declarations, and daemon-reloads without restarting any service.
Backups live under `~/.local/state/host-user/backups/`. There is no recursive
control-directory deletion. The legacy ctx controls were already removed by its
own installer before this snapshot.

| Setting | Initial live value | Kept/corrected declaration | Evidence |
| --- | --- | --- | --- |
| session CPUWeight / MemoryLow | 1000 / 4 GiB, untracked user.control | CPUWeight=1000, MemoryMin=MemoryLow=7 GiB | Session lifetime peak 6,346,428,416 B (5.91 GiB), ~18% protection margin; requires matching protected ancestor chain |
| session IOWeight | 1000, untracked, ineffective on mq-deadline | Remove override; `/dev/sdb` latency target 10 ms | Controlled direct-read trial below |
| agent telemetry / Dash watcher / service watcher MemoryHigh | 1500 / 384 / 128 MiB | infinity; retain existing hard caps | House rule: no reclaim throttle; ctx livelock diagnosis |
| farm MemoryHigh / MemoryMax | 6 / 8 GiB | infinity / 8 GiB | Peak 3,126,669,312 B; preserve established hard budget, remove soft throttle |
| dormant Hermes batch/heavy/interactive slices MemoryHigh | 8 / 10 / 4 GiB | infinity, unchanged hard caps | Same no-MemoryHigh rule, not new activations |
| T3 agents MemoryHigh / MemoryMax | 18,639,716,352 / 20,787,200,000 B, runtime | infinity / 4 GiB | Aggregate peak 1,229,709,312 B; parent-selected >3x headroom; initialization can overwrite until upstream fix |
| Multi-session OOMPolicy | hermes-core and hermes-web stop; gateway and T3 continue | Flag stop as blast-radius risk; do not silently change lifecycle | Inventory includes exact OOMPolicy for every loaded service/scope |
| Large unbounded groups | app and background slices, gateway/core, Noctalia, Ollama GPU | Explicitly reported, not guessed caps | Lifetime peaks must not be summed across parent/child groups |

Noctalia's peak was 930,508,800 B; T3 server 1,818,808,320 B; Hermes web
311,656,448 B (below the inventory's 512 MiB large-working-set flag). Chrome
scopes are listed individually. The agent aggregate's historical 14,181,822,464 B
peak exceeds its *current* 10 GiB hard cap; that is a pre-change historical peak,
not proof that the kernel is currently ignoring its cap. Caps and peaks may
reflect different policy periods. z0int-policy's separate failed 256 MiB budget
is owned by CapacityAutoEval; this installer does not invent a replacement.
Unbounded groups keep any global sufficient-memory guarantee unknown.

### Scheduler-independent desktop IO protection

With mq-deadline, plain `io.weight` does not provide proportional IO service
unless an effective weight-capable controller (BFQ/io.cost) is configured.
The delegated kernel `io.latency` interface accepted `8:16 target=10000`.
`IODeviceLatencyTargetSec=/dev/sdb 10ms` protects session.slice against sibling
background/app/agent traffic without hard bandwidth caps or scheduler changes.
No unmeasured target was added to another device.

`scripts/probe-desktop-io` uses only O_DIRECT reads against an existing 153 MiB
archive on the SSD. Two owned transient services run concurrently: random 1 MiB
background reads and paced 4 KiB session probes, each for six seconds/64 MiB RAM.
Same fixture and fixed random seed were used with target zero and then 10 ms:

| Measurement | Target off | Target 10 ms |
| --- | ---: | ---: |
| session p50 | 3.98 ms | 3.24 ms |
| session p95 | 18.70 ms | 11.99 ms |
| session p99 | 39.70 ms | 17.81 ms |
| background bytes | 834,666,496 | 730,857,472 |
| session full PSI total delta | 122,604 us | 67,493 us |

Receipts: `/tmp/files-io-before.json`, `/tmp/files-io-after.json`; background and
session PSI windows differ slightly at service startup. This short uncontrolled
host-load A/B is evidence of working controller admission and observed improvement,
not a sustained desktop latency guarantee or isolated causal benchmark.

### Upstream, secrets and OOM ranking boundaries

T3's installed service launches the packaged
`~/.t3/runtime/versions/0.1.2/t3`, not a local development checkout.
Its current source hardcodes runtime memory limits at initialization
([upstream issue 24708](https://github.com/pingdotgg/t3code/issues/24708)).
The manifest marks this `drift=owned-upstream`; an upstream-owned conflict is
still nonclean. The tracked T3 service sets the proposed
`T3CODE_AGENT_MEMORY_POLICY=inherit` seam for patched builds; old builds ignore it.
No T3 server restart or upgrade is performed here.

`TYPESAFE_API_KEY` was found globally exported by a private environment.d file
whose mode was already 0600. Its value is not tracked. The manifest's explicit
private exception remains unknown rather than claiming secret-source verification.
Actual name-based consumers found were OMP's `typesafe-jev/index.ts` and z0int's
`functions/jev.py`; no tracked user unit/helper directly named the variable.
Consumer-scoped BWS/`dsh-env-exec.py --allow TYPESAFE_API_KEY` injection is the
proposed replacement, requiring its separately authorized owner.

The classifier raises routed workload processes and Hermes-gateway descendants
to `oom_score_adj=800`, never lowering an already-higher score. Service MainPIDs,
recognized agent controls, browser/compositor/audio processes are excluded.
PID start-time identity and ownership are rechecked before each write. Scope
drop-ins cannot set service-only `OOMScoreAdjust`: the real mechanisms are
agent-launch's inherited process score and the classifier's recovery sweep.
`memory.min` is reclaim protection, **not immunity from global OOM selection**;
existing desktop processes need the root owner's separately planned lifecycle
to inherit a lower base score. No compositor/gateway/harness restart is authorized.

The two dangling `zer0-voice-maxine-full.service` links are backed up and retired:
the never-tracked experiment was superseded by `zer0-voice-direct` (PM commit
8fe26d0). This removes only broken symlinks, not voice data or PipeWire config.
Both direct voice and its watchdog were disabled/inactive when explicitly queried;
neither is started by this installer.

### Desktop placement: next login, not a live desktop restart

| Component | Observed current slice | Declared next-start slice |
| --- | --- | --- |
| Noctalia (also its notification/launcher surfaces) | app.slice | session.slice |
| Alternate Waybar transient service | not active in snapshot | session.slice |
| HyprCaffeine idle inhibitor | app.slice | session.slice |
| GTK desktop portal | app.slice | session.slice |
| Base/Hyprland desktop portals, compositor, PipeWire | session.slice | unchanged |
| Chrome interactive scope | app.slice | gap: packaged desktop entry, no tracked Chrome launcher |

The existing bar-mode launcher also explicitly requests session.slice for
future Noctalia/Waybar services. Four service drop-ins stage the same placement
independent of existing launcher paths. A daemon-reload can expose the new
configured Slice while a running service's actual cgroup remains app.slice;
only its next owned start/login moves it. No desktop service is restarted here.
Clipboard watchers are launched directly by the tracked compositor autostart,
not by separate app.slice units. UWSM is present, but the active Lua entrypoint
does not use the separate `config/binds.lua` browser shortcut. No user-local
Chrome desktop entry or tracked Chrome launcher was found, so this change does
not claim future Chrome placement is fixed.

