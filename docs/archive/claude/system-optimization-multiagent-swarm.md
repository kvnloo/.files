# Multi-Agent Swarm Development — System Optimization Analysis

**Generated:** 2026-07-03  
**Host:** `groot` (CachyOS Linux)  
**Workload:** 30+ AI agent harnesses (Codex, Claude Code, Kimi × 10) plus browsers, dev servers, tests, and compositor.

---

## 1. Hardware Profile

| Component | Details |
|-----------|---------|
| CPU | Intel Core i9-10900KF @ 3.70 GHz (Comet Lake) |
| Cores / Threads | 10 physical cores / **10 logical CPUs (SMT disabled in BIOS)** |
| Max turbo | 5000 MHz |
| L1d / L1i / L2 / L3 | 320 KiB / 320 KiB / 2.5 MiB / 20 MiB |
| NUMA | 1 node |
| RAM | 16 GB (15.5 GiB usable) |
| Swap | 47.5 GB total = 15.5 GB zram (zstd) + 32 GB disk partition |
| GPU | NVIDIA GeForce RTX 3080 Ti (12 GB), driver 610.43.02 |
| Root / Workspace | Samsung SSD 960 EVO 500 GB NVMe (XFS) |
| BIOS | American Megatrends Inc. 2601, 2022-05-17 |

**Observed CPU state under load:** all 10 cores pinned at ~5.0 GHz.  
**Turbo status:** enabled (intel_pstate `no_turbo=0`, max_freq == cpuinfo_max_freq == 5 GHz).  
**SMT status:** disabled at BIOS; kernel reports `smt/control = notsupported`, 10 CPUs online.

---

## 2. OS / Kernel Profile

| Item | Value |
|------|-------|
| Distribution | CachyOS Linux (Arch-based, rolling) |
| Kernel | `7.1.2-3-cachyos` |
| Preemption | `PREEMPT_DYNAMIC` / `CONFIG_PREEMPT=y` |
| Default scheduler | CachyOS default EEVDF with BORE patches |
| sched-ext | **Supported and installed, not active** |
| cpufreq driver | intel_cpufreq (intel_pstate in passive mode) |
| Governor | **schedutil** |
| Kernel cmdline | `initrd=\initramfs-linux-cachyos.img root=UUID=9e575c2d-52cc-41ec-8b3f-15afd8191c81 rw zswap.enabled=0 nowatchdog quiet splash` |

**Already-installed performance tooling:**
- `scx-scheds 1.1.1-1` and `scx-tools 1.1.1-1.1`
- `ananicy-cpp.service` active with 14340 rules
- zram generator producing 15.5 GB zstd-compressed swap
- systemd resource limits already high (`nofile 1048576`, `nproc 65535`)

---

## 3. Workload Characterization

At the time of profiling the system was 4 hours uptime under active multi-agent work:

- **Load average:** 12.79 / 13.10 / 11.70 on 10 CPUs → sustained 100%+ utilization.
- **Agent harnesses:** Codex, Claude Code, multiple Kimi instances (`kimi`, `kimi-code`).
- **Browsers:** Zen Browser, Google Chrome, Chromium (including Playwright/headless shells for testing).
- **Dev/test infra:** Vite dev servers, pytest runs, Playwright CDP sessions, `agent_runs.py` watcher.
- **Desktop:** Hyprland, wallpaperengine, PipeWire, waybar, kitty.
- **Background services:** Docker, containerd, Ollama, Tailscale, Avahi, Ananicy-cpp.

**Process archetypes for scheduling:**
1. **Latency-sensitive interactive:** Hyprland, kitty, browser UI threads, PipeWire.
2. **Bursty agent orchestrators:** Codex/Claude Code/Kimi main processes (wake, spawn, wait on I/O/LLM).
3. **CPU-bound batch workers:** pytest, Vite builds, headless Chromium renderers, Python fuzzing.
4. **I/O-bound / idle background:** Docker, Ollama, wallpaperengine.

This is a **mixed desktop + throughput workload** where interactive responsiveness must stay good despite constant CPU saturation from background agents.

---

## 4. Bottleneck Analysis

### 4.1 Memory pressure is the primary bottleneck

- RAM: 16 GB.
- Swap used: **46 GB out of 47.5 GB** (15.5 GB zram full + 31.3 GB disk swap active).
- zram is doing useful work (15.2 GB data compressed to 4.6 GB), but it is full and the system has spilled to slow disk swap.

**Implication:** Agent harnesses spawn hundreds of Node/Python/Chromium processes. With only 16 GB RAM the kernel is constantly reclaiming and swapping. No scheduler or governor tweak will fix this; the only complete fix is more physical RAM.

### 4.2 SMT disabled reduces thread parallelism

