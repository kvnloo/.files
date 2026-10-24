# Builds and tests: run them on the fleet, not on groot

groot is the owner's desktop, the k3s server and the GPU box, and it is often
short on memory with `heavy.lock` queued behind other agents. Builds and test
suites go to the workers by default:

| Work | Where | Command |
| --- | --- | --- |
| Gradle / Android (NOOP, Lawnchair) | mbp | `fleet-build -- ./gradlew assembleFullDebug` |
| Bun, Node, Python suites, `make` | mbp | `fleet-build -- bun test` |
| lint, pure-Python tests, scans, git work (arm64-safe) | mbp or a phone | `fleet-build --light -- python3 -m pytest tests/unit` |
| Genuine GPU work | groot, inside the bounded agent envelope | allocate/prove the GPU; a name or render label is not enough |
| CPU-only film delivery | mbp | `fleet-fframes-delivery --out NEW_DIRECTORY --wait 0` |
| code from an unknown repo | k3s `factory` queue | oss-factory `factory submit` |

`~/.local/bin/fleet-build` points to the installed admission owner's isolated
dotfiles tree (inspect `readlink -f` rather than assuming a branch). Run it from anywhere inside a repo: it
ships the repo's tracked and untracked-but-not-ignored files, runs the command
in the same subdirectory on the worker, streams the output, and exits with the
job's code. It never picks groot (groot has no host lane).

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
- No room (mbp busy with another build, paused by `fleet health` because it
  is hot, or cordoned): `fleet-build` waits and retries every 60 s for up to
  `--wait` seconds (default 1800), then exits 75. That wait is the queue. Do not
  fall back to a groot build to save time.
- Never hold Groot's `/tmp/mbp-turnstile.lock` or `/tmp/mbp-quiet.lock` during
  admission waits. Inside either lock, use `fleet-build --wait 0`.
  On admission exit 75, release the locks, sleep outside them, then retry the
  whole lock wrapper. A 55-minute admission wait inside an exclusive lock
  blocked 19 jobs on 2026-10-23.
- Explicit `--node mbp` does not bypass pause, thermal or health admission.
  Unknown/unhealthy thermal telemetry holds before source transfer. A missing CPU
  toolchain is not permission to run on groot; install it through fleet IaC or hold.
- `--input FILE:RELATIVE_PATH` stages an exact artifact without scanning an output
  tree. `--keep` preserves the remote job directory. Once a job ID exists, a 75 is
  not automatically retried: inspect partial side effects first.

See [DESKTOP-ADMISSION.md](DESKTOP-ADMISSION.md) for effective cgroup ceilings,
Kueue worker-only placement, the bounded supervisor, and guarded delivery continuation.
- Jobs share mbp's lane (7 GiB, 4 CPUs for all agentjob work). A job is admitted
  only when the lane has room for its `--mem`, so two 6 GiB builds run one after
  the other instead of OOM-killing each other.
- Exit 137: the job passed its memory cap; raise `--mem` (mbp's lane allows up
  to 7 GiB in total).
- The worker side: JDK 17/21 (Temurin) and Bun in `/opt/fleet`, the Android SDK
  in `/opt/android-sdk` (read-only for jobs), Gradle caches in
  `/home/agentjob/.gradle` on mbp's own disk, so the second build of a repo
  downloads nothing. Gradle and Kotlin daemons are stopped with the job.
  Installed by `scripts/fleet toolchain mbp` from the registry's `toolchains`.
- Check a node's toolchain before relying on it:
  `scripts/fleet run --node mbp --no-src -- sh -c 'java -version; bun --version; echo $ANDROID_HOME'`.

Prefer phone workers for arm64-friendly tests when the MBP queue is busy:
`fleet-build --node galaxy-s22plus --phone --wait 0 -- python3 ...`,
or replace the node with `omarchy-phone`.

Phones: no agent resource caps; Android manages battery/thermal/RAM. Enforced by Bend law O10 / z0-guard phone-caps.

Both phones retain owner pause/call hooks, job timeout and process-group cleanup.
The wrapper preserves installed mise runtime discovery when payload HOME changes.
Guest package policy is `phone_packages` in the registry.
`scripts/fleet toolchain NODE` provisions those packages through normal admitted
phone jobs. `--check` only reads installed package versions.
See the [phone audit](README.md#phone-audit-and-routing-2026-10-23) for measured
results and GPU limits. Neither phone supports Docker/k3s or x86 executables.
For phone dependency setup, use `bun install --backend copyfile` and
`UV_LINK_MODE=copy` with uv. PRoot hardlink emulation can create inaccessible
`.l2s` caches and memory expansion. Invoke an installed compiler directly rather
than a second `bunx` package install. See the audit for real failure receipts.

Android manages phone memory and cached apps. Do not infer a guest job budget
from phone-wide `MemAvailable`, or reserve RAM for Android on the agent's behalf.
