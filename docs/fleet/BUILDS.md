# Builds and tests: run them on the fleet, not on groot

groot is the owner's desktop, the k3s server and the GPU box, and it is often
short on memory with `heavy.lock` queued behind other agents. Builds and test
suites go to the workers by default:

| Work | Where | Command |
| --- | --- | --- |
| Public-source heavy installs/full suites/compiler gates | Avrea (4 vCPU by default) | `fleet-build --node avrea -- bash -lc 'npm ci && npm test'` |
| Local/private data, native-toolchain Gradle/Android | MBP Kueue, subject to quota | `fleet-build --node mbp -- ./gradlew assembleFullDebug` |
| Local-data Bun/Node/Python suites, `make` | MBP Kueue | `fleet-build --node mbp -- bun test` |
| Light arm64-safe tests, scans, git work | phones | `fleet-build --phone -- python3 -m pytest tests/unit` |
| x86 overflow and Docker | boat (trial allowance) | pin the admitted boat host lane |
| Genuine GPU work | groot, inside the bounded agent envelope | allocate/prove the GPU; a name or render label is not enough |
| CPU-only film delivery | mbp | `fleet-fframes-delivery --out NEW_DIRECTORY --wait 0` |
| code from an unknown repo | k3s `factory` queue | oss-factory `factory submit` |

