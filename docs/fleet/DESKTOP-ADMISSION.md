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
Refreshes run with `Nice=10` and `IOSchedulingClass=idle` so foreground work
takes priority. The host's mq-deadline scheduler honors this I/O class;
`IOWeight` alone does not provide that protection. After a policy restart,
check `ionice -p "$(systemctl --user show ctx -p MainPID --value)"` and confirm
refresh `processed_bytes` still advances before accepting idle scheduling.

The older single-preparation-worker drop-in remains staged and is not installed
by this policy: ctx 2.2.8 already defaults to one preparation worker. Its
`ExecStart` override is not needed for the resource fix. Preserve the generated
`env -i` launch contract rather than installing that redundant override.

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

## Groot system-layer audit and staged installation (2026-10-24)

`config/host/groot.toml` is the managed-path contract. Root configuration lives
under `config/host/etc/`; `scripts/apply-host-system` is dry-run by default.
The system stage copies exact tracked bytes, backs up replaced files/symlinks
with a receipt under `/var/backups/files-host/`, and retires the five obsolete
sysctl `.conf` files plus two duplicate local I/O-scheduler rules. The inactive
`.pre-migration` sysctl backup is evidence, not an active policy file.
The retired latency/swap and groot-memory installer entry points are removed.
The performance installer delegates system policy rather than writing a second
VM/scheduler policy. No desktop, terminal, gateway, k3s or zram restart occurs.
Only earlyoom and systemd-journald are restarted by `--apply`, each only when
its tracked configuration changed, with activation/verification logs.

### Observed deviations and decisions

| Setting | Observed live | Tracked desired / decision | Evidence |
| --- | --- | --- | --- |
| swappiness | 180 | retain 180 | Historical 3.6e9 file vs 0.9e9 anon refaults; kernel permits >100 for cheap in-memory swap |
| watermark_scale_factor | 200 | retain 200, not claimed optimum | Historical 36% direct reclaim; earlier 125 files conflict |
| page-cluster / VFS pressure | 0 / 50 | distro-owned, no duplicate | Installed `70-cachyos-settings.conf` |
| dirty limits | bytes=0/background=0, ratios20/10 | 256MiB/64MiB byte caps, ratios become zero | Runtime differed from last-on-disk file; distro already supplies these caps |
| overcommit | mode1, ratio100 | retain mode1, ratio100 | No measured reason to risk ENOMEM for large llama.cpp/Node/Bun/JVM mmap reservations |
| old CFS scheduler keys | absent | remove invalid writes | Current 7.2.9 scheduler has no latency/min/wakeup/migration-cost sysctls |
| other local networking/watch/process limits | existing custom values | preserve, not claimed tuned optimum | No measured reason to change working network/container semantics during memory repair |
| zram | logical=ram, resident=ram/2, zstd, priority200; failed_writes8,655,925 | kept; reconsider only with measured A/B (PSI + failed_writes + OOM count over >=24h) | Current11.63GB swapped/5.14GB resident supports keeping capacity; correct overcommitted workload budgets first |
| sdb SSD scheduler | mq-deadline | keep distro mq-deadline | Two current samples: util99.4/98.9%, r_await8.81/8.10ms, w_await15.27/13.94ms; no controlled BFQ A/B evidence |
| NVMe scheduler | kyber | distro-owned kyber, retire older local `none` writes | Installed `60-ioschedulers.rules` wins over both local singular rules |
| mounts | sdb2 btrfs noatime/compress=zstd:3; root/workspace NVMe XFS noatime/lazytime; sda unmounted NTFS | preserve, no remount | fstab, mnt-zer0models.mount, findmnt/lsblk snapshot |
| fstrim.timer | enabled, active weekly | preserve package timer | `systemctl status`; do not manually run trim under current I/O load |
| boot cmdline | `/proc/cmdline` equals `/etc/kernel/cmdline` | preserve source; generated Limine entry UNKNOWN | Limine12.9; `/boot` permission denied |
| systemd-oomd | active, user-1000/system.slice monitored at80%/30s, swap90% | separate `--oomd` stage: empty monitored set | Broad ancestor could kill desktop/harness; explicitly approved staged policy |
| earlyoom | active, memory5%/swap65%, Python/node preferred | remove --prefer; anchored harness/session --avoid; retain thresholds | ps comm: omp/hermes/tern/node-MainThread; packaged earlyoom1.9 help |

Effective-file order is lexical basename across sysctl.d directories, with
`/etc` replacing same-basename vendor files. `99-custom` sets swappiness180,
ratios10/5; `99-performance-tuning` replaces them with150,20/10, overcommit1
and unsupported CFS writes; `99-z-memory-latency` replaces swappiness150,
watermark125, overcommit0 and bytes; `99-zz-groot-memory` finally replaces
swappiness180, watermark200 and bytes. That predicts byte caps on reload, but
the measured runtime was ratios20/10: file order alone does not prove runtime.
`50-cursor.conf` contains only comments. `30-zram.rules` intentionally retains
swappiness180 against the packaged zram event's150 and disables simultaneous
zswap; it is separately tracked. Dirty byte caps are global, not sdb bandwidth
caps. No SSD `io.max` cap is introduced. Keep scheduler choice separate from
the measured scheduler-independent desktop `io.latency` policy.

