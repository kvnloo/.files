# Fleet: permanent workers over Tailscale

groot (the desktop) is the controller and the k3s server. Other devices and
Avrea take work in three lanes:

| Lane | For | How | Isolation |
| --- | --- | --- | --- |
| **k3s** (`factory`, `lanes`, `z0` queues) | untrusted repo work, anything that fits a container | oss-factory `factory submit`, or a Job with `kueue.x-k8s.io/queue-name` | restricted Pod Security, `netpol-ready` gate, egress only to DNS + internet (docs/k3s/ONBOARDING.md) |
| **host** (`fleet run`) | our own builds/tests that need the host toolchain (Gradle/Android, bun, cargo, make, ...) | `scripts/fleet-build -- <cmd>` (default routing) or `scripts/fleet run <node> -- <cmd>` | unprivileged `agentjob` user, capped systemd scope, no LAN/tailnet egress; phones: polite-run |
| **Avrea** (public exact-head CI) | public-source heavy installs, full suites, compiler gates, factory verification | `scripts/fleet-build --node avrea -- <cmd>` | ephemeral runner, public checkout only, no workflow secrets or persisted checkout credentials |

The registry is `config/fleet/nodes.yaml`. Everything here is idempotent:
re-running a command with the same registry changes nothing.

## Devices (2026-10-20)

