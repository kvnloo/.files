# Fleet: permanent workers over Tailscale

groot (the desktop) is the controller and the k3s server. Other devices take
work in two lanes:

| Lane | For | How | Isolation |
| --- | --- | --- | --- |
| **k3s** (`factory`, `lanes`, `z0` queues) | untrusted repo work, anything that fits a container | oss-factory `factory submit`, or a Job with `kueue.x-k8s.io/queue-name` | restricted Pod Security, `netpol-ready` gate, egress only to DNS + internet (docs/k3s/ONBOARDING.md) |
| **host** (`fleet run`) | our own builds/tests that need the host toolchain (Gradle/Android, bun, cargo, make, ...) | `scripts/fleet-build -- <cmd>` (default routing) or `scripts/fleet run <node> -- <cmd>` | unprivileged `agentjob` user, capped systemd scope, no LAN/tailnet egress; phones: polite-run |

The registry is `config/fleet/nodes.yaml`. Everything here is idempotent:
re-running a command with the same registry changes nothing.

## Devices (2026-10-20)

| Device | Role | State |
| --- | --- | --- |
| groot (i9-10900KF, 24 GB, RTX 3080 Ti) | k3s server, GPU, controller | online; health report-only; server hardening waits on the owner's sudo |
| mbp (i7-4870HQ 4C/8T, 16 GB, CachyOS) | permanent worker: k3s agent + host lane; **the default build node** | hardened and verified; JDK 17/21, Android SDK (34/35/37.2, build-tools 34/35/37), Bun, Node, Python; NOOP debug APK built there 2026-10-20 |
| omarchy-phone (S25 Ultra, Arch ARM in Omalauncher) | polite worker, host lane only | polite lane installed and verified; k3s cannot run there |
| galaxy-s22plus, alias `s22` (spare S22+, Arch ARM in Omalauncher, guest node `localhost-0`) | polite worker, host lane only, lowest priority | installed and verified 2026-10-20; ssh on 8022; works when charging or >= 50 % |
| cursor, cos | unknown Linux devices | offline; identify, then [add a Linux worker](#adding-a-linux-worker) |
| RTX 2080 Super PC, Oracle Always Free ARM VM | future workers | not on the tailnet |

Full facts: `zer0/data/operations/fleet/inventory-20261020.json`.

## Running work

### Default routing (every agent)

Builds and test suites do **not** run on groot. Use `scripts/fleet-build`
(`~/.local/bin/fleet-build` on groot); the short version for agents is
[BUILDS.md](BUILDS.md).

```sh
cd noop-oura/android && fleet-build --fetch app/build/outputs/apk/full/debug --out /tmp/apk -- ./gradlew assembleFullDebug
fleet-build -- bun test                     # class build -> mbp
fleet-build --light -- python3 -m pytest    # mbp or a phone, 512 MiB
```

- Gradle/Android -> capability `android-build` (mbp; 6 GiB, 4 CPUs, JDK 17, or
  `--jdk 21`). Everything else that builds or tests -> class `build` (mbp).
  Light arm64-safe work -> `--light` (phones allowed).
- groot only for the GPU or a toolchain that exists only there, said explicitly.
  No room (busy, hot, cordoned) -> `fleet-build` retries every 60 s for
  `--wait` seconds (default 1800), then exits 75; never queue it on groot instead.
- `fleet run` on Linux admits a job only when the lane slice's anonymous memory
  leaves room for `--mem` (concurrent builds queue instead of OOM-killing each
  other), and it stops the job's scope afterwards.
- Capabilities (`capabilities:` in the registry) are what a host-lane job finds
  on the node; `fleet run --class X` matches classes or capabilities, and
  `fleet nodes` lists them. `scripts/fleet toolchain <node>` installs the node's
  `toolchains:` (`scripts/fleet-toolchain.sh`: Temurin JDK 17/21 and Bun pinned by
  sha256 in `/opt/fleet`, Android SDK with cmdline-tools pinned by Google's sha1 in
  `/opt/android-sdk`, plus Corepack/pnpm and root-owned Rust as described below).
  `/etc/fleet/toolchain.env` is sourced by every Linux job. Toolchain requirements
  in the registry are desired state, not proof of a live installation. Gradle
  caches stay in `/home/agentjob/.gradle`; the job's scope is stopped at the end,
  so Gradle/Kotlin daemons never outlive it.

### `fleet run`

```sh
scripts/fleet nodes                                  # registry + live load/memory/power
scripts/fleet run mbp -- uname -a                    # on a named node
scripts/fleet run -- make test                       # least-loaded eligible node, ships the cwd's git files
scripts/fleet run --class build --mem 3G --cpus 4 --fetch src/dist -- make release
scripts/fleet run --arch arm64 --tolerate phone -- make test   # allow the phone
scripts/fleet kill mbp <job-id>
```

- **Source**: by default `fleet run` sends the current directory. In a git
  worktree it sends tracked and untracked-but-not-ignored files (`git ls-files
  -co --exclude-standard`), so `.git`, build output and ignored files stay
  home. `--src DIR` picks another directory; `--no-src` sends nothing.
  `--git` opts into a fresh remote repository and tracked-file index for checks
  that call Git (also accepted by `fleet-build`). It does **not** copy the original
  `.git`, history, remotes, hooks, credentials, branch or HEAD identity. It is a
  current-tree fixture, not a historical checkout; tracked and untracked source
  paths retain that distinction. History-sensitive checks need a separate,
  explicitly reviewed source strategy. Without `--git`, no Git metadata is sent.
  A local archive failure must abort transfer, not run checks on a partial tree;
  live PR #41 head `62e5db9` resolved the reported CUA job
  `20261022-224002-24a1` source-transfer failure. That live change is separate from
  this branch's opt-in metadata work.
- **Placement**: candidates are nodes with a host lane, the asked class/arch,
  tolerated taints, not cordoned and not paused by `fleet health`. Each is
  probed live; a node qualifies only when `MemAvailable >= mem_floor + --mem`.
  The lowest `load1 / cpus` wins; phones get a +1 penalty so they only take
  work when the Linux workers are full. The remote side re-checks the floor
  right before starting (exit 75 = "no room, retry later").
- **Limits (Linux)**: the job runs as `agentjob` in
  `systemd-run --user --scope` with `MemoryMax=--mem`, `MemorySwapMax=512M`,
  `CPUQuota=--cpus` and `timeout`. The whole `agentjob` user slice is capped
  root-side (mbp: 7 GiB, 400 % CPU, 4096 tasks) and cannot reach 10/8,
  172.16/12, 192.168/16, 100.64/10 (tailnet), link-local or ULA addresses.
  Internet works. Crossing the memory cap can cause a scoped OOM kill, but exit
  137 alone only indicates a SIGKILL-shaped termination, not its cause.
- **Results**: output streams back and is saved to
  `~/.local/state/fleet/runs/<job-id>-<node>.log`; `--fetch PATH` (relative to
  the job dir, e.g. `src/dist`) copies files back to
  `~/.local/state/fleet/runs/<job-id>/`. The remote job dir is deleted unless
  `--keep`. Exit code = the job's exit code (75 admission hold/drained, 124 timeout;
  137 requires supporting memory evidence before it is called an OOM).