The CachyOS defaults are documented at
<https://wiki.cachyos.org/features/cachyos_settings/>; installed vendor files,
not the latest web revision, define this host's package baseline. Kernel
semantics: <https://docs.kernel.org/admin-guide/sysctl/vm.html>.

### Exact privileged stages

Run from the merged `deploy/live` checkout:

```sh
# READ ONLY: names, hashes and package metadata only, never env/credential values.
# Retain locally; no upload. Root removes the explicit UNKNOWN permission gaps.
sudo python3 scripts/apply-host-system --audit
# Separate explicit policy choice; keeps oomd running, removes broad candidates.
python3 scripts/apply-host-system --oomd
sudo python3 scripts/apply-host-system --oomd --apply
python3 scripts/apply-host-system
sudo python3 scripts/apply-host-system --apply
```

Expected sysctl verification: swappiness180, watermark_scale_factor200,
page-cluster0, dirty_bytes268435456, dirty_background_bytes67108864,
overcommit_memory1. The two corresponding dirty ratios should read zero.
Expected oomd verification: `oomctl` prints no `Path:` entries and
`VERIFIED: oomctl monitored set empty`; if any candidate remains the stage
fails rather than claiming protection. Oomd's configured thresholds remain
90% swap, default60%/30s pressure, but apply to **no** cgroup in this stage.
No pressure threshold is invented as a guarantee. This is tested for rendered
files and fake-root idempotence, not a live root-systemd/cgroup/VM test.
Expected earlyoom verification: `VERIFIED: earlyoom active; -m 5 -s 65;
anchored harness/session avoid; no --prefer`. Its TERM gate requires BOTH
available memory below5% (~1.17GiB) and free swap below65% (used above35%,
~8.18GiB with current23.36GiB logical zram). The default KILL gates halve
those free percentages to2.5%/32.5%. Zram uses real RAM, so a large logical
swap size is not a physical reserve. Keep existing capacity and thresholds;
do not infer capacity from them. Earlyoom remains an active **single-process**
killer (no `-g`).
`--avoid` is a preference, not immunity; kernel global OOM remains possible.
T3's observed `node-MainThread` comm is shared by some Node tool workers,
so those workers are also avoided: comm matching is not process identity.
Generic `node`, `python`, `python3`, compiler and llama worker fixtures are
not avoided. Claude/codex were absent from the live census; their exact launch
names are defensively included, not falsely claimed observed. The other
observed broker identity is `omp daemon brok` (Linux comm truncation).

Zram capacity is **unchanged**: logical=ram, resident=ram/2, zstd, priority200.
Only stale safety claims in its comment are corrected. No resize, swapoff,
generator restart or zram reboot step belongs to this deployment. Reconsider
only after measured A/B PSI, failed_writes and OOM counts over at least24h.

The k3s20Gi host reserve is already owned by `scripts/setup-k3s.sh server`.
Run `sudo bash scripts/setup-k3s.sh server` only in a separately approved k3s
maintenance window: it can install/configure and restart the server, unlike
the host installer. Check its printed plan and node Allocatable afterward.
It is not invoked automatically here.

Rollback is receipt-based: restore each saved file/symlink to its same absolute
path; for receipt entries with `existed=false`, remove only that newly installed
file. Restore retired files from the same backup. Then daemon-reload and
sysctl --system. Zram capacity is unchanged. Backups and receipts are never
deleted by this installer.

### Scope and residual risk

The package inventory includes modified, missing and unreadable backup paths.
Account databases (`passwd`, `group`, `shadow`, subuid/subgid), dynamically
generated resolver/mirror lists, credentials and firewall state are **not**
copied into public dotfiles as arbitrary file snapshots. Existing owning
generators/security policy retain those boundaries. The audit emits names and
hashes, not contents. Root-only `/boot`, k3s.service.env and other inaccessible
paths remain UNKNOWN until the read-only sudo audit; absence of access is not
proof of clean configuration. Generated k3s units remain setup-k3s-owned.
The streamed `pacman -Qkk` completed in349.85s (exit1: alterations/unreadable
paths, not a package-clean certificate); `-Qii` found42 modified/missing/
unreadable backup entries. Nine readable `.pacnew` files remain in locale,
mkinitcpio, mirror lists, resolver and TPM profiles. They are inventoried, not
blindly applied or deleted. Neither permission failures nor pending `.pacnew`
reviews are represented as resolved. No `.pacsave` was found in readable
directories. Scope/hashes, package status, full sysctl assignment chains and
measurements are in the tracked audit JSON, without credential values.