| Device | Role | State |
| --- | --- | --- |
| groot (i9-10900KF, 24 GB, RTX 3080 Ti) | k3s server, GPU, controller | online; health report-only; server hardening waits on the owner's sudo |
| mbp (i7-4870HQ 4C/8T, 16 GB, CachyOS) | permanent worker: k3s agent + host lane; local-data and native-toolchain builds | hardened and verified; JDK 17/21, Android SDK (34/35/37.2, build-tools 34/35/37), Bun, Node, Python; NOOP debug APK built there 2026-10-20 |
| omarchy-phone (S25 Ultra, Arch ARM in Omalauncher) | polite worker, host lane only | polite lane installed and verified; k3s cannot run there |
| galaxy-s22plus, alias `s22` (spare S22+, Arch ARM in Omalauncher, guest node `localhost-0`) | polite worker, host lane only | ssh on 8022; explicit light/worker profiles below |
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
fleet-build --node avrea -- bash -lc 'bun install --frozen-lockfile && bun test'
fleet-build --light -- python3 -m pytest    # phones for light arm64-safe work
```

- Public committed source + heavy verification -> **Avrea first**. Default
  `avrea-ubuntu-latest-4-vcpu` (16 GB); `-4-vcpu-8gb` saves minutes for
  CPU-bound work. Standard GitHub public runners remain the no-Avrea-budget
  baseline and fallback, not a reason to contend for MBP memory.
- Local/private data and native-only toolchains -> MBP. Gradle/Android ->
  capability `android-build` (mbp; 6 GiB, 4 CPUs, JDK 17, or `--jdk 21`).
  Uncommitted local work stays on the host lane; Avrea never uploads it.
- Phones -> light arm64-safe work (`--light`), not full dependency installs or
  x86 jobs. Boat -> x86 overflow and Docker jobs within its trial allowance.
  Avrea ARM/macOS are available when architecture/native macOS is required,
  not the default: ARM reference-minute cost is 3x x86.
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
  `/opt/android-sdk`, `/etc/fleet/toolchain.env` sourced by every Linux job);
  `--check` reports only. Gradle caches stay in `/home/agentjob/.gradle` on the
  node; the job's scope is stopped at the end, so Gradle/Kotlin daemons never
  outlive it.

### Boat: public x86 verification and overflow

Boat is an ephemeral Ubuntu amd64 worker, not a tailnet machine. Use the same
source, command and output interface:

```sh
fleet-build --node boat --light --src /tmp/reviewed-public-snapshot --fetch results.json --out /tmp/results -- python3 verify.py
fleet-build --x86 --mem 4G --timeout 300 --src /tmp/public-repo -- bash ci/verify.sh
fleet-build --docker --src /tmp/public-repo -- bash ci/docker-test.sh
fleet-build --public --light --src /tmp/public-repo -- python3 -m unittest discover
```

- Prefer Boat for x86 binaries and Docker-dependent jobs. `--x86` and `--docker`
  select Boat unless a node is pinned. They assert that the source is public.
  Docker is not a preinstalled capability claim. Install and check required
  toolchains in the job command.
- Use `--public` for reviewed public-source overflow. Normal routing tries the
  MBP and eligible phones first. A pre-admission 75 then tries Boat before
  sleeping. An allocated job never replays automatically, including exit 75.
- Keep local datasets, private repositories, environment files, credentials,
  GPU jobs and host-only toolchains off Boat. Use `--local-data` to disable
  cloud overflow. Explicit `--node boat --local-data` fails before admission.
  Review all source files and explicit `--input` files before upload.
- `--src` must be a Git checkout. Tracked and unignored files form one tarball.
  Environment files refuse transfer. The archive limit is 32 MiB compressed.
  Boat's JSON file API accepts only 5 MiB decoded. Larger archives use its
  signed raw-upload URL. The host sends no account Authorization header there.
  Signed URLs remain secret and do not enter job logs.
  Keep vendor trees and build caches ignored. `--no-src` can run standalone
  commands without an archive checkout. No host environment is forwarded.
- Boat creates a lease, uploads the archive, runs the command, fetches each
  requested output, and deletes the VM. Fetches reject archive traversal.
  Outputs and receipts remain under `~/.local/state/fleet/runs/JOB/`.
  `--keep` is forbidden. Failed jobs also delete their VM.
  A failed command keeps its original exit code if a requested output is absent.
  A successful command with an unfetchable requested output still fails.
- `--mem` and `--cpus` select a provider shape, not a guest process cgroup.
  Requests up to 3 GiB and 2 CPUs use small (4 GB RAM, 2 vCPU).
  Larger requests use default (8 GB RAM, 4 vCPU), with 7 GiB maximum requested
  memory. The command timeout is capped at 450 seconds inside the 600-second
  lease. Dependency installation and output retrieval also consume the lease.
- The shared guard allows **3 compute hours per rolling 24 hours** and at
  most **90,000 total trial seconds**. It reserves 600 seconds for every live
  VM plus the new VM. Provider concurrency is **2**. Prioritize jobs that unblock
  other agents. Do not bypass the guard, create directly, or enable paid usage.
- On provider/budget hold, `--wait` retries outside admission. Use `--wait 0`
  inside MBP quiet or turnstile locks. Release locks before any retry.
  Groot never becomes the build fallback.

The [Boat operations guide](BOAT.md) describes the reaper and encrypted-secret
mechanism. The [scoped-key proposal](BOAT-SECRETS-PROPOSAL.md) requires Kevin's
approval. This integration sends no worker credentials.
### Avrea public exact-head lane

The dedicated public repository is
[kvnloo/fleet-runner](https://github.com/kvnloo/fleet-runner), workflow
`.github/workflows/verify.yml`. This is the only dispatch repository used by
`fleet-build`; a target project does not need its own workflow or app installation.
Kevin's Avrea installation covers all 1,292 repositories (console, 2026-10-23).
The dedicated repo has provisioned an Avrea runner successfully. For a future
selected-repository installation, add it through
[the Avrea app installation](https://github.com/apps/avrea/installations/new).

```sh
# Commit and push first. Otherwise select a public SHA explicitly.
fleet-build --node avrea --fetch 'test-results/**' --out /tmp/gate -- \
  bash -lc 'python3 -m pip install -e ".[test]" && python3 -m pytest'
fleet-build --node avrea --repo OWNER/REPO --sha FULL_40_CHARACTER_SHA \
  --runner avrea-ubuntu-latest-4-vcpu-8gb --timeout 1800 -- bash -lc 'make test'
