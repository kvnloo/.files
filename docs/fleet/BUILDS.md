# Builds and tests: run them on the fleet, not on groot

groot is the owner's desktop, the k3s server and the GPU box, and it is often
short on memory with `heavy.lock` queued behind other agents. Builds and test
suites go to the workers by default:

| Work | Where | Command |
| --- | --- | --- |
| Public-source heavy installs/full suites/compiler gates | Avrea (4 vCPU by default) | `fleet-build --node avrea -- bash -lc 'npm ci && npm test'` |
| Local/private data, native-toolchain Gradle/Android | MBP host lane | `fleet-build --node mbp -- ./gradlew assembleFullDebug` |
| Local-data Bun/Node/Python suites, `make` | MBP host lane | `fleet-build --node mbp -- bun test` |
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

Default non-phone local jobs and explicit `--node mbp` retain the host backend.
Kueue is opt-in only through `--node k3s-mbp` while cache compatibility qualifies.
Explicit phone, Boat and Avrea routes retain their own backends.
The MBP backends preserve the caller's relative directory and never select groot.

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
- Host admission waits retry every 60 seconds for `--wait` seconds.
  `--wait 0` disables host retries. The host lane remains 7 GiB / 4 CPUs.
- Never hold `/tmp/mbp-turnstile.lock` or `/tmp/mbp-quiet.lock` during host
  admission waits. Inside either lock, use `fleet-build --node mbp --wait 0`.
  On admission exit 75, release locks, sleep outside them, then retry.
- The following Kueue behavior applies only to `--node k3s-mbp`.
  Do not wrap Kueue submissions in host turnstile or quiet flocks.
- Opt-in Kueue jobs enter the `lanes` LocalQueue in namespace `fleet-mbp` as suspended
  Kubernetes Jobs. Kueue admits them against the MBP flavor quota.
  Queued jobs do not consume CPU.
- `--wait 0` means no queue wait on all nodes. Kueue permits five seconds for
  controller admission, then deletes a still-pending Job and exits 75.
  Positive `--wait N` permits at most N seconds of admission waiting.
  Only `--node k3s-mbp --wait -1` waits indefinitely.
  `--timeout SECONDS` limits execution after admission, not queue time.
  A busy queue is not permission to execute on groot.
- Opt-in Kueue `--mem` and `--cpus` set both container requests and limits.
  Requests above the total queue quota exit 75 immediately, before staging.
  The default build request remains 3 GiB. Gradle remains 6 GiB.
  Neither fits the sampled 3011592192-byte (~2.805 GiB) quota.
  Use an explicit memory request appropriate for the actual job.
  Do not reduce a real job's request merely to obtain admission.
- `--input FILE:RELATIVE_PATH` stages an exact artifact without scanning an output
  tree. `--keep` preserves the remote job directory. Once a job ID exists, a 75 is
  not automatically retried: inspect partial side effects first.

See [DESKTOP-ADMISSION.md](DESKTOP-ADMISSION.md) for effective cgroup ceilings,
Kueue worker-only placement, the bounded supervisor, and guarded delivery continuation.
- The opt-in `lanes` quota is separate from the 7 GiB host slice.
  Static quota does not account for live host work. Do not run both backends
  against the same apparent free capacity without coordinating admission.
- CPU quota uses physical cores: `min(4 physical cores, 6.5 allocatable CPUs) = 4`.
  The parent sample at `2026-10-24T00:45:10Z` reported `MemAvailable=5159075840`
  bytes. Allocatable is `12046536Ki`, or `12335652864` bytes.
  The exact budget is
  `max(0, min(12335652864, 5159075840 - 2147483648)) = 3011592192` bytes.
  The declaration uses that byte value without whole-GiB rounding.
- During migration, factory's MBP CPU and memory quotas are zero. Otherwise its
  independent queue could overcommit the same worker. Restore capacity only through
  an explicit shared-capacity plan. Both `lanes` LocalQueues share one quota.
- Source transfers use tar through the existing fleet registry and SSH command
  for MBP's `agentjob` identity. Remote commands use `bash -c`.
  Staging is `/home/agentjob/.local/state/fleet/kueue/<job>` on MBP.
  The pod mounts source at `/work/src` through hostPath.
  It runs as `agentjob`, UID 1001, with `runAsNonRoot: true`.
- HOME is `/home/agentjob`, mounted read-write to retain existing build caches.
  This allows trusted jobs to access that account's other files and caches.
  `/tmp` uses a per-job disk directory. Cache qualification must pass before
  any default-backend cutover receives parent approval.
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
  Without `--keep`, foreground Job deletion stops pods before staging removal.
  Cancellation removes the Job and staging even with `--keep`.
  `--fetch` copies results under `~/.local/state/fleet/runs/<job>/`.
  `--out DIR` also copies requested results there.
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