Hard caps are ceilings, not reservations: agent10GiB + farm8GiB + ctx5GiB
already equals23GiB against23.36GiB physical RAM, before desktop, kernel,
zram and unbounded system services. The complete census's17 non-overlapping
capped groups sum69.8657GiB, not a reservation: agent10, farm8, ctx5,
app-t3code-agents19.36, kubepods19.36, telemetry2.441, Docker2+0.5,
neuroforge0.75+0.75+0.125, dash0.75, service-watch0.25, ghcache0.25,
identity-warm0.25, earlyoom0.0488 and polkit0.03125GiB. Nested capped
scopes/pods are excluded from that sum; the audit's own transient scope is
excluded. See `config/host/groot-audit-20261024.json` for bytes and paths.
`system.slice`,
background.slice, app.slice, session.slice, t3code, noctalia-shell, hermes-web
and browser/desktop workloads remain unbounded. Global kernel OOM can still
hit the desktop. Removing broad oomd selection prevents that userspace
whole-cgroup kill route, **not all OOMs or individual process kills**.

An opt-in killable-only slice requires a later ownership/placement design:
only disposable worker processes may enter it; harness, MCP, AgentsView,
session and desktop processes must be excluded before enabling any
ManagedOOM=kill threshold. `agent-workloads-v2.scope` currently mixes tool
work with MCP/AgentsView and is not an eligible kill target. This stage does
not implement that migration or falsely mark mixed scopes killable.


### Unified reclaim reserve and victim-selection layers

The single measured budget table is
`config/host/groot-audit-20261024.json` → `host_memory_budget.groups`:
per group, lifetime `MemoryPeak`, current cap, proposed/retained cap and basis.
Do not add hierarchical peaks as simultaneous demand. Session lifetime peak
was6,346,428,416 bytes (5.91GiB). The measured-peak-plus-margin choice is
MemoryMin=MemoryLow=7GiB, replacing the user session's existing4GiB MemoryLow.
The root installer propagates7GiB through user.slice, user-1000.slice and
user@1000.service; UserLayer owns session.slice. Kernel memory.min/low values
are read back after reload; mismatch fails rather than claiming protection.
No manager or desktop restart is used to apply reclaim settings.

The continuous manifest `[budget]` check adopts
`physical RAM - effective session.slice MemoryMin >= largest non-desktop cap`.
With7GiB protected, remaining17,565,974,528 bytes (~16.36GiB) exceeds the
largest proposed finite group10GiB. T3 agents move19.36→4GiB and Kubernetes
19.36→approximately3.36GiB after its explicit20GiB host-reserve maintenance.
The nominal sum still exceeds RAM (~38.5GiB); caps are not reservations and
need not all peak together. Unbounded/missing groups produce UNKNOWN, never a
false pass. The guard is a necessary finite-single-runaway check, **not**
sufficient when other workloads already occupy memory. Hard reclaim
protection does not exempt a process from global OOM victim selection.

Victim selection is separate: earlyoom avoids the anchored harness/session
names; kernel scores still matter independently. Observed live
`oom_score_adj`: user manager100; Hyprland, Xwayland, noctalia(qs), tern,
OMP and Hermes200. Current scores were respectively733,804,802,814,806,812,
814 (gateway); these are changing observations, not static guarantees.
Some preexisting Hermes worker processes also retained200, so desired
agent-launch child800 was not proof that every live child had that rank.
The root user@1000 drop-in stages OOMScoreAdjust=0 for the **next controlled
login/reboot only**. Existing user manager/desktop scores are not rewritten
by this root script and user@1000 is never restarted. UserLayer owns bounded
classifier updates to raise only eligible disposable children; no invalid
OOMScoreAdjust directive is added to a scope (it is service-spawn-only).

Residual risk: unbounded groups and concurrent capped workloads can still
cause global OOM; reclaim protection, earlyoom avoidance and relative
oom_score_adj ranking do not guarantee desktop survival.

### Journal retention

Packaged `00-journal-size.conf` limited the whole journal to50MiB; measured
usage43.5MiB and missing same-day incident records justify a host override.
Tracked `50-groot-retention.conf` sets SystemMaxUse=1G, SystemKeepFree=2G and
MaxRetentionSec=30day. One GiB is below1% of the132GiB root filesystem.
The storage policy targets20GiB root free upstream; the smaller2GiB journald
floor avoids discarding debugging history prematurely during an incident.
Thirty days is a **maximum age**, not guaranteed minimum retention: volume
and the1GiB ceiling may rotate sooner. Residual risk: when `/` falls below
2GiB free, history may still be vacuumed by journald's space policy.
No bulk-disk journal mount or data migration is introduced.

`--apply` restarts only systemd-journald when this file changes, then prints
`journalctl --disk-usage` and `systemd-analyze cat-config systemd/journald.conf`
for verification. The latter must show the later host file with1G/2G/30day.
There is **no** manual journal vacuum operation and no journal deletion.
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

Installer upgrades accept a previous managed link only after recomputing its
complete content/mode-stamped release digest (once per release). This permits
tracked updates without weakening the refusal of arbitrary operator edits.
The five obsolete Dash preview/bridge overrides are explicitly hash-retired
after the PR88 canonical bridge/Metro cutover; their exact live files are backed
up and removed, never reinstalled from the earlier inventory snapshot.