# JSON file: an array of independent shell command strings, each at the same SHA.
fleet-build --node avrea --matrix /tmp/commands.json --parallel 3 -- make test
```

Inputs are a **public** repository, full commit SHA, shell command, runner
label, relative artifact globs, optional command matrix, parallel bound, and
timeout. No local source/data/credentials are transferred. The client rejects
private repos and implicit dirty heads; the workflow independently verifies
public visibility and checks out the exact SHA with `persist-credentials: false`.
Commands execute at the repo root for explicit `--sha`, or in the caller's
subdirectory for inferred clean local heads. Include dependency/toolchain setup
in the command. `--input`, `--keep`, local JDK/resource flags and `--light` are
host-only, not silently ignored.

The client dispatches with `gh workflow run`, correlates a unique request ID
(never someone else's latest run), waits, downloads artifacts, validates
exact-head receipts and returns the command's exit status. Matrix failures do
not cancel siblings. Results include `request.json`, `budget.json`, `run.json`,
`status.json`, and per-job `receipt.json`/`stdout.log` plus requested artifacts.
Queue timeout requests cancellation; ambiguous dispatch failures retain their
budget reservation and must not be blindly replayed. All logs, commands and
artifacts are public: never put secrets or private data in them.

**Runner/account facts:** [labels and RAM](https://docs.avrea.com/runners/),
[rates](https://avrea.com/pricing), [billing](https://docs.avrea.com/billing/).
Linux x86 sizes are 1/2/4/8/16/32 vCPU; ARM 1/2/4/8/16.
`avrea-ubuntu-latest` is 2 vCPU/8 GB, latest currently Ubuntu24.04.
Memory-qualified 4-vCPU/8-GB and 8-vCPU/16-GB variants are cheaper.
`avrea-macos-26-{8,16}-vcpu` uses Apple M5 Max ARM (24/48 GB).
Windows2025 labels are `avrea-windows-2025-{2,4,8,16}-vcpu`; no Windows32 label.
Free-tier job/vCPU caps are lower and usage-dependent, not a published number.
Start at an operator-approved parallel bound of4 and back off on queueing;
this is a discovery policy, not a claim the service guarantees4 slots.

**Monthly guard:** `scripts/fleet-avrea-budget check` runs before every lane
dispatch. At80% used it warns; at95% projected usage it refuses (exit75),
including timeout-based reservations for the requested fan-out. Reference
minutes are priced at Linux x86 2-vCPU/$0.004: x864-vCPU/16-GB costs2x,
4-vCPU/8-GB1.5x, 8-vCPU/16-GB3x, 8-vCPU/32-GB4x, 32-vCPU16x;
ARM is3x its corresponding x86 type, Windows8 costs8x, macOS8 costs20x.
Accounting is per second, not rounded job minutes. Other metered resources
can consume the same free credit.

The initial operator-confirmed baseline is org`z0`, **2,955 remaining of3,000**
at2026-10-23 18:45CDT (23:45UTC), therefore45 reference minutes used.
No card is on file; exhaustion stops jobs, but the guard deliberately holds
earlier. Re-baseline from Kevin's Billing screenshot when a new balance is
provided. No documented CLI billing field supplies this current free balance.
The guard refuses missing/stale/invalid accounting rather than assuming zero.
See `fleet-avrea-budget --help` for the local authoritative snapshot schema,
factory workflow scope and reservation lifecycle. Snapshot/ledger live under
`~/.local/state/fleet/avrea/`, never in public source. Protect that baseline as
operator input; it is not self-reported by target code.

Caching is colocated: `actions/cache@v4+` and language setup caches work
without migration; package registries and supported build tools are proxied.
Regular cache quota25GB/repo, LRU eviction, unused entries eligible after7days.
Run a full gate twice and report both timings; do not call a second run a
cache hit without cache evidence. [Cache docs](https://docs.avrea.com/cache/overview/).
The documented CLI (`avr`, Python3.14+) exposes JSON run/job/repo/org inventory,
logs, metrics, caches and SSH (`avr job ssh JOB_ID`); authenticate separately.
SSH is only available while the job is live. [CLI](https://docs.avrea.com/cli/),
[SSH](https://docs.avrea.com/debugging/).

**Security:** dispatch is manual only, no `pull_request_target`, no workflow
secrets, no deployment environments or credentials forwarded to target commands.
Only public code/data is eligible; never execute untrusted fork PR code with
secrets. Target checkout tokens are not persisted. The verification job's
GitHub permission is read-only contents; artifact upload is the only write
service it uses. Existing fork CI conversions live on downstream branches,
never existing project default branches.

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
  Internet works. A job that passes its memory cap is OOM-killed inside its
  scope (exit 137); the host and k3s are untouched.
- **Results**: output streams back and is saved to
  `~/.local/state/fleet/runs/<job-id>-<node>.log`; `--fetch PATH` (relative to
  the job dir, e.g. `src/dist`) copies files back to
  `~/.local/state/fleet/runs/<job-id>/`. The remote job dir is deleted unless
  `--keep`. Exit code = the job's exit code (75 no room/drained, 124 timeout,
  137 memory).
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
- laptops: not on battery under 40%. Light-mode phones: battery >=50% or charging,
  battery <=40 C and thermal status <=1. Worker mode follows the explicit
  [owner override](#phone-audit-and-routing-2026-10-23): no thermal gate,
  only S25's 2% floor, plus memory limits.
- not in maintenance (`/var/lib/fleet/maintenance`)

After 2 bad checks in a row a `cordon` node is cordoned and annotated
`z0.dev/cordoned-by=fleet-health` with the reason; after 2 good checks it is
uncordoned. A node someone cordoned by hand is never uncordoned. groot is
report-only (it hosts the control plane, Kueue and the factory gateway). Phones
are `pause`d: `fleet run` skips them. Reports: `~/.local/state/fleet/health/<node>.json`
and `history.jsonl` (bounded). Warnings (pending updates, reboot needed) do not cordon.

Forced test (what the PR verified):

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

- Profiles are explicit: `fleet phone-mode NODE light|worker`. Admission reads
  one guest file, `~/.config/fleet/phone-mode.json`, generated from the registry.
- Light mode uses one slot, two low-numbered cores while charging or one on
  battery, and a 25% aggregate RAM ceiling. It keeps battery >=50% or charging,
  battery <=40 C and Android thermal status <=1.
- Worker mode is the owner's manual override. S25 uses cores 0-5, six slots,
  a 75% RAM ceiling and only a 2% battery floor. S22 uses cores 0-6, four slots,
  the same RAM ceiling and no battery floor. Neither worker profile gates on
  charging, battery temperature or Android thermal status. Thermal readings
  remain in admission receipts. Android handles throttling.
- All modes keep nice 19, idle I/O, the owner pause switch and memory admission.
  Live available RAM must cover 1200 MiB plus outstanding reservations and the
  next request. Aggregate requests also cannot exceed the profile's RAM ceiling.
  This conservative sampled admission is not a cgroup hard limit.
- Each slot holds an inherited flock and memory reservation across both direct
  and durable execution. Two failing running gates drain a job with TERM then
  KILL. A mode switch drains jobs admitted under the old mode. The 800 MiB
  emergency available-memory floor remains active.
- Tern, its daemon and remote serve are not touched and keep running. Android
  apps and settings are not touched. Jobs in the guest run as the Omalauncher
  app's uid and can read the guest's `/root`, so only the owner's own work goes
  there; it is tainted `phone` and needs `--tolerate phone` or `--node`.
- Owner switch: `touch ~/.config/fleet/pause` in the guest stops phone work
  (running jobs drain within a minute); `rm` it to resume.

### Phone audit and routing (2026-10-23)

Use `fleet-build --node galaxy-s22plus --light --mem 512M --wait 0 -- COMMAND`
for S22, or replace the node with `omarchy-phone` for S25. A pinned phone still
needs `--light`: the default `build` class selects the MBP, not phone workers.
Prefer phones for arm64-friendly Python/Node suites when the MBP queue is busy.

```sh
scripts/fleet phone-mode omarchy-phone worker
scripts/fleet phone-mode galaxy-s22plus worker
# Before interactive daily-phone use:
scripts/fleet phone-mode omarchy-phone light
# Omit the final argument to read the selected profile.
```

The mode file contains affinity, slots, RAM percentage, battery floor and mise
runtime versions. Source policy stays in `config/fleet/nodes.yaml`. The owner
explicitly removed worker thermal and charging gates on 2026-10-23.
Light mode keeps the original gates. This does not authorize Android changes.

Both guests expose Python 3.14.8 and Git 2.56.0. S25 has Node 24.21.0 and
Bun 1.3.14 under mise. Its profile places mise shims on the fleet-job PATH,
with explicit runtime versions and MISE_DATA_DIR even when payload HOME changes.
S22 package provisioning installed Node 26.12.0, Bun 1.4.3, Go 1.27.3,
Rust/Cargo 1.99.1 and GCC 16.1.1. A real fleet job executed every version command.
The transaction downloaded 184.73 MiB and installed 869.06 MiB in 519.775 seconds.
Neither phone initially exposed Zig.

S25's stale package database initially produced 404 errors. The owner approved
a full guest `pacman -Syu`, not a partial refresh. Before that operation,
explicit and complete package lists recorded 61 and 338 entries at
`~/.local/state/fleet/package-snapshots/20261023-162245-omarchy-phone/` on groot.
Copies remain in the retained guest upgrade job
`~/fleet-jobs/20261023-162338-a645/src/pre-upgrade-{explicit,all}.txt`.
The admission check confirmed 64% battery and charging.

The full upgrade updated 49 packages, then installed Go 1.27.3,
Rust/Cargo 1.99.1 and GCC 16.1.1. The entire job completed in 197.41 seconds.
PRoot reported skipped systemd hooks and symlink-permission warnings.
The transaction exited 0, the existing Tern/SSH services remained reachable,
and a subsequent real compiler job passed. No Tern binary or session restart
command was issued. The existing fleet maintenance flag blocked other jobs
through the package transaction and was removed only on success.

| Job | Phone routing |
| --- | --- |
| Owner-owned Python suites, scans, Git work | Prefer phones when MBP is queued. Start at 512 MiB. |
| Node/Bun tests | Both phones have native runtimes. Keep dependencies arm64, not copied x86 node_modules. |
| Go/Rust tests | Both phones run native compilers. S25 completed the approved full guest upgrade first. Start with `--mem 1G`, `GOMAXPROCS=3` and `go test -p 1`. |
| Bend-C or Zig cross-builds | Not qualified. No measured Bend/Zig result. Never execute x86 outputs. |
| Docker, k3s, cgroup-dependent tests | Unsupported inside PRoot. Use a real Linux worker. |
| Large memory jobs | A 75% ceiling does not promise 75% free RAM. Live memory admission wins. |
| GPU inference | Not qualified. S22 and default S25 Vulkan enumerate CPU llvmpipe. Forced S25 Freedreno finds no GPU. |

Bun package installation must avoid PRoot hardlink emulation. Use
`bun install --backend copyfile` and invoke an already-installed native compiler
directly, such as `node_modules/.bin/tsgo`, rather than another `bunx` install.
FactoryScale reported a real S25 OpenCode qualification at `7e399379`
(`20261023-163855-1ddd`): 562 packages installed in 15.13 seconds with copyfile,
then 133 tests passed with 747 assertions in 4.59 seconds under job-local Bun 1.4.2.
The later bunx compiler install expanded `.l2s` pointers and reached sampled
RSS 2012 MiB against a 1 GiB request. The memory guard correctly returned 137.
That typecheck was NOT_RUN, not a source failure.
The leftover job cache refused PRoot cleanup. Accessible entries measured
345 KiB, not a complete size because some pointers returned EPERM. The phone
still had 15 GiB free and all slot locks were free. Do not retry that expansion
or recursively delete unrelated guest data to remove the isolated cache.
For uv, set `UV_LINK_MODE=copy`. FactoryScale's initial S25
`20261023-165620-f753` downloaded CPython 3.13.13 but failed venv seeding before
tests because of hardlink emulation. Its accessible leftover size was 2824 KiB
with nine inaccessible paths, while the filesystem retained 14 GiB free.
The corrected copy-mode job `20261023-165805-1b96` passed 19 study tests,
three manifest tests and the real producer/consumer check in 30.88 seconds.
These are peer-reported qualification results, not tests rerun by PhoneFleet.

S22 uses key-only SSH at `100.97.11.22:8022` (`ssh s22`), even when its Android
Tailscale app is offline. Self-ADB uses `_adb-tls-connect._tcp` mDNS.
Never touch its launcher UI for a build. Worker affinity excludes core 7.

S25 guest SSH/Tailscale and its audio supervisor were already reachable.
Pinned ADB port 36065 was stale. Read-only
`avahi-browse -rt _adb-tls-connect._tcp` found port 38547.
Guest `adb connect 100.117.226.39:38547` and `getprop ro.product.model` confirmed
SM-S938U before pinning the new serial. Starting only the existing worker runsv
restored fleet-worker without restarting Tern or SSH. Its tracer was the
persistent PulseAudio PRoot.

S25 has Termux, but ADB run-as refuses its non-debuggable package and its private
runtime directory denies access. No native Termux llama.cpp or GPU compute is
reachable from the current fleet connection.

Initial admissions refused S25 at 34% discharging and S22 above 40 C with
thermal status 3. The S22 queue exhausted 15 minutes without a payload.
These are admission holds, not CPU runtime measurements. The owner then chose
the explicit worker overrides above. Charging is recommended, not required.

Qualification uses the same two-file snapshot of this repository's
`tests/test_fleet_phone_lane.py` and `scripts/fleet-polite-run`. The eight tests
exercise real wrapper execution, slot exclusion, aggregate memory admission,
light-mode gates and the explicit worker override. Android telemetry inside
the unit tests is an isolated fixture, not evidence of hardware performance.

| Node | Eight-test payload | Observed command wall | Job ID |
| --- | ---: | ---: | --- |
| S25 `omarchy-phone` | 25.704 s | 33.124 s | `20261023-161317-97f0` |
| S22 `galaxy-s22plus` | 45.526 s | 55.319 s | `20261023-162125-2eb0` |
| MBP `mbp` (1 CPU, 512 MiB) | 25.384 s | 87.87 s including quiet-lock wait | `20261023-165950-0d0c` |

All three jobs exited 0 and printed matching source hashes:
runner `d44ad6da0a61a4b78e3fab95ffc109a99d74df83b2f9af8c81f2859594b4aaa9`,
tests `28140676e82c236c7e3e06a55b9fb183c05b36324c56b905405a87ecf2249427`.
Logs remain under `~/.local/state/fleet/runs/JOB-NODE.log` on groot.
Phone wall figures measure the direct fleet invocation. MBP's observed command
wall includes the external quiet-lock wait, so it is not a normalized fleet-only
comparison. Its persisted job log confirms all eight tests and exit 0.
The MBP attempt used `--wait 0` inside the shared lock. Any admission retry
must release the locks and sleep outside them.
This suite includes wait-based concurrency tests. Do not treat these numbers
as a CPU or GPU ranking. Source-transfer size also matters: shipping the whole
dotfiles tree previously cost S25 118.041 seconds end-to-end for a 26.180-second
payload. The measured comparison therefore sends only the required real files.

Native qualification ran Go's real `crypto/sha256` standard-library tests,
then compiled and ran three Rust checks for arm64 target, threads and filesystem
I/O. Both used a 1 GiB request, `GOMAXPROCS=3` and `go test -p 1 -count=1`.
The Rust checks are an explicit compiler/runtime smoke fixture, not a product
test suite or a Bend benchmark.

| Node | Go/Rust qualification fleet wall | Job ID |
| --- | ---: | --- |
| S25 after full guest upgrade | 33.203 s | `20261023-162830-a54a` |
| S22 after toolchain installation | 243.123 s | `20261023-162459-bbe0` |

Each job passed Go's suite and all three compiled Rust checks. These first-build
figures include compiler startup/cache population and PRoot overhead.
S25 additionally printed its Node/Bun versions. Do not infer a general CPU
ranking from these jobs. GPU enumeration after S25's Mesa 26.2.5 upgrade still
reported only CPU llvmpipe, and forced Freedreno still found no physical GPU.

No APK, Android setting or launcher UI was changed by this fleet work.
After a wireless-debugging port change, discover mDNS, connect guest ADB,
confirm the model and update the pinned serial.

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
- Worker mode uses cores 0-6 and four slots, reserving core 7 for its launcher.

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