The i9-10900KF is capable of 20 threads with Hyper-Threading. It is currently limited to 10. For highly parallel agent workloads this cuts aggregate throughput roughly 20–30%. However, disabling SMT can improve per-core latency consistency (fewer shared-resource collisions), which is why some low-latency guides recommend it.

**Trade-off for this workload:** more threads help agent parallelism; disabling SMT helps interactive latency. With only 10 cores already 100% loaded, re-enabling SMT is likely a net win for throughput.

### 4.3 Governor = schedutil under sustained load

`schedutil` ramps frequency based on utilization. Under 100% load it already hits 5 GHz, so switching to `performance` will not raise peak frequency. It will, however, eliminate governor polling latency and keep clocks flat, reducing micro-jitter for the interactive threads. Low risk, small but positive effect.

### 4.4 Default kernel scheduler is acceptable but not optimal for mixed load

CachyOS default EEVDF+BORE is well tuned. For a desktop saturated with background batch work while interactive threads still need low latency, a sched-ext scheduler designed for mixed workloads can provide better tail latency and fewer stalls. `scx_flow` is explicitly designed for this exact pattern.

---

## 5. Scheduler Recommendation

### 5.1 Why `scx_flow`

From the CachyOS sched-ext guide (2026-06-17):

> scx_flow is a budget-based scheduler … Use cases: General-purpose desktop and workstation multitasking; Gaming with background applications open; **Development work with builds, tests, or containers running**; Any scenario where interactive responsiveness under mixed load matters.

This matches the current workload exactly:
- Agent orchestrators and UI threads are bursty → keep budget, get express-lane wakeups.
- pytest / builds / headless Chromium are CPU hogs → drain budget and settle into the deficit tier, still making progress.
- Rotating tier dispatch prevents starvation or priority inversion.

### 5.2 Alternatives considered

| Scheduler | Best for | Why not first choice here |
|-----------|----------|---------------------------|
| Default EEVDF/BORE | General throughput | Already active; good but not specialized for saturated mixed load. |
| `scx_bpfland` | Gaming / interactive desktop | Excellent, but `scx_flow` is explicitly aimed at dev/build/test mixed load. |
| `scx_lavd` | Latency-critical gaming/audio | `--performance` mode is viable, but over-tuned for gaming; core compaction may not help under 100% load. |
| `scx_rusty` | Many-core cache locality / server | Good for 32C+ servers; on 10C the locality win is smaller. |
| `scx_cake` | Gaming tier classification | Experimental and gaming-focused; not the best fit. |
| BMQ / PDS kernels | Historical gaming schedulers | Less maintained, not recommended by CachyOS maintainers. |

### 5.3 Recommendation

**Primary:** `scx_flow` with `scx_loader` auto-start on boot.  
**Fallback if instability:** revert to default EEVDF/BORE or try `scx_bpfland -m performance -w`.

---

## 6. In-Flight Optimization Script (No Reboot Required)

Because root privileges are required for system-level tuning, all in-flight changes are packaged in an executable script. Run it once with `sudo`:

```bash
sudo /workspace/.files/scripts/optimize-multiagent-swarm.sh
```

To revert every change later:

```bash
sudo /workspace/.files/scripts/optimize-multiagent-swarm.sh --revert
```

### What the script does

1. **VM / memory tuning** — writes `/etc/sysctl.d/99-multiagent-swarm.conf` and applies it:
   - `vm.swappiness = 100` (down from CachyOS default 150)
   - `vm.watermark_scale_factor = 125` (up from 10)
   - `vm.dirty_ratio = 20`, `vm.dirty_background_ratio = 10` (up from 10/5)
   - Pins CachyOS defaults `vm.vfs_cache_pressure = 50` and `vm.page-cluster = 0`

2. **CPU governor** — switches from `schedutil` to `performance`.

3. **Ananicy-cpp rules** — writes `/etc/ananicy.d/99-multiagent-swarm.rules` with priority boosts for `kimi`, `kimi-code`, `codex`, `claude`, and deprioritizes `linux-wallpaperengine` and `pytest`. The rules remain on disk but **ananicy-cpp is stopped** while `scx_flow` is active (see below).

4. **sched-ext scheduler** — configures `scx_loader` to auto-start `scx_flow` on boot and starts it now. The kernel default EEVDF/BORE scheduler is replaced in userspace; no reboot or kernel rebuild needed.

5. **irqbalance** — installs (if missing) and enables `irqbalance.service` to distribute device interrupts across cores.

### Why ananicy-cpp is stopped

The CachyOS sched-ext documentation warns that auto-nice daemons such as `ananicy-cpp` can conflict with sched-ext schedulers and are a common cause of stalls or crashes. Therefore the script stops `ananicy-cpp` while `scx_flow` is active. The custom rules file is kept in place so that if you ever disable `scx_loader` and revert to the default scheduler, you can re-enable `ananicy-cpp` and the agent priorities are already configured.

---

## 7. Recommendations Requiring Reboot or BIOS Access