`~/.local/bin/fleet-build` points to the installed admission owner's isolated
dotfiles tree (inspect `readlink -f` rather than assuming a branch). Public
committed heavy work prefers `--node avrea`: it dispatches an exact public SHA
to [fleet-runner](https://github.com/kvnloo/fleet-runner), never ships local data,
downloads per-job receipts/artifacts and returns the command exit status.
Commit/push first or select `--repo OWNER/REPO --sha FULL_SHA` explicitly.
Use `--matrix FILE --parallel 3` for independent commands at the same head;
the operator-approved initial bound is4, back off if the free tier queues.
The monthly budget guard warns at80% and refuses at95% projected usage,
with rate-normalized minutes and a current operator billing baseline.
See [Avrea routing, budget and security](README.md#avrea-public-exact-head-lane).

Default non-phone local jobs and explicit `--node mbp` use Kueue.
`--node mbp-host` selects the host escape with a full-lifetime Kueue reservation.
Explicit phone, Boat and Avrea routes retain their own backends.
The MBP backends preserve the caller's relative directory and never select groot.
Direct `scripts/fleet run --node mbp` and automatically selected MBP work also
delegate to Kueue. They do not bypass shared admission.
Use `mbp-host` only for exceptional native-host requirements.

```sh
cd /mnt/zer0models/noop-oura/android
fleet-build --fetch app/build/outputs/apk/full/debug --out /tmp/noop-apk -- ./gradlew assembleFullDebug
# -> /tmp/noop-apk/debug/app-full-debug.apk, signed with the repo's fork-debug.keystore

cd /mnt/zer0models/lawnchair-z0live
fleet-build --jdk 21 -- ./gradlew assembleLawnWithQuickstepPlayDebug
```

- `./gradlew ...` implies `--android`: capability `android-build` (mbp), 6 GiB
  job memory, 4 CPUs, JDK 17. `--jdk 21` for Lawnchair. Override with `--mem`,
  `--cpus`, `--node`.
- `--fetch PATH` is relative to the directory you ran from; `--out DIR` copies
  the fetched files there (otherwise they stay under
  `~/.local/state/fleet/runs/<job>/`).
- Do not wrap Kueue submissions in manual turnstile or quiet flocks.
  Remove outer admission locks. Existing named wrappers should pass through to
  `fleet-build` without locking. Only Kueue reservations authorize admission.
- `--node mbp-host` must acquire its Kueue reservation before host execution.
  Retain the reservation until the host process and all its children stop.
  The old 7 GiB host slice is a safety ceiling, not a second admission budget.
- MBP Kueue jobs enter the `lanes` LocalQueue in namespace `fleet-mbp` as suspended
  Kubernetes Jobs. Kueue admits them against the MBP flavor quota.
  Queued jobs do not consume CPU.
- `--wait 0` means no queue wait on all nodes. Kueue permits five seconds for
  controller admission, then deletes a still-pending Job and exits 75.
  Positive `--wait N` permits at most N seconds of admission waiting.
  For MBP Kueue, `--wait -1` explicitly waits indefinitely.
  `--timeout SECONDS` limits execution after admission, not queue time.
  A busy queue is not permission to execute on groot.
- Kueue `--mem` and `--cpus` set both container requests and limits.
  Requests above the total queue quota exit 75 immediately, before staging.
  The default build request remains 3 GiB. Gradle remains 6 GiB.
  Both fit the approved 10441814016-byte (~9.73 GiB) aggregate memory quota.
  Use an explicit memory request appropriate for the actual job.
  Do not reduce a real job's request merely to obtain admission.
- `--input FILE:RELATIVE_PATH` stages an exact artifact without scanning an output
  tree. `--keep` preserves the remote job directory. Once a job ID exists, a 75 is
  not automatically retried: inspect partial side effects first.

See [DESKTOP-ADMISSION.md](DESKTOP-ADMISSION.md) for effective cgroup ceilings,
Kueue worker-only placement, the bounded supervisor, and guarded delivery continuation.
- Kueue is the shared admission budget. Direct host jobs are not accounted by static
  quota unless a reservation covers their whole lifetime. Never reserve the same
  capacity independently through the host slice and the queue.
- CPU quota uses physical cores: `min(4 physical cores, 6.5 allocatable CPUs) = 4`.
  After the host-work drain and authorized tmpfs cleanup, the parent approved
  **10441814016 bytes** (~9.73 GiB), without GiB rounding:
  `16630620160 - 2147483648 - 2837270528 - 1204051968 = 10441814016`.
  These terms are total RAM, the 2 GiB reserve, frozen idle OS baseline,
  and remaining shared memory. The idle baseline includes anonymous memory,
  unreclaimable kernel memory, stacks, page tables, unevictable and per-CPU memory.
  Do not treat active job memory as a new idle baseline.
  The result remains below allocatable `12046536Ki` (`12335652864` bytes).
  This is a static capacity plan, not instantaneous available-memory admission.
  Recompute after measured changes rather than assuming additional capacity.
- During migration, factory's MBP CPU and memory quotas are zero. Otherwise its
  independent queue could overcommit the same worker. Restore capacity only through
  an explicit shared-capacity plan. Both `lanes` LocalQueues share one quota.
- Source transfers use tar through the existing fleet registry and SSH command
  for MBP's `agentjob` identity. Remote commands use `bash -c`.
  Staging is `/home/agentjob/.local/state/fleet/kueue/<job>` on MBP.
  The pod mounts source at `/work/src` through hostPath.
  It runs as `agentjob`, UID 1001, with `runAsNonRoot: true`.
- HOME is `/home/agentjob`, mounted read-write to retain existing build caches.
  Absolute paths under that HOME remain valid in host and Kueue jobs.
  Trusted jobs can access that account's other files and caches.
  Both transports set package-cache environment values to HOME-backed disk storage.
  pnpm uses `/home/agentjob/.local/share/pnpm/store`.
  npm uses `/home/agentjob/.cache/npm`. uv uses `/home/agentjob/.cache/uv`.
  Host transport staging uses HOME-backed jobs storage, not host `/tmp`.
  Kueue staging and the pod's `/tmp` use per-job HOME-backed disk directories.
  The parent approved default routing after actual cache qualification and host-work drain.
- The image is `busybox:1.37.0`. Host toolchain mounts remain read-only:
  `/usr`, `/lib`, `/lib64`, `/opt`, `/etc/fleet` and `/etc/ssl`.
  The pod has no service-account token,
  drops all capabilities and disallows privilege escalation.
  These jobs execute the owner's trusted code.
  They are not the restricted `factory` path for unknown repositories.
- The dedicated `fleet-mbp` namespace permits hostPath through privileged Pod Security
  admission. This namespace label does not make the pod privileged.
  Existing `lanes` and `factory` namespaces remain restricted.
- The backend streams pod logs and saves
  `~/.local/state/fleet/runs/<job>-mbp.log`.
  It returns the container command's exit status when available.
  Oversized requests and admission timeout return 75. Execution deadline returns 124.
  Interrupted execution returns 130. A failed Job without a container result returns 1.
  Inspect the recorded job ID before any retry.
  A transport error does not prove that the command stopped.
- `--keep` retains terminal Jobs and their staged directories. Jobs have a 24-hour
  TTL. Retained staging needs separate removal after inspection.
  Native-host `--keep` retains staging and logs, not the reservation Job.
  The helper always releases that reservation after the host work stops.
  Without `--keep`, foreground Job deletion stops pods before staging removal.
  Cancellation removes the Job and staging even with `--keep`.
  `--fetch` copies results under `~/.local/state/fleet/runs/<job>/`.
  `--out DIR` also copies requested results there.
- Native execution has deadline T. Its reservation deadline is T+90 seconds
  so host termination grace remains covered.
  `scripts/fleet kill mbp <job-id>` stops a native host scope, if present,
  before deleting its Kueue Job. Other host/phone routing remains unchanged.
- Workload manifests for the migrated Hermes executor and quackles stay in
  `hermes-k8s-lab`. `.files` owns fleet policy, queue declarations and references.
  The parent retires kind only after it proves the replacement workloads healthy.

Prefer phone workers for arm64-friendly tests when the MBP queue is busy:
`fleet-build --node galaxy-s22plus --light --mem 512M --wait 0 -- python3 ...`,
or replace the node with `omarchy-phone`. Keep `--light` with the explicit pin,
because phones do not advertise the default `build` class.
Worker mode gives S25 cores 0-5/six slots and S22 cores 0-6/four slots.
Both reserve at most 75% RAM and retain the live 1200 MiB floor plus reservations.
Core 7 remains excluded for S22 launcher headroom. Jobs keep nice 19 and idle I/O.
The owner's worker override removes thermal and charging gates, retaining only
S25's 2% battery floor. Light mode keeps one slot and the original safety gates.
Use `scripts/fleet phone-mode NODE worker|light` to switch, or omit the mode to read it.
S25's profile exposes its existing mise Node 24.21.0 and Bun 1.3.14 to fleet jobs.
Guest package policy is `phone_packages` in the registry.
`scripts/fleet toolchain NODE` provisions those packages through normal admitted
phone jobs. `--check` only reads installed package versions.
See the [phone audit](README.md#phone-audit-and-routing-2026-10-23) for measured
results and GPU limits. Neither phone supports Docker/k3s or x86 executables.
For phone dependency setup, use `bun install --backend copyfile` and
`UV_LINK_MODE=copy` with uv. PRoot hardlink emulation can create inaccessible
`.l2s` caches and memory expansion. Invoke an installed compiler directly rather
than a second `bunx` package install. See the audit for real failure receipts.

S25 memory (measured 2026-10-20 23:36): the phone has 11.1 GiB RAM and 12 GiB
zram swap (6.2 GiB in use). `MemAvailable` is phone-wide, about 2.1 GiB. The
Omalauncher guest itself holds about 0.8 GiB RSS (Tern UI ~420 MiB, omp ~210 MiB,
pi, Hermes TUI gateways, tailscaled); the rest is Android: the owner's apps
(Oura, NOOP, ChatGPT, Telegram, X, WhatsApp, Gmail, ...) and 4.1 GiB of cached
app processes. Those cached apps are what the kernel would reclaim, so the
1200 MiB floor stays: it keeps a job from pushing Android's low-memory killer
into the owner's apps. What refused jobs was the 1 GiB default job size
(1200 + 1024 = 2224 MiB). A 512 MiB job fits (1712 MiB) and ran there
(`fleet-build --phone`, PHONE_OK aarch64).