- **Trust**: the host lane is for the owner's own agents' code. Anything from
  an unknown repo goes through the k3s `factory` queue.

## Job classes (k3s)

`scripts/fleet labels` writes `z0.dev/class-{cpu-heavy,build,render}=true|false`
on every node from the registry, and taints groot
`z0.dev/host=interactive:PreferNoSchedule`. The per-node Kueue flavors carry the
same labels, so a queued Job with `nodeSelector: {z0.dev/class-render: "true"}`
goes to mbp, as does `class-build`; only genuine NVIDIA GPU resource allocation permits heavyweight groot placement
(`config/k3s/smoke/class-job.yaml` proves both). A dedicated node (for example a
future render box) gets a `NoSchedule` taint in the registry, and only Jobs that
tolerate it land there.

## Health

`scripts/fleet health` (a user timer on groot every 2 minutes, installed with
`scripts/fleet install-timer`) probes every node with `fleet-node-probe` and
judges it on groot:

- tailnet reachable (the probe crossing the tailnet counts), k8s `Ready` and no
  Memory/Disk/PID pressure
- `MemAvailable` and free disk (root, k3s data dir, lane home) above the
  registry thresholds; temperature under 95 C
- `k3s-agent`/`k3s`, `tailscaled`, `sshd` active
- laptops: not on battery under 40 %; phones: battery >= 50 % or charging,
  battery <= 40 C, Android thermal status <= 1
- not in maintenance (`/var/lib/fleet/maintenance`)

After 2 bad checks in a row a `cordon` node is cordoned and annotated
`z0.dev/cordoned-by=fleet-health` with the reason; after 2 good checks it is
uncordoned. A node someone cordoned by hand is never uncordoned. groot is
report-only (it hosts the control plane, Kueue and the factory gateway). Phones
are `pause`d: `fleet run` skips them. Reports: `~/.local/state/fleet/health/<node>.json`
and `history.jsonl` (bounded). Warnings (pending updates, reboot needed) do not cordon.

### Cluster steward: branch proposal and evidence limits

The steward reuses fleet run logs and health history; it is not another scheduler.
The branch adds a dry-run analysis hook to the existing `fleet health` path.
An explicit observation-only invocation is:

```sh
scripts/fleet health --dry-run --steward
# Or scope the health observation:
scripts/fleet health --node mbp --dry-run --steward
```

The hook calls `scripts/fleet-steward` with the selected fleet state directory,
its `registry.json` snapshot, and `--dry-run`. Outputs live under
`${FLEET_STATE:-~/.local/state/fleet}/steward/`: `ledger.jsonl`, `findings.json`,
`parameters.json`, `lessons.json` (full envelope), `lessons.jsonl` (candidates),
`capacity.json`, and `report.md`. Dry-run
allows local report files, not cluster changes or cache deletion. Only the fixed
agentjob UV/npm/Bun/Go-build cache paths on MBP are eligible for an explicitly
applied, fresh-low-disk cleanup; no owner directories or sudo actions are automatic.

New run records carry `# steward ` JSON metadata alongside the legacy
`# fleet job ...` and `# exit ...` lines. `fleet-build` exports epoch-seconds
`FLEET_QUEUED_TS` and an opaque `FLEET_ATTEMPT_ID` once before its retry loop.
Every admission retry shares them, including when values came from a caller.
Queue wait is not reset at each retry. These fields add evidence, not another
queue or global lock. A non-admission exit (for example exit 1) still ends the
wrapper; `--wait 1800` is an admission window, not a promise to replay failed jobs.
An allocated job that returns 75 is not blindly replayed.

