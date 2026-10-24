# Six-Harness Adaptive Workstation Specification

**Status:** design complete; root-level application and reboot require explicit approval.

## Objective

Keep six interactive AI harnesses available while preventing whole-desktop stalls and involuntary process loss on the i9-10900KF / RTX 3080 Ti workstation. Optimize responsiveness, useful throughput, and recovery—not synthetic peak concurrency.

## Observed constraints

- 15.5 GiB physical RAM, currently two 8 GiB DDR4-4000 DIMMs; two slots are empty.
- Spare kit: G.Skill F4-3600C18D-16GTRS, two 8 GiB DDR4-3600 CL18 DIMMs. Mixed-kit stability is not established.
- Active swap: 24 GiB zram at priority 200, 32 GiB NVMe at priority 50, and 128 GiB emergency file at priority 10.
- Zram currently retains about 14.3 GiB of swapped pages. Earlier measurement showed only 1.66:1 compression and about 7–11 GiB of physical RAM consumed by zram.
- Kernel OOM has killed Chrome, Chromium, and Claude processes inside tmux scopes despite ample nominal disk-swap capacity.
- Current tmux scopes range from about 3 MiB to 565 MiB resident, with 9–648 tasks; historical peaks reached roughly 1.75 GiB resident plus 3.8 GiB swap and 408 tasks in one scope.
- Current aggregate app.slice residence is about 2.2 GiB, but cold pages remain trapped in zram. Memory PSI has previously reached full avg300=2.63%; current full avg300 is about 0.25%.
- Active scheduler is CachyOS Flow in Auto mode. VM policy is swappiness=150, page-cluster=0, vfs_cache_pressure=50, watermark_scale_factor=125, overcommit_memory=0.

## Root cause

The failure is capacity and lifecycle control, not CPU scheduling. Long-lived tmux scopes accumulate browser, Node, language-server, build, and agent descendants. Oversized zram consumes scarce DRAM and cannot spill already-compressed pages to lower-priority NVMe swap. The 128 GiB emergency file dilutes percentage-based early-OOM thresholds. Existing agent.slice safeguards are inactive because real workloads live in app.slice/tmux-spawn scopes. Performance mode removes visual effects but does not reclaim or contain the workloads.

## Architecture

### 1. Preserve interactive shells; control heavy work

- Keep tmux server and durable pane shells outside disposable workload scopes.
- Launch each harness in a named `agent.slice/agent-<id>.scope`; return to the pane shell when it exits.
- Do not promise six simultaneous browser/build bursts on 16 GiB. Keep six harnesses connected, but admit heavy tool phases through a pressure-aware concurrency gate.
- Initial heavy tokens: 2 on 16 GiB, 3 on 24 GiB, 4 on verified 32 GiB. Autotuning may reduce these values immediately but may increase them only after a clean canary window.
- Classify Chromium, Chrome, Playwright, Electron, Node build workers, compilers, and local model servers as heavy. Network-waiting agents, shells, editors, and tmux are interactive-light.

### 2. Replace zram-only compression with an evictable hierarchy

Preferred post-reboot hierarchy:

1. DRAM.
2. Zswap compressed cache using zstd/zsmalloc, max pool 20%, accept threshold 90%, shrinker enabled.
3. Existing 32 GiB NVMe swap partition.
4. Existing 128 GiB emergency file inactive, retained only for explicit recovery.

Zswap is preferred over a large zram swap device because its LRU can evict compressed pages to the backing NVMe swap. The current kernel supports zswap, zstd, and the shrinker; zswap is currently disabled. This change requires staged root configuration and reboot. Never run swapoff while used pages cannot fit in available RAM.

### 3. Pressure-aware cgroup policy

- Protect `session.slice`, Hyprland, PipeWire/WirePlumber, tmux, networking, and the active terminal with `MemoryLow`/higher CPU and IO weights.
- Put harnesses in `agent.slice` with lower CPU/IO weights and `MemoryHigh` as a soft reclaim boundary.
- Avoid routine `MemoryMax`, systemd-oomd kill, and earlyoom targeting of harnesses: the user requires no process loss.
- At warning pressure, stop admitting heavy work and call `memory.reclaim` in small stateless increments on idle harness scopes.
- At critical pressure, freeze the least-recently-interactive heavy scope with cgroup v2 `cgroup.freeze`; do not SIGSTOP individual processes. Resume automatically after sustained recovery.
- Keep a final global OOM backstop because Linux cannot mathematically guarantee survival under arbitrary allocation. Its activation is an invariant breach, not normal control flow.

### 4. Deterministic realtime controller

A small privileged policy service observes aggregate, privacy-safe metrics every second and acts from an allowlist. An LLM never writes live kernel controls.

States:

- `GREEN`: admit up to the current heavy-token limit.
- `AMBER`: memory some PSI or refault/swap latency elevated; stop new heavy admissions, enable desktop performance mode, reclaim cold pages.
- `RED`: sustained memory full PSI, low MemAvailable, or NVMe swap latency breach; freeze one idle heavy scope and re-evaluate.
- `RECOVERY`: resume one frozen scope at a time after 60 seconds below recovery thresholds.

Initial thresholds are canary values, not universal truths:

- AMBER: memory some avg10 >= 2%, full avg10 >= 0.5%, or MemAvailable < 2 GiB for 10 seconds.
- RED: memory full avg10 >= 2%, MemAvailable < 1 GiB, or swap-in latency/churn exceeds the measured safe baseline for 10 seconds.
- RECOVERY: memory full avg60 < 0.25%, MemAvailable > 3 GiB, and no rising refault rate for 60 seconds.

Use hysteresis and minimum dwell times. Never oscillate freeze/resume faster than once per minute.

### 5. Autoresearch without unsafe autonomy

Separate observation, proposal, canary, and promotion:

1. Record aggregate metrics and workload class labels, never pane contents, command arguments, clipboard, titles, or keystrokes.
2. Offline analyzer proposes one allowlisted parameter change.
3. Validate configuration bounds and create an automatic rollback transaction.
4. Canary for at least 20 minutes or one representative workflow.
5. Reject immediately on OOM, process exit attributable to policy, audio xruns, compositor restart, memory full PSI regression, p95 interaction-latency regression >10%, or throughput regression >5% without a corresponding latency win.
6. Promote only after repeated improvement across at least three comparable windows.

Allowlisted experimental variables:

- heavy-token count
- AMBER/RED PSI thresholds and dwell times
- reclaim interval and byte increment
- CPUWeight and IOWeight for agent.slice
- scheduler mode among prevalidated Flow/scx_lavd profiles
- zswap max-pool and accept threshold, within fixed bounds and only across controlled reboots

Never autotune overclocking, firmware, power limits, filesystems, network/firewall policy, OOM kill policy, or arbitrary sysctls.

## Metrics and invariants

Track:

- `/proc/pressure/{cpu,memory,io}` some/full averages and totals
- per-scope `memory.current`, `memory.peak`, `memory.events`, `memory.stat`, `memory.pressure`, task count, and frozen state
- zswap pool size, stored pages, rejects, writeback, and compression ratio
- swap-in/out throughput, major faults, workingset refaults, NVMe latency
- runnable queue, CPU utilization/frequency, GPU utilization/VRAM
- compositor health, audio xruns, tmux pane/scope liveness
- admitted, queued, frozen, resumed, completed, and failed workload counts

Hard invariants:

- No automated signal-based termination.
- No mutation based on pane content or command arguments.
- Tmux server, shells, compositor, audio, networking, and SSH stay outside reclaim/freeze targets.
- Every mutation is bounded, journaled, reversible, and expires unless promoted.
- One variable per canary; rollback on missing telemetry.
- A user override immediately disables admission/reclaim/freeze actions.

## Hardware recommendation

32 GiB is the practical target. Install the complete spare 2x8 GiB kit only after confirming the installed Patriot kit's voltage, timings, and part number. Mixed four-DIMM operation should prioritize stability at the common DDR4-3600 profile over DDR4-4000. Do not install a single unmatched module as the intended steady state. If the cooler blocks A1, reseat it and install A1/B1 together.

## Delivery sequence

1. Implement read-only observer and record a representative baseline.
2. Implement durable pane shell plus per-harness scopes without limits; verify topology.
3. Add heavy-work admission gate; verify six harnesses stay connected while excess heavy jobs queue.
4. Add stateless `memory.reclaim` in conservative canary mode.
5. Add cgroup freeze/resume emergency control and user override; pressure-test in a bounded disposable cgroup.
6. Stage zswap/NVMe configuration, deactivate emergency auto-swap, and reboot under explicit approval.
7. Run 16 GiB workload canaries; then repeat after a validated 32 GiB upgrade.
8. Enable offline autoresearch proposals only after deterministic controls demonstrate zero policy-attributed process exits.

## Acceptance criteria

- Six harness sessions remain available through a bounded synthetic pressure test.
- Excess browser/build phases queue or temporarily freeze; none are killed.
- Tmux pane shells remain interactive after an agent command exits.
- No kernel OOM, systemd-oomd kill, earlyoom kill, compositor restart, or audio xrun during the representative six-harness workload.
- Memory full PSI and p95 terminal interaction latency improve from the recorded baseline.
- Rebooted swap topology is zswap over 32 GiB NVMe, with the 128 GiB emergency file inactive.
- Every controller action is visible in a privacy-safe event log and can be disabled immediately.
