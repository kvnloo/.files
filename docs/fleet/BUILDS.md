# Builds and tests: run them on the fleet, not on groot

groot is the owner's desktop, the k3s server and the GPU box, and it is often
short on memory with `heavy.lock` queued behind other agents. Builds and test
suites go to the workers by default:

| Work | Where | Command |
| --- | --- | --- |
| Gradle / Android (NOOP, Lawnchair) | mbp | `fleet-build -- ./gradlew assembleFullDebug` |
| Bun, Node, Python suites, `make` | mbp | `fleet-build -- bun test` |
| lint, pure-Python tests, scans, git work (arm64-safe) | mbp or a phone | `fleet-build --light -- python3 -m pytest tests/unit` |
| GPU work, or a toolchain that exists only on groot | groot | say so explicitly in your report |
| code from an unknown repo | k3s `factory` queue | oss-factory `factory submit` |

`fleet-build` is `/workspace/.files-k3s/scripts/fleet-build` (symlinked as
`~/.local/bin/fleet-build` on groot). Run it from anywhere inside a repo: it
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

The phones (`omarchy-phone`, `galaxy-s22plus`) cannot run Gradle (arm64, about
2-3 GiB free, no SDK) and refuse jobs under 50 % battery off-charger or when
hot. `--light` (512 MiB per job) sends work there only when mbp is busier;
`--phone` forces a phone.

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