### 7.1 Hardware: add RAM (highest impact)

16 GB is insufficient for 30+ agent harnesses + browsers + dev servers. Target **64 GB DDR4** (4×16 GB or 2×32 GB). This is the single biggest upgrade possible.

### 7.2 BIOS / UEFI settings

Enter BIOS (Del/F2 on ASUS/AMI boards) and adjust:

| Setting | Current (inferred) | Recommended | Rationale |
|---------|-------------------|-------------|-----------|
| SMT / Hyper-Threading | Disabled | **Re-enable** | Doubles logical CPUs to 20, big win for parallel agent work. |
| CPU power profile | Likely balanced | **Performance / Max Performance** | Keeps clocks flat, reduces jitter. |
| Intel Turbo Boost | Enabled | **Keep enabled** | Already working; peak 5 GHz is useful. |
| C-States | Unknown | **Limit C3/C6, keep C1E** | Deep C-states add wake latency. For a desktop workstation, disable C6/C7/C8; keep C1E for reasonable idle power. |
| Intel SpeedStep (EIST) | Unknown | **Keep enabled** | Modern governors handle this fine; disabling is usually unnecessary on CachyOS. |
| Resizable BAR / Above 4G Decoding | Unknown | **Enable** if available | Helps GPU throughput, minor bonus. |
| XMP / DOCP | Unknown | **Enable** | Ensure RAM runs at rated speed/timings. |

**Caveat:** re-enabling SMT may slightly worsen worst-case latency for the interactive thread, but on a 10-core chip the throughput gain for parallel agents outweighs this. Test and compare.

### 7.3 Kernel command-line additions for next boot

Edit `/etc/default/grub` (or use CachyOS Kernel Manager) and append to `GRUB_CMDLINE_LINUX_DEFAULT`:

```
intel_pstate=passive
```

(Already effectively passive, but making it explicit avoids future surprises.)

Optional further tweaks (measure before/after):

```
rcupdate.rcu_normal_after_boot=1 rcutree.enable_rcu_lazy=1
```

Then regenerate grub config:

```bash
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

### 7.4 Consider a dedicated BORE kernel

If sched-ext proves unstable, install `linux-cachyos-bore` and boot it. BORE is tuned for burst responsiveness and is CachyOS's gaming/low-latency default. For this workload it is a reasonable fallback behind `scx_flow`.

---

## 8. Monitoring & Validation

After applying changes, run the verification script:

```bash
/workspace/.files/scripts/verify-multiagent-swarm.sh
```

Or watch specific metrics:

```bash
# Scheduler active?
scxctl status
journalctl -u scx_loader.service -f

# Governor locked?
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort | uniq -c

# Memory pressure?
free -h
vmstat 1

# Swap activity?
sar -S 1   # or: watch -n1 'cat /proc/vmstat | grep -E "pswpin|pswpout"'

# Scheduler latency (install schbench)
sudo pacman -S schbench
schbench -m 2 -t 8 -r 60
```

If `scx_flow` causes stalls or crashes, disable it:

```bash
sudo systemctl stop scx_loader.service
sudo systemctl disable scx_loader.service
```

The kernel falls back to the default EEVDF/BORE scheduler automatically.

---

## 9. Summary of Priority

| Priority | Action | Expected Impact | Status |
|----------|--------|-----------------|--------|
| 1 | **Add RAM to 32–64 GB** | Massive reduction in swap thrashing; largest possible win. | Requires hardware purchase + reboot. |
| 2 | **Re-enable SMT in BIOS** | +20–30% throughput for parallel agent work. | Requires reboot/BIOS. |
| 3 | **Run `scx_flow` scheduler** | Better responsiveness under mixed saturation. | In script; run with `sudo`. |
| 4 | **Lock governor to `performance`** | Reduced frequency jitter. | In script; run with `sudo`. |
| 5 | **Tune VM watermarks + swappiness** | Smoother memory reclamation. | In script; run with `sudo`. |
| 6 | **Add Ananicy agent rules + enable irqbalance** | Better I/O and process prioritization. | In script; run with `sudo`. |
| 7 | **Limit deep C-states in BIOS** | Lower wake latency. | Requires BIOS. |

---

## 10. References

- [CachyOS sched-ext Tutorial](https://wiki.cachyos.org/configuration/sched-ext/)
- [CachyOS Kernel Differences Discussion](https://discuss.cachyos.org/t/what-are-the-major-differences-in-the-cachyos-kernels/14173)
- [Phoronix CachyOS BORE Benchmark](https://www.phoronix.com/review/cachyos-bore)
- [CachyOS Forum: I Installed CachyOS, How Can I Get More SPEED?](https://discuss.cachyos.org/t/i-installed-cachyos-how-can-i-get-more-speed/29432)
- [Linux Basecamp Gaming Performance](https://linuxbasecamp.com/gaming/gaming-performance-optimization)