Historical logs often have no source identity, memory limit, peak, queue entry,
or completion timestamp. Those fields remain **null with provenance**. The
timestamp in a legacy job ID is local time; a log's mtime is not runtime.
Never execute log content to reconstruct a result.

| Evidence read on 2026-10-22 | Interpretation and proposal |
| --- | --- |
| `20261022-205911-3b11-mbp.log`: Omnara frontend exits 127, `corepack: command not found` | **Confirmed missing command in that run.** Propose Corepack/pnpm provisioning below; registry entries alone do not repair MBP. |
| `20261020-170927-9192-mbp.log`: synthetic Python allocation, 512 MiB scope, exit 137 | Cap exercise, **not a production repository's memory requirement**; no repo budget learned. |
| `20261020-171304-677a-omarchy-phone.log`: synthetic allocation, explicit RSS drain above 256 MiB, exit 137 | Confirms that phone guard's drain report, not any build's budget. |
| `20261020-234206-c24d-mbp.log`: NOOP Android, 2048 MiB scope, exit 143 | Repository identified from Gradle tasks/tests, but **not confirmed OOM**. |
| `20261020-235612-838b-mbp.log`: NOOP Android succeeds with in-process Kotlin and a 3 GiB JVM heap | Success is confirmed; total budget/peak is absent. **Candidate**: shell-wrapped builds run from NOOP's `android/` subtree use the existing 6 GiB Android envelope rather than generic 3 GiB. |
| `20261021-014404-a7c5-mbp.log`: lane has 7165 MiB left for a 7168 MiB request | Do not default to the entire 7 GiB lane: even small resident overhead can hold it. The lane cap stays 7 GiB. |
| `20261022-220746-b01f-mbp.log`: OMP pii-redact/typecheck workflow, explicit timeout 900 s, exit 143 | Termination is observed, but this is **not GEV full npm-test evidence**. Do not invent a repo-wide runtime default or call it OOM. |

The NOOP candidate matches the canonical `remote.origin.url` repository name,
not a worktree directory name. It changes only build-mode defaults inside
`android/`; other NOOP builds and unknown repos remain 3 GiB, light jobs 512 MiB,
and direct Gradle/`--android` jobs 6 GiB. Explicit `--mem` always wins. Lawnchair
keeps its existing Android envelope; no blanket increase or adaptive retry on
exit 137 is added. New peak/cgroup evidence is needed to confirm any budget.

### PROPOSE only: worker toolchains and existing timer cutover

No commands in this proposal were applied by the steward. On MBP, from the
reviewed checkout, the exact privileged provisioning command is:

```sh
# PROPOSE ONLY — owner runs on MBP after review, not on groot:
sudo bash scripts/fleet-toolchain.sh install corepack pnpm rust
```

Corepack 0.33.0 and pnpm 10.11.0 use separate root-owned `/opt/fleet/<name>`
prefixes, so Corepack's bundled pnpm shim cannot overwrite the standalone tool.
Existing commands are retained. Missing Node/npm prerequisites use the existing
distro pattern (`pacman -S --needed --noconfirm nodejs npm`, or
`apt-get install -y nodejs npm`, or `dnf/yum install -y nodejs npm`), without a
database refresh or full OS upgrade. npm installs use `--ignore-scripts` and
`--engine-strict`; unsupported installed Node versions fail rather than bypassing
engine requirements. Project `packageManager` pins remain the project's choice.
Version metadata: [Corepack](https://registry.npmjs.org/corepack/0.33.0),
[pnpm](https://registry.npmjs.org/pnpm/10.11.0).

Rust uses only trusted distro `/usr/bin/rustup` to install a stable/minimal
toolchain in root-owned `/opt/fleet/rust`; controlled installer state stays
there, not in an owner's or agentjob's home. `/opt/fleet/rust/current` exposes
the actual toolchain binaries, not rustup proxies. Both `cargo` and `rustc`
must exist and report their versions before installation/check succeeds.
Jobs receive that read-only compiler bin directory and writable
`CARGO_HOME=$HOME/.cargo` for their own dependency caches. Existing healthy
managed installs are retained; this does not automatically honor project
`rust-toolchain.toml` overrides or upgrade to another compiler. A different
required compiler needs an owner-reviewed toolchain change. The installer does
not expose `/home/kvn/.cargo/bin`, change home permissions, grant sudo access,
or execute any agentjob-owned rustup program as root.

The actual existing timer is a **user** timer under
`~/.config/systemd/user`, every 2 minutes. Its service and
`50-admission-owner.conf` currently point at
`/mnt/zer0models/worktrees/files-desktop-cpu-admission/scripts/fleet health`.
There is no system `fleet-health.service`/timer. This isolated branch is not
the active timer checkout. After review, the owner can stop the existing user
timer, merge the reviewed changes into its live checkout, then start the same
timer; do not install a second timer or point a live unit at this draft worktree.

```sh
# PROPOSE ONLY — owner-controlled cutover on groot; no sudo required:
systemctl --user stop fleet-health.timer
git -C /mnt/zer0models/worktrees/files-desktop-cpu-admission merge --no-ff feat/fleet-cluster-steward-20261022
systemctl --user start fleet-health.timer
```

### Cooperative MBP quiet windows and validation plan

Observed contention (load 13.6/8 and an almost-full 7 GiB lane) is an environment
constraint, not a reason to loosen timing assertions. Operators on groot
temporarily cooperate through the same lock:

```sh
# Normal exact-head job; request the smallest real envelope:
flock -s /tmp/mbp-quiet.lock /home/kvn/.local/bin/fleet-build --wait 0 --mem 512M --cpus 1 -- python3 -m unittest discover -s tests -p 'test_fleet*.py'
# Timing-sensitive or large-memory exact-head gate; hold it <=20 minutes:
flock -x -w 3600 /tmp/mbp-quiet.lock /home/kvn/.local/bin/fleet-build --wait 0 --mem 512M --cpus 1 --timeout 1200 -- python3 -m unittest discover -s tests -p 'test_fleet*.py'
```

Choose one validation command above, not two concurrent runs. Run one job
per lead; after an admission exit 75, wait at least 5 minutes before resubmitting.
These are operator-chosen wrappers, not a new automatic global lock in fleet.
Longer-term reservation/priority and fairness belong in the existing Kueue lanes
and workload repository, with their reviewed schema and capacity owner—not a
second host scheduler or fabricated capacity model.

Focused wrapper/toolchain tests use temporary fixtures and fake dispatchers.
They do not install tools or run builds. Certify the exact integrated head once.
Keep command output with the review receipt. A loaded-host timeout is environment
evidence, not permission to relax a test deadline.


### PROPOSE only: ranked OSS follow-through

All four research artifacts have arrived:
[Z01-K8S-OSS](https://github.com/kvnloo/z0intelligence/issues/131#issuecomment-6356877382),
[Z01-K8S-LEARN](https://github.com/kvnloo/z0intelligence/issues/131#issuecomment-6356843385),
[Z01-K8S-MIGRATE](https://github.com/kvnloo/z0intelligence/issues/131#issuecomment-6356821555),
and [Z01-K8S-STEWARD](https://github.com/kvnloo/z0intelligence/issues/131#issuecomment-6356895926).
These are research proposals, not deployment receipts. The OSS ranking is:

1. **Existing kubelet/Btrfs physical accounting first.** Inspect effective
   drop-ins, mounts, free bytes and inodes. The 2% minimum-reclaim setting is
   already in the #41 source and reported applied; do not claim it as a new fix.
   Pressure clearance still depends on effective thresholds and hysteresis.
2. **Existing health diagnostics next.** Keep sensor provenance and the owner's
   MBP `max_temp_c: 110` policy. STEWARD/MIGRATE's older 95 C admission proposals
   are stale and explicitly rejected; a diagnostic warning at 95 C must not
   override current admission or add a new automatic hold/taint.
3. **Reconcile installed Kueue budgets with actual host use.** The host lane's
   aggregate 7 GiB/4 CPU slice and pods share physical resources; queue quotas
   are not independent extra capacity. Reservations/fair sharing belong in the
   existing workload repository after installed-CRD review. Kueue does not
   schedule host-lane requests. No new scheduler, preemption, or groot CPU
   fallback is proposed.
4. **Defer scoped kube-state-metrics** until a scrape/history sink and IO/resource
   headroom are qualified. Limit any future pilot to nodes/pods/jobs/namespaces;
   research sizing is not measured capacity or repair authority.
5. **Defer a single-node VictoriaMetrics pilot** until storage/IO headroom is
   proven. Prefer its built-in scraper; do not add an operator/vmagent stack.
   If no safe storage exists, retain existing fleet histories. Scraping agents
   without a remote receiver are not local query storage.

This is a Draft-PR documentation fold-in, **not a workload deployment**.
Android, phones, GUI work and persistent sessions remain on their existing host
lanes; no Kubernetes migration is implied.

### Historical health exercise (prior PR)

```sh
scripts/fleet health --node mbp --strikes 1 --set min_disk_free_gb=100000   # BAD ... action=cordoned
kubectl get node mbp                                                       # Ready,SchedulingDisabled
scripts/fleet health --node mbp --strikes 1                                # OK ... action=uncordoned
```

## Node hardening (`scripts/fleet-harden.sh`)

`scripts/fleet enroll <node>` copies the scripts to `/opt/dotfiles-k3s` on the
node over root ssh and runs `fleet-harden.sh worker` with the registry's
values, then `fleet-toolchain.sh install <toolchains>` when the node lists any. Each file is written only when it changes; services reload only when
their file changed; nothing reboots. `fleet-harden.sh plan worker|server`
renders everything into a temp dir without root.

| Area | Worker setting | Why |
| --- | --- | --- |
| journald | persistent, `SystemMaxUse=500M`, `SystemKeepFree=2G`, 1 month | logs survive reboots, never fill the disk |
| sshd | key-only, `PermitRootLogin prohibit-password`, `MaxAuthTries 3`, `LoginGraceTime 20`; agentjob: keys in root-owned `/etc/ssh/fleet_authorized_keys/agentjob` with `from="<groot>",restrict`, no TTY/forwarding | a job cannot add keys or open tunnels |
| ufw | incoming deny; `2222/tcp` on tailscale0 **from groot only**; k3s 10250/8472 on tailscale0 | LAN sees nothing; the tailnet sees only k3s ports |
| fail2ban | **not installed** | password auth is off and 2222 accepts only groot's address, so there is nothing to brute-force; a ban list could only lock groot's agents out |
| k3s | `Restart=always`, no start limit, `OOMScoreAdjust=-900`; kubelet `system-reserved`, `kube-reserved`, `eviction-hard memory.available<1Gi,nodefs<10%,imagefs<10%`, `eviction-soft 1536Mi/1m` via `/etc/rancher/k3s/config.yaml.d/50-fleet.yaml` | pods together are capped below RAM (mbp allocatable 14.0 -> 11.5 GiB) and evicted before the host starves |
| logind (laptops) | lid close on AC does nothing | a closed laptop keeps working; on battery the default applies and health cordons it under 40 % |
| agentjob | own user, home 0700, no groups (not docker/wheel), password locked, lingering user manager, slice caps + IP deny | host jobs cannot see the owner's files, docker or sudo |
| updates | `fleet-updates.timer` daily: `checkupdates -d` downloads, writes `/var/lib/fleet/updates.json` | see below |

### Updates policy (CachyOS/Arch)

Arch has no security-only channel and an unattended `pacman -Syu` can break a
node (manual interventions, partial kernel/module states), so updates are
**downloaded automatically and applied on purpose**:

1. Daily, the node downloads pending packages into its cache and records counts
   (`pending`, `kernel_pending`, `core_pending` for openssh/openssl/glibc/sudo/
   systemd/tailscale, `reboot_required`). `fleet health` shows them as warnings.
2. `scripts/fleet update mbp` shows them; `scripts/fleet update mbp --apply`
   cordons and drains the node, runs `pacman -Syu --noconfirm`, and uncordons
   only if it succeeded. It never reboots; after a kernel update health warns
   `reboot required` until the owner reboots.
3. Apply at least weekly, and the same day when `core_pending > 0`.

### groot (server)

Needs the owner's sudo, once (it restarts the k3s server, a short API blip;
pods keep running):

```sh
cd /workspace/.files-k3s
sudo scripts/fleet-harden.sh server --restart-k3s \
  --kubelet-arg system-reserved=cpu=2,memory=4Gi --kubelet-arg kube-reserved=cpu=1,memory=1Gi \
  --kubelet-arg 'eviction-hard=memory.available<1Gi,nodefs.available<10%,imagefs.available<10%' \
  --kubelet-arg 'eviction-soft=memory.available<1536Mi' --kubelet-arg eviction-soft-grace-period=memory.available=2m
```

It sets journald, key-only sshd (only because `~/.ssh/authorized_keys` exists;
console login is unaffected), the k3s unit drop-in, kubelet reservations,
the update report and the k3s firewall ports. It does not touch groot's port 22
exposure or anything else on the desktop.

## Adding a Linux worker

For the RTX 2080 Super PC, the Oracle VM, and cursor/cos once identified:

1. On the device: install Linux (CachyOS, or Ubuntu 24.04 arm64 on Oracle), then
   `tailscale up` (Oracle: `--advertise-tags=tag:worker`), and `ufw enable` with
   `ufw allow in on tailscale0 to any port 22 proto tcp` if you use Tailscale SSH.
2. From groot, prove access: `ssh root@<tailnet-ip> true` (Tailscale SSH; approve
   the check URL once) or put groot's key in `/root/.ssh/authorized_keys`.
3. Add the node under `nodes:` in `config/fleet/nodes.yaml` (copy mbp; set
   `tailnet_ip`, `ssh_port: 22` for the first enroll, `arch`, `classes`,
   `capabilities`/`toolchains` if it should build, kubelet reservations sized
   to its RAM) and a `node-<name>` flavor in
   `config/k3s/kueue/queues.yaml`.
4. Join k3s (docs/k3s/ONBOARDING.md "Joining an agent"), then from groot:
   ```sh
   scripts/fleet enroll <name> --port 22     # hardening; opens 2222 for groot
   # set ssh_port: 2222 in the registry
   scripts/setup-k3s.sh admit <name>         # isolation proof, untaints
   scripts/fleet labels && scripts/setup-k3s.sh kueue
   scripts/fleet health --node <name> && scripts/fleet run <name> -- uname -a
   ```
5. GPU box: `sudo scripts/setup-k3s.sh gpu` on it, label `z0.dev/gpu=<model>`,
   add `render` to its classes.

Oracle notes: arm64, so container images must be multi-arch; open nothing in
the Oracle security list (tailnet only); the VM is reclaimed when idle, so keep
the `fleet-updates` timer and a cheap k3s workload on it.

## Phones

Phones run the host lane only. The S25's Linux guest (`omarchy-phone`) is
Arch Linux ARM inside Omalauncher (`dev.omalauncher`), started through PRoot
without Android root. k3s cannot run there: no cgroup v2 mount, netlink is
denied (iptables/nft fail), no systemd. So the phone gets `scripts/fleet-polite-run`:

- the job runs under `nice 19`, `ionice idle`, `taskset` cores 0-3 (half the
  phone), in `~/fleet-jobs/<id>`, with `HOME`/`TMPDIR` pointed there
- gate before start and every 30 s: battery >= 50 % or charging, battery <= 40 C,
  Android thermal status <= 1, `MemAvailable >= 1200 MiB`, no
  `~/.config/fleet/pause` file. Battery and thermal come from read-only
  `adb shell dumpsys battery|thermalservice` over the guest's wireless-debugging
  link to its own phone (the guest cannot read `/sys/class/power_supply`); if adb
  is unreadable the gate fails closed
- PRoot traces every process, so `SIGSTOP` does not pause a job (tested). Two
  failed gates in a row **drain** the job (TERM, then KILL; exit 75); it is
  killed when its process group passes `--mem` RSS (default 1 GiB, max 2 GiB)
  or the phone drops under 800 MiB available
- Tern, its daemon and remote serve are not touched and keep running. Android
  apps and settings are not touched. Jobs in the guest run as the Omalauncher
  app's uid and can read the guest's `/root`, so only the owner's own work goes
  there; it is tainted `phone` and needs `--tolerate phone` or `--node`.
- Owner switch: `touch ~/.config/fleet/pause` in the guest stops phone work
  (running jobs drain within a minute); `rm` it to resume.

If Android restarts wireless debugging, its port changes and the gate closes
(battery unreadable). Re-pair: in the guest `adb connect <android-tailnet-ip>:<new port>`,
then `scripts/fleet enroll omarchy-phone` to re-pin the device.

### Galaxy S22+ (`galaxy-s22plus`, alias `s22`)

The spare S22+ (SM-S906U1) runs the same polite lane as the S25. Differences:

- Its guest is the tailnet node `localhost-0` (100.97.11.22); the Android
  Tailscale app node `galaxy-s22` (100.72.191.23) is the same phone. There is no
  Tailscale SSH in this guest: groot reaches it with key-only OpenSSH on port 8022
  (`ssh s22`; the host key is pinned in groot's `~/.ssh/known_hosts`). The
  registry says `ssh_port: 8022`.
- Omalauncher ships Tern 0.9.5 at `/opt/tern/tern/tern` and launches it
  directly, so the S25's `~/.local/bin/tern` wrapper (which starts tailscaled,
  sshd, the daemon and remote serve on the S25) does not apply. The clone script
  copies only the S25's start helpers and the peer-credential shim, and installs
  the supervisor below.
- Jobs get cpus 0-3, the four small cores.

Rebuild or repair it from groot (idempotent):

```sh
scripts/fleet-phone-clone.sh root@100.104.42.85 root@100.97.11.22 --port 8022 --model SM-S906U1
scripts/fleet nodes && scripts/fleet health --node s22
scripts/fleet run s22 --tolerate phone --no-src -- uname -a   # exit 75 + reason while the guard is closed
```

Verified 2026-10-20:
- `fleet nodes` lists `galaxy-s22plus`.
- `fleet run s22 ... uname -a` was refused with `battery 35% and not charging` (exit 75).
- With the pause file, the run was refused with `paused by ~/.config/fleet/pause`.
- In a drill, a running polite-run job drained 64 s after `touch ~/.config/fleet/pause`
  (the drill used a temporary copy with the battery floor lowered to 30 %).

### Service supervision on phones without systemd

The guest has no systemd (so Tern's own `tern remote install --user`, a systemd
user unit with `Restart=on-failure`, cannot work there), and PRoot kills every
process a session started when that session's PRoot exits (`--kill-on-exit`).
`setsid`, `nohup` and double forks do not escape it: tested on the S22+, all
three stayed traced by the window's PRoot and died when its Recents card was
swiped away. So supervision has to live in the longest-lived session
Omalauncher has, and restarts have to be event-driven, not polled.

That session is Omalauncher's PulseAudio PRoot (`AudioBridge.kt`): the launcher
starts `pulseaudio` as soon as Linux is up, with the screen on or off and no
window open, and restarts it whenever it exits. Its PATH puts `/usr/local/bin`
first, so `scripts/fleet-phone-keepalive.sh` installs:

- `/usr/local/bin/pulseaudio` (`config/fleet/phone/pulseaudio-hook`): runs
  `fleet-phone-supervise up --adopt` detached, then execs `/usr/bin/pulseaudio`.
- `~/.local/bin/fleet-phone-supervise` (`scripts/`): the supervisor, busybox
  runit (`pacman -S busybox`; Arch has no s6/runit/dinit packages). One `runsv`
  per service in `~/.local/share/fleet/sv/<service>` (`config/fleet/phone/sv/`),
  services in the foreground: `tailscaled` (userspace networking), `sshd -D -e`,
  `tern remote serve --user --no-iroh` (with the peer-credential shim). runsv
  restarts a service the moment it exits (`wait4`; runsv wakes once an hour,
  svlogd every ~45 min, the supervisor never). `./finish` restarts at once
  unless a service dies three times in a row within 30 s of starting, then backs
  off 1, 2, 4 ... 60 s. The supervisor waits on its runsvs with `wait -n` and
  restarts one that dies. `up --adopt` from the PulseAudio session takes over a
  supervisor that started in a shorter-lived session (a login shell).
- Services started some other way (Tern's S25 wrapper, by hand) are adopted,
  not killed: the run script blocks on the old pid (util-linux `waitpid`, a
  pidfd) and starts its own the moment it exits. Installing never restarts
  anything.
- `tailscaled` gets two extra guards, both found on the S22+: its startup can
  block forever in a netlink `recvfrom` (`netmon.New` -> `syscall.NetlinkRIB`;
  Android), so the run script kills it if its socket is not there in 20 s and
  runsv starts it again; and it can wedge on SIGTERM under PRoot, so the run
  shell stays its parent, turns runsv's TERM into a KILL after 5 s, and
  `setpriv --pdeathsig KILL` takes it down if that shell dies. Restart it with
  `busybox sv restart ~/.local/share/fleet/sv/tailscaled`, never `kill <pid>`.
- `/etc/profile.d/zz-fleet-autostart.sh`: login shells run `up` only when no
  supervisor runs (the next PulseAudio start moves it into the audio session).

Commands (in the guest): `fleet-phone-supervise status|up|down`,
`busybox sv status|restart|down|up ~/.local/share/fleet/sv/<service>`. Logs:
`~/.local/state/fleet/supervise/{log,events}` (supervisor and every exit with its
restart delay), `~/.local/state/fleet/log/{sshd,tailscaled}/current` (svlogd,
2 x 256 KiB), `~/.local/state/tern-remote/service.log`. Off switch:
`touch ~/.config/fleet/no-autostart`. The old 60 s watcher
(`fleet-phone-autostart --watch`) is gone; the installer stops and removes it.

Measured on the S22+ (2026-10-20, 10-minute idle windows, `/proc/<pid>/stat`):

| | old 60 s watcher | runit supervisor |
| --- | --- | --- |
| keep-alive CPU | 2.78 s per 10 min in the watcher tree, plus about the same again in its PRoot tracer (~0.42 s CPU per check, measured over 10 checks) | 0 ms: supervisor and 3 runsv 0 ctx switches; svlogd 10 ms |
| wakeups | 1218 ctx switches per 10 min, ~20 execs per minute | 0 (runsv: 1 per hour) |
| restart after a kill | next tick, up to 60 s (28 s measured) | sshd 0.2-0.4 s, `tern remote serve` 0.4-0.5 s (listening); tailscaled process 0.2 s, backend Running 2-4 s |
| launching window swiped away | services in that window died; back at the next tick if a watcher survived elsewhere | pids unchanged (supervisor in the audio session) |

IDLE_WHOLE_APP_PLACEHOLDER

### Keep-alive: what kills the guest, and what stops it

Omalauncher holds its Linux guest in one app process with a `specialUse`
foreground service (`LinuxService`, the "Linux session running"
notification). The service is `START_NOT_STICKY`, and only the app's
`MainActivity` starts Linux. So once Android kills the process, the guest stays
down until the app is opened again. Every guest process lives inside the PRoot
of the window that started it (`--kill-on-exit`).

The S25's `dumpsys activity exit-info dev.omalauncher` (Oct 11-20) shows what
killed it:

| Cause | Seen | Countermeasure |
| --- | --- | --- |
| `LOW_MEMORY` (lmkd), even while the service runs (importance 125) | 6x | none from adb: no root, so the app's oom score cannot change. Keep the guest's memory down. App fix below |
| `REMOVE TASK`: card swiped out of Recents | 1x | Recents card > **Lock** (Samsung "keep open"). Swiping a Linux *window* card also closes that window and kills every service it started |
| Samsung `AL_Kill : over 1 slots` while cached | 1x | foreground service plus the Doze/background whitelist below |
| `PACKAGE UPDATED` (APK reinstall) | 8x | expected. Reopen the app afterwards |
| Doze/app standby cutting network for the app uid | S22+ was not whitelisted | `deviceidle` whitelist (the uid now sits in netpolicy's power-save allowlist) |
| Android 12+ phantom-process killer (a cap of 32 child processes per app; every guest process counts) | S22+ had it on (default) | `settings_enable_monitor_phantom_procs=false`, `max_phantom_processes=2147483647` |

`scripts/fleet-phone-keepalive.sh root@<guest-ip> [--port N]` runs on groot and
is idempotent. `fleet-phone-clone.sh` calls it too. It installs:

- **Android side** (`scripts/fleet-phone-android-harden`, through the guest's
  own adb, or from groot with `-s ip:port`). For `dev.omalauncher` and
  `com.tailscale.ipn`: `deviceidle` user whitelist,
  appops `RUN_ANY_IN_BACKGROUND`/`RUN_IN_BACKGROUND` allow, standby bucket
  `active` if lower. Phone-wide: the phantom-process killer off. Each change
  records its undo command first. `... status` shows the current state; `... undo`
  restores the originals. Undo files (original values) are in
  `~/.local/state/fleet/android-harden/<model>-<serial>.undo.sh` on groot
  (S25: `SM-S938U-R5CY93G2WNH`, S22+: `SM-S906U1-RFCTA1RZAQY`, also in the
  S22+ guest). Run with `ADB_SERIAL=<current ip:port> sh <file>`.
- **Guest side**: the runit supervisor and the PulseAudio hook (see Service
  supervision above).
- **Health** (`fleet health`, groot timer every 2 min). On phones, the probe reports
  `services` = tailscaled / sshd / tern-remote / fleet-supervise (pidfiles and
  /proc, no systemd; `comm`, not `exe`, since another PRoot session sees every
  exe as proot's loader) and `supervisor_session` (a warning unless `audio`). groot adds `tern remote doctor <user>@<ip>`, and, when
  groot's adb reaches the phone (`android.adb_host`), whether Omalauncher's
  service is up and whether the screen is on. Any of these down makes the node
  BAD. Log: `~/.local/state/fleet/health/phone-keepalive.jsonl` (bounded).
  `android.revive: true` (off by default) reopens Omalauncher only when the guest
  is truly down: the ssh probe failed, `tern remote doctor` failed, and the
  app's foreground service is gone; only while the screen is off, at most every
  15 min. Linux startup runs the PulseAudio hook, so the services come back
  without any window. Restarting a dead service is the guest supervisor's job.

Verified 2026-10-20:
- S22+ (supervisor, 19:06-19:33): see the table above. Installing adopted the
  running sshd/tailscaled/remote serve without restarting them; the first kill
  of each handed over in 0.2-2 s. Killing the window that ran the escape test
  left the supervisor and all service pids unchanged.
- S22+ caveat found while testing: tailscaled restarts sometimes hung in
  netlink before opening its socket (tailnet down ~19:08-19:13 and ~19:23-19:27
  while testing; Omalauncher itself was not frozen: `procState=4`, oom adj 200,
  `isFrozen=false`, `LinuxService isForeground=true` with Settings in front). The
  start watchdog now retries those; 6 forced restarts in a row all came back.
- S25 (owner using it): installed only; all three running services adopted,
  supervisor in the audio session, no service restarted. No kill tests there.
- S22+: Doze forced with `force-idle` while the screen was off
  (18:24:10-18:25:02, then someone woke the screen). ssh, the same sshd/serve
  pids and `tern remote doctor` auth stayed ok. Service pids were unchanged
  through 18:30.
- `dumpsys netpolicy`: both apps' uids are in the power-save allowlist (S22+
  10339, S25 10756).
- S25 not Doze-tested: the owner was using it.

Owner steps (adb cannot do these):
1. Recents: lock the Omalauncher card. Swiping a Linux window card no longer
   matters for the services (they live in the PulseAudio session); swiping the
   launcher itself kills the app process and everything with it.
2. Settings > Battery > Background usage limits > **Never sleeping apps**: add
   Omalauncher and Tailscale (Samsung's own list).
3. After the app is killed (update, low memory), open Omalauncher once; Linux
   start runs the hook, no Terminal tile needed. The real fix is in the app:
   branch `feat/keep-linux-running` on `kvnloo/omalauncher` (a sticky
   `LinuxService` that relaunches Linux, a boot receiver, and a
   `~/.config/omalauncher/session` script supervised like PulseAudio, all behind
   `~/.config/omalauncher/keep-running`). Draft upstream PR text:
   `docs/fleet/omalauncher-keep-running-pr.md`.

Freezer: Android's cached-apps freezer (`use_freezer=true`,
`freezer_cutoff_adj=850`) only freezes cached processes. Omalauncher runs at
oom adj 200 with its foreground service, so it is never frozen while
`LinuxService isForeground=true`; nothing was changed. If the service is ever
lost, the app becomes cached (freezable and killable) and only reopening it
helps; disabling the freezer phone-wide would not keep Linux alive.

### Setting up another phone like the S25

1. Install Omalauncher (`kvnloo/omalauncher`, app id `dev.omalauncher`) and let it
   create its Arch Linux ARM guest. Turn on Tailscale inside the guest (its own
   userspace node) and keep the Android Tailscale app signed in.
2. Let groot in: append groot's `~/.ssh/id_ed25519.pub` to the guest's
   `/root/.ssh/authorized_keys` and run `sshd` there (port 8022 if 22 is taken).
3. Battery access: Android Settings -> Developer options -> Wireless debugging ->
   Pair device with pairing code; in the guest `adb pair <IP:port> <code>`, then
   `adb connect <IP:port on the Wireless debugging screen>`; `adb devices` must
   list it as `device`.
4. From groot: `pacman -S --needed python` in the guest if missing, then
   `scripts/fleet-phone-clone.sh root@100.104.42.85 root@<guest-ip> --port <port> --model <model>`.
   Add the phone under `nodes:` (copy `galaxy-s22plus`).

## Tailscale SSH

`fleet` uses key-only OpenSSH on 2222 and does not depend on Tailscale SSH.
Interactive `ssh root@mbp` on :22 still uses Tailscale SSH `check` mode, which
expires every 12 h. The ACL change that fixes this properly is in
`zer0/data/operations/fleet/tailscale-acl-proposal.md` (owner edit).

## Rollback

- Host lane on a node: `userdel -r agentjob; rm -r /etc/ssh/fleet_authorized_keys /etc/systemd/system/user-1001.slice.d`.
- Any hardening file: delete it (`/etc/systemd/journald.conf.d/50-fleet.conf`,
  `/etc/rancher/k3s/config.yaml.d/50-fleet.yaml`, `/etc/systemd/system/k3s-agent.service.d/50-fleet.conf`,
  `/etc/systemd/logind.conf.d/50-fleet-worker.conf`, `fleet-updates.{service,timer}`),
  `systemctl daemon-reload`, restart the matching service.
- Health timer: `systemctl --user disable --now fleet-health.timer`.
- Phone lane: `rm -r ~/.local/lib/fleet ~/.config/fleet ~/fleet-jobs` in the guest.
