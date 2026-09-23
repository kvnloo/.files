# PC Performance Optimization Master Report

**System:** `groot` — CachyOS Linux workstation  
**Generated:** 2026-07-03  
**Scope:** BIOS/UEFI firmware inspection, OS/kernel tuning, CPU/GPU/RAM overclocking, input/IRQ/DPC/audio latency reduction, and workload-specific optimization for the current multi-agent AI, audiophile, and development workflows.

---

## 1. Executive Summary

This report consolidates repository documentation, live system telemetry, and targeted research into a single, actionable optimization guide for an ASUS PRIME Z490-A / Intel Core i9-10900KF / NVIDIA RTX 3080 Ti / 16 GB RAM build running CachyOS.

**Top findings:**

1. **RAM is the primary bottleneck.** With 16 GB physical memory the system is already swap-thrashing under the current workload (multiple Kimi/Codex/Claude agent processes, Zen Browser, Python pytest, Rust builds, Wallpaper Engine, Hyprland). **Upgrade to 32–64 GB DDR4-3600+ with tight timings** is the single biggest quality-of-life improvement.
2. **SMT is disabled in firmware.** The i9-10900KF is operating as 10C/10T instead of 10C/20T. For the current throughput-heavy agent workloads, re-enabling Hyper-Threading is strongly recommended.
3. **CPU governor is `schedutil`, not `performance`.** The `scx_loader` service is disabled and `ananicy-cpp` is running without a sched-ext scheduler. Switching to `performance` governor and enabling `scx_flow` (or `scx_lavd` for interactive/gaming latency) provides immediate gains.
4. **Kernel cmdline is conservative.** `zswap.enabled=0 nowatchdog quiet splash` disables the watchdog and zswap, but omits C-state limits, `intel_pstate=passive`, `threadirqs`, and optional latency parameters.
5. **A working UEFI hidden-settings inspector was created.** `scripts/uefi-hidden-settings-inspector.py` parses the AMI NVAR `StdDefaults` variable and diffs it against live NVRAM, showing 15 setup variables with non-default byte values.
6. **No root access was available during this session**, so kernel-level changes are provided as scripts/commands for the user to run with `sudo`.

**Immediate, safe wins (user can apply now):**

- Run `sudo cpupower frequency-set -g performance`
- Run `scripts/optimize-multiagent-swarm.sh` (from the repo)
- Add `intel_pstate=passive threadirqs` to kernel cmdline
- Enable `scx_loader` with `scx_flow`
- Apply Rust/Cargo `target-cpu=native` and dev-env threading limits

**Bigger wins requiring hardware purchase or BIOS changes:**

- Upgrade RAM to 32–64 GB
- Re-enable SMT in BIOS
- Tune XMP/DOCP and Resizable BAR
- Set CPU multiplier / cache / ring / VCCIO / VCCSA for memory overclocking
- Undervolt GPU via `nvidia-settings` CoolBits

---

## 2. Hardware Profile

| Component | Detected | Notes |
|---|---|---|
| **Motherboard** | ASUS PRIME Z490-A, BIOS 2601 (2022-05-17) | AMI Aptio UEFI. BIOS write-protect / BIOS Lock status unknown. |
| **CPU** | Intel Core i9-10900KF (Comet Lake, 10C20T capable) | Currently 10C/10T (SMT disabled). Max turbo 5.3 GHz, all-core ~5.0 GHz. Running at 5.0 GHz under load. |
| **RAM** | 16 GB total (15.5 GiB usable) | Single-rank? Exact DIMM count/speed/timings need `sudo dmidecode -t 17`. This is the bottleneck. |
| **GPU** | NVIDIA GeForce RTX 3080 Ti 12 GB | Driver 610.43.02. Current P3 state, 103 W / 350 W, 20% VRAM used. |
| **Storage** | Samsung SSD 960 EVO 500 GB NVMe (root+workspace XFS) | Root 79% full, workspace 74% full. I/O scheduler `none`. Mount options include `noatime,lazytime`. |
| **Secondary storage** | 4 TB WD Blue SATA SSD (Ubuntu/ZFS fallback), 3 TB Toshiba HDD, 500 GB Samsung 850 EVO | Not mounted in CachyOS session. |
| **Network** | Intel I225-V Ethernet, Intel Wi-Fi 6 AX200 | Wired recommended for low latency. |
| **Displays** | ASUS ROG PG248QP 540 Hz (primary, DP-1) | 1920×1080@540.16 Hz. |
| | AOP 25XV2Q F 240 Hz (portrait, DP-2) | 1920×1080@239.96 Hz. |
| | Dell S3222HN 75 Hz (HDMI-A-1) | Secondary. |
| **Audio** | Topping DX5 USB DAC | PipeWire bit-perfect chain with AutoEQ/BRIR/LSP/ZaMaximX2. Blue Snowball USB mic. |
| **Input** | Wooting 60HE (USB), unknown mouse | Wooting is hall-effect/analog; supports high polling rate. |

---

## 3. Current State Snapshot

### 3.1 OS & kernel

```
Linux groot 7.1.2-3-cachyos #1 SMP PREEMPT_DYNAMIC
CachyOS Linux (Arch-based rolling)
Kernel cmdline: initrd=\initramfs-linux-cachyos.img root=UUID=... rw zswap.enabled=0 nowatchdog quiet splash
```

### 3.2 CPU governor

```
scaling_driver: intel_cpufreq
governor: schedutil on all 10 cores
available: conservative ondemand userspace powersave performance schedutil
```

### 3.3 Scheduler services

| Service | Status |
|---|---|
| `scx_loader` | disabled, inactive |
| `ananicy-cpp` | enabled, running |
| `irqbalance` | not checked (enable for multi-core IRQ spreading) |

### 3.4 Memory / swap

```
Mem: 15.5 GiB total, 6.1 GiB used, 4.5 GiB available
Swap: 47.5 GiB total (15.5 GiB zstd zram + 32 GiB disk), 7.0 GiB used
vm.swappiness = 150
vm.vfs_cache_pressure = 50
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
vm.page-cluster = 0
```

**Interpretation:** The combination of low `MemAvailable` (4.5 GB) and 7 GB swap-in-use confirms memory pressure. `vm.swappiness=150` is an aggressive zram-preferring value; with 16 GB physical RAM this is appropriate for zram but the real fix is more RAM.

### 3.5 GPU

```
NVIDIA RTX 3080 Ti, driver 610.43.02
P3 state, 103 W / 350 W, memory 5001 MHz (max 9501 MHz)
GPU util: 41%
VRAM used: 1224 / 12288 MiB
```

GPU is far from thermal or power limits. There is headroom for overclocking/undervolting.

### 3.6 Storage mount options

```
/dev/nvme0n1p1 /     xfs rw,noatime,lazytime,inode64,logbufs=8,logbsize=32k,noquota
/dev/nvme0n1p3 /workspace xfs rw,noatime,lazytime,inode64,logbufs=8,logbsize=256k,noquota
```

Good base options, but `logbsize=32k` on root could be raised to 256k for NVMe. `allocsize` not set.

### 3.7 Audio

```
PipeWire 1.6.7 + WirePlumber
Default sink: effect_input.headphone_dsp_room
PipeWire RT prio: 88
limits: @pipewire rtprio 95 / nice -19 / memlock unlimited
kernel param: threadirqs (recommended)
```

Audio stack is already well tuned for low latency.

---

## 4. Workload Analysis (Live Processes)

Top CPU consumers at time of inspection:

| %CPU | Process | What it is |
|---|---|---|
| 131% | `python -m pytest ...` | Test runner for `backend/falsification/test_rd001_regime_calibration.py` |
| 95% | `target/debug/market-native-ui` | Rust GUI (probably `market-native-ui` product) |
| 49% | `Hyprland` | Wayland compositor |
| 31% | `kimi` | Kimi AI agent |
| 17% | `zen-bin` (main) | Zen Browser |
| 17% | `kimi` (second instance) | Kimi AI agent |
| 7% | Zen content process | Browser renderer |
| 6% | `claude` | Claude Code |
| 5% | `codex` | Codex agent |
| 4% | `kitty` | Terminal |
| 4% | `linux-wallpaperengine` (×2) | Animated wallpapers on DP-1/DP-2 |

Top memory consumers:

| %MEM | Process | Notes |
|---|---|---|
| 2.3% | `zen-bin` (main) | Browser main process |
| 2.3% | `kimi` | AI agent |
| 1.9% | `kimi` | AI agent |
| 1.8% | `market-native-ui` | Rust GUI |
| 1.6% | `python -m pytest` | Test runner |
| 1.2% | `kimi` | AI agent |
| 1.1% | `codex` | AI agent |
| 1.1% | Zen content process | Browser renderer |
| 1.1% | `kimi` | AI agent |

**Workload fingerprint:**

- Heavy **multi-agent AI orchestration** (Kimi/Codex/Claude multiple windows)
- **Rust development** (market-native-ui, cargo builds)
- **Python data/quant development** (pytest, numpy/pandas)
- **Web browsing** (Zen Browser with many content processes)
- **Audiophile music playback** through real-time DSP chain
- **Triple-monitor desktop** with animated wallpapers

This is a throughput + interactivity mix. The system needs:

1. More RAM to stop swap pressure.
2. More threads (re-enable SMT) for parallel agents.
3. Low-latency scheduling for the compositor, audio, and input.
4. Fast storage I/O for Rust/Python builds and agent I/O.

---

## 5. Bottleneck Diagnosis

| Bottleneck | Severity | Evidence | Fix |
|---|---|---|---|
| **RAM capacity** | Critical | 7 GB swap used, 4.5 GB MemAvailable | Upgrade to 32–64 GB |
| **SMT disabled** | High | `/proc/cpuinfo` shows `siblings=10` | Enable Hyper-Threading in BIOS |
| **CPU governor schedutil** | Medium | Governor `schedutil` under load | Set `performance` |
| **scx_loader disabled** | Medium | `scx_flow`/`scx_lavd` not active | Enable sched-ext scheduler |
| **Kernel cmdline missing latency params** | Medium | No `threadirqs`, `intel_pstate=passive`, C-state limits | Edit bootloader |
| **GPU not tuned** | Low-Medium | P3 state, stock clocks | Undervolt/overclock with CoolBits |
| **Root filesystem 79% full** | Low | 22 GB free left | Clean up or expand |
| **Hyprland high CPU** | Low | 49% CPU on compositor | Review effects/wallpapers/direct scanout |

---

## 6. BIOS / UEFI Optimization

### 6.1 Visible BIOS settings (ASUS PRIME Z490-A)

Enter BIOS with `Del`/`F2` during POST. Recommended settings:

| Menu / Setting | Recommended | Rationale |
|---|---|---|
| **Advanced → CPU Configuration → Hyper-Threading** | **Enabled** | Doubles logical threads to 20; massive for agent builds. |
| **Advanced → CPU Configuration → Active Cores** | All | — |
| **Advanced → CPU Configuration → Intel SpeedStep** | Enabled | Modern governors handle transitions fine. |
| **Advanced → CPU Configuration → Turbo Mode** | Enabled | Peak 5.3 GHz single-core. |
| **Advanced → CPU Configuration → CPU C-States** | **Disabled** or limit to C1/C1E | Deep C-states add wake latency. |
| **Advanced → CPU Configuration → CFG Lock** | Disabled if present | Allows OS/MSR control of power limits (hidden on many ASUS boards; see §6.3). |
| **Advanced → AI Tweaker → AI Overclock Tuner** | XMP I or XMP II | Runs RAM at rated speed/timings. |
| **Advanced → AI Tweaker → DRAM Frequency** | Rated speed (e.g., DDR4-3600+) | Match XMP profile. |
| **Advanced → AI Tweaker → DRAM Timing Control** | Use XMP, then tighten | Primary timings CAS-tRCD-tRP-tRAS, tRRDS/tRRDL/tFAW, tWR, tRFC. |
| **Advanced → AI Tweaker → VCCIO / VCCSA** | Auto or manual per memory OC | Needed for high-frequency RAM stability. |
| **Advanced → System Agent → Above 4G Decoding** | Enabled | Required for Resizable BAR. |
| **Advanced → System Agent → Re-Size BAR Support** | Enabled | Minor GPU throughput boost. |
| **Advanced → System Agent → VT-d** | Enabled if using PCI passthrough / IOMMU | Required for GPU/PCI passthrough. |
| **Advanced → Onboard Devices → Wi-Fi / Bluetooth** | Disable if unused | Reduces IRQ traffic. |
| **Boot → Fast Boot** | Enabled (or Disabled for debugging) | Faster POST. |
| **Boot → CSM** | Disabled | Pure UEFI, faster boot. |

### 6.2 SceWin / AMISCE and hidden settings

**SceWin** (`SCEWIN_64.exe`) is an AMI Windows tool bundled with MSI Center that reads/writes NVRAM variables, including hidden BIOS options. It requires:

- `amifldrv64.sys` and `amigendrv64.sys` in the same folder.
- Administrator CMD.
- On newer ASUS boards: **Tool → Publish HII Resources → Enabled** in BIOS.

Typical SceWin workflow:

```cmd
SCEWIN_64.exe /o /s nvram.txt   :: export all NVRAM settings
:: edit nvram.txt
SCEWIN_64.exe /i /s nvram.txt   :: import changed settings
```

Because the primary OS is CachyOS Linux, SceWin is not directly usable. The Linux equivalent workflow is:

1. **Inspect live NVRAM variables:** `scripts/uefi-hidden-settings-inspector.py` (created in this report).
2. **Map variables to human-readable names:** extract the BIOS image and parse IFR (see §6.3).
3. **Modify individual settings:** use `setup_var.efi` from a UEFI Shell, or write variables with `efivar` from Linux (risky).
4. **Full GUI-style editing:** boot a Windows PE or dual-boot Windows and use SceWin/AMISCE.

### 6.3 Firmware dumping and IFR extraction

To see **all** modified hidden settings with names:

1. **Dump SPI flash** (needs `sudo`):
   ```bash
   sudo chipsec_util spi dump bios.bin
   # or
   sudo flashrom -p internal -r bios.bin
   ```
2. **Open in UEFITool** and locate the `SetupUtility` DxeDriver.
3. **Extract the Setup PE32 body** as `Setup.bin`.
4. **Extract IFR**:
   ```bash
   ifrextractor-rs Setup.bin   # produces Setup.txt
   ```
5. **Cross-reference** the offsets from `uefi-hidden-settings-diff.md` with `Setup.txt` to identify each changed setting.

Install the required tools with:

```bash
yay -S --needed chipsec-git uefitool-ng-bin ifrextractor-rs-bin
```

### 6.4 UEFI hidden settings inspector results

Running `python3 scripts/uefi-hidden-settings-inspector.py diff` produced:

- **24 default entries parsed** from `StdDefaults` (22,027 bytes).
- **24 current variables matched**.
- **15 variables have byte differences** from factory defaults.

The changed variables include:

- `Setup` (ASUS main setup)
- `SetupCpuFeatures`
- `CpuSetup`
- `SaSetup`
- `PchSetup`
- `ASUSAiSetup`
- `AsusFanSetupFeatures`
- `AsusHwmSetupOneof`
- `AsusQFanSetupData`
- and others.

Full byte-level diff is written to `uefi-hidden-settings-diff.md` when the script runs. Without IFR extraction, the exact setting names are not known, but the offsets are available for cross-reference.

**Important:** Changing NVRAM variables can brick the board. Always:

- Dump the current BIOS/NVRAM before modifications.
- Change one setting at a time.
- Have a way to clear CMOS / reflash.

### 6.5 Comet Lake-specific BIOS tuning

For i9-10900KF on Z490:

- **Cache/Ring ratio:** Set to 47–49× (depends on silicon). Lower than core ratio improves thermals.
- **VCCIO / VCCSA:** Auto usually works up to DDR4-3600. For 4000+ or tight timings, try 1.15–1.25 V VCCIO and 1.20–1.30 V VCCSA, then stability-test.
- **CPU VCore:** If overclocking all-core, 1.30–1.35 V for 5.0–5.1 GHz is typical. Use LLC level 4–6 on ASUS.
- **AVX offset:** -1 or -2 if thermals are a concern.
- **Power limits:** Set PL1/PL2 to motherboard limits (max current) for sustained turbo.

---

## 7. OS / Kernel Optimization

### 7.1 Recommended kernel command line

Edit `/etc/default/grub` or `/boot/loader/entries/*.conf` (systemd-boot) and add to the `linux` line:

```bash
intel_pstate=passive
threadirqs
processor.max_cstate=1
intel_idle.max_cstate=1
rcupdate.rcu_normal_after_boot=1
rcutree.enable_rcu_lazy=1
mitigations=off
# Optional, more aggressive:
# isolcpus=9 nohz_full=9 rcu_nocbs=9
```

For CachyOS with GRUB:

```bash
sudo nano /etc/default/grub
# add to GRUB_CMDLINE_LINUX_DEFAULT="..."
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

Parameter rationale:

| Parameter | Effect |
|---|---|
| `intel_pstate=passive` | Disables active P-state governor; allows `acpi-cpufreq`/`cpufreq` performance governor to work deterministically. |
| `threadirqs` | Forces threaded interrupt handlers, reducing worst-case ISR latency. |
| `processor.max_cstate=1` | Limits CPU package C-states to C1, reducing wake latency. |
| `intel_idle.max_cstate=1` | Limits core C-states. |
| `mitigations=off` | Disables speculative-execution mitigations for performance (security trade-off). |
| `isolcpus=9` | Isolates CPU 9 for low-latency audio/RT tasks. |
| `nohz_full=9` | Disables scheduler tick on isolated core. |
| `rcu_nocbs=9` | Offloads RCU callbacks from isolated core. |

### 7.2 CPU governor and frequency

Set at runtime:

```bash
sudo cpupower frequency-set -g performance
```

Persist with a systemd service. The repo already has logic in `scripts/optimize-multiagent-swarm.sh`.

Verify:

```bash
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort | uniq -c
```

### 7.3 sched-ext scheduler selection

CachyOS supports sched-ext BPF schedulers. Current recommendation for this mixed workload:

- **`scx_flow`** — good balance of throughput and interactivity; the repo already configures this.
- **`scx_lavd`** — Valve's latency-aware scheduler, excellent for gaming/interactivity (may use more CPU in performance mode on hybrid CPUs; not an issue here since Comet Lake is homogeneous).
- **`scx_bpfland`** — responsive desktop scheduler.

Enable:

```bash
sudo systemctl disable --now ananicy-cpp.service
sudo systemctl enable --now scx_loader.service
sudo tee /etc/scx_loader/config.toml <<'EOF'
default_sched = "scx_flow"
default_mode = "Auto"
EOF
```

For maximum gaming/input latency, try:

```toml
default_sched = "scx_lavd"
[scheds.scx_lavd]
auto_mode = ["--autopilot"]
```

### 7.4 IRQ and DPC latency

Current state:

- `irqbalance` not checked; should be enabled on 10-core system.
- `threadirqs` not in kernel cmdline.
- High `CAL` (function call interrupts) and `RES` (reschedule) counts indicate busy scheduling.

Actions:

```bash
sudo systemctl enable --now irqbalance.service
```

Add `threadirqs` to kernel cmdline.

For extreme latency, pin critical IRQs (USB controller for mouse/keyboard, GPU, NVMe, audio) away from CPU 0 and onto dedicated cores:

```bash
# Example: move USB controller IRQs to CPU 2
for irq in $(grep -E 'xhci_hcd|ehci_hcd' /proc/interrupts | awk -F: '{print $1}'); do
    sudo echo 4 > /proc/irq/$irq/smp_affinity
    sudo echo 2 > /proc/irq/$irq/smp_affinity_list
done
```

Measure DPC/ISR latency with:

```bash
sudo cyclictest -m -S -p 90 -i 200 -n -h 500 -l 100000
# or
sudo rtla osnoise -c 0-9 -d 60
```

Install:

```bash
sudo pacman -S rt-tests rtla
```

### 7.5 Timer resolution

With `nohz_full` on an isolated core, the scheduler tick is removed. For the rest of the system, modern Linux uses `hrtimer` (high-resolution timers) automatically. No further tuning needed unless running a real-time audio/gaming loop on an isolated core.

---

## 8. Memory & Swap

### 8.1 RAM upgrade

**This is the #1 hardware upgrade.** Current 16 GB is insufficient for:

- Multiple AI agent processes (each Kimi/Claude/Codex window can be 100–500 MB+)
- Rust builds (`market-native-ui` debug build + incremental artifacts)
- Python data workloads
- Browser with many content processes
- PipeWire DSP + Wallpaper Engine

**Recommendation:** Install 32 GB (2×16 GB) or 64 GB (2×32 GB) DDR4-3600 CL16–18. If buying new, DDR4-4000 CL18+ can be worthwhile if the IMC and motherboard handle it, but DDR4-3600 CL16 is the sweet spot for Z490/Comet Lake.

### 8.2 Current zram/swap tuning

The repo already uses zram with zstd. Current `vm.swappiness=150` is correct for zram-preferring behavior on a memory-constrained system. However, with more RAM, lower it:

```bash
# For 16 GB current
vm.swappiness = 150
vm.vfs_cache_pressure = 50
vm.page-cluster = 0
vm.dirty_ratio = 20
vm.dirty_background_ratio = 10
vm.watermark_scale_factor = 125

# For 32+ GB
vm.swappiness = 100
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
```

The repo's `scripts/optimize-multiagent-swarm.sh` already applies a good 16 GB profile.

### 8.3 Memory overclocking

If XMP is not enabled:

1. Enter BIOS → AI Tweaker → AI Overclock Tuner → XMP I.
2. Verify with:
   ```bash
   sudo dmidecode -t 17 | grep -E 'Speed|Configured|Voltage'
   # or
   inxi -m
   ```
3. Stress-test memory:
   ```bash
   sudo pacman -S memtest86+    # bootable
   # or within Linux (limited):
   stress-ng --vm 4 --vm-bytes 80% --vm-keep -t 600
   ```

### 8.4 Huge pages

For large Rust/Python/agent workloads, enable transparent huge pages:

```bash
echo always > /sys/kernel/mm/transparent_hugepage/enabled
```

Or add to kernel cmdline:

```bash
transparent_hugepage=always
```

For databases or large monolithic allocations, static huge pages can help:

```bash
echo 1024 > /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages
```

---

## 9. Storage & Filesystem

### 9.1 NVMe I/O scheduler

Already set to `none` (correct for NVMe). Verify:

```bash
cat /sys/block/nvme0n1/queue/scheduler
```

### 9.2 XFS mount options

Current `/workspace` uses good options. Consider adding `allocsize=256k` for build workloads:

```bash
/dev/nvme0n1p3 /workspace xfs rw,noatime,lazytime,inode64,logbufs=8,logbsize=256k,allocsize=256k,noquota 0 0
```

For the root partition, raise `logbsize` to 256k:

```bash
/dev/nvme0n1p1 / xfs rw,noatime,lazytime,inode64,logbufs=8,logbsize=256k,noquota 0 0
```

### 9.3 Filesystem allocation groups

For the 4 TB WD Blue SSD (if formatted XFS), use more allocation groups:

```bash
mkfs.xfs -d agcount=32 /dev/sda4
```

### 9.4 Disk cleanup

Root is 79% full. Clean old logs, caches, and build artifacts:

```bash
sudo journalctl --vacuum-time=7d
sudo pacman -Sc
rm -rf ~/.cache/yay/*
# Rust target dirs
find /workspace -type d -name target -exec du -sh {} \; | sort -h | tail
```

---

## 10. GPU Optimization (NVIDIA RTX 3080 Ti)

### 10.1 Enable CoolBits

Create `/etc/X11/xorg.conf.d/20-nvidia.conf` or edit the existing Xorg config:

```bash
Section "Device"
    Identifier     "NVIDIA GPU"
    Driver         "nvidia"
    VendorName     "NVIDIA Corporation"
    BoardName      "GeForce RTX 3080 Ti"
    Option         "Coolbits" "28"
    Option         "TripleBuffer" "false"
EndSection
```

`Coolbits=28` enables overclocking, fan control, and thermal monitoring.

### 10.2 Overclock / undervolt

After CoolBits and reboot, use `nvidia-settings`:

```bash
nvidia-settings -a '[gpu:0]/GPUPowerMizerMode=1'        # prefer maximum performance
nvidia-settings -a '[gpu:0]/GPUGraphicsClockOffsetAllPerformanceLevels=-150'
nvidia-settings -a '[gpu:0]/GPUMemoryTransferRateOffsetAllPerformanceLevels=500'
nvidia-settings -a '[gpu:0]/GPUFanControlState=1'
nidia-settings -a '[fan:0]/GPUTargetFanSpeed=70'
```

For a manual voltage-frequency curve on Linux, use a wrapper like `nvidia-vfio` or the open-source `nvidia-undervolt` / `gwe` (GreenWithEnvy) tools. However, full VF curve editing is still limited on Linux compared to Windows MSI Afterburner.

### 10.3 Wayland/NVIDIA settings

For Hyprland on NVIDIA:

```bash
# In ~/.config/hyprland/hyprland.conf
general {
    allow_tearing = true    # for lowest latency in fullscreen games
}
```

Set environment variables:

```bash
env = GBM_BACKEND,nvidia-drm
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
env = WLR_NO_HARDWARE_CURSORS,1
env = __GL_SYNC_TO_VBLANK,0
```

`__GL_SYNC_TO_VBLANK=0` disables vblank syncing for OpenGL; use only if tearing is acceptable or in fullscreen with `allow_tearing`.

### 10.4 Resizable BAR

Enable in BIOS and verify:

```bash
lspci -vv -s 01:00.0 | grep -i "resizable"
```

---

## 11. Input Latency

### 11.1 USB polling rate

Wooting 60HE supports 1000 Hz polling (and higher via Rappy Snappy / Wootility). Verify current polling:

```bash
lsusb -v -d 31e3: | grep -i "bInterval"
```

For generic USB devices, forced 1000 Hz requires kernel patch or `usbhid` quirk. Gaming mice usually advertise 1000 Hz already.

### 11.2 HID settings

Check current mouse polling:

```bash
cat /sys/bus/usb/devices/*/product | grep -i mouse
for d in /sys/bus/usb/devices/*-*; do
    [ -r "$d/product" ] && grep -qi mouse "$d/product" && echo "$d: $(cat $d/power/control) $(cat $d/bInterval 2>/dev/null)"
done
```

Disable USB autosuspend for input devices:

```bash
sudo tee /etc/udev/rules.d/50-usb-input-low-latency.rules <<'EOF'
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{product}=="*Mouse*", ATTR{power/control}="on"
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{product}=="*Keyboard*", ATTR{power/control}="on"
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="31e3", ATTR{power/control}="on"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 11.3 Hyprland input settings

Current config already uses `accel_profile = flat`. Additional options:

```ini
input {
    kb_layout = us
    follow_mouse = 1
    sensitivity = 0
    accel_profile = flat
    force_no_accel = true
    scroll_method = no_scroll   # if unused, reduces input thread work
}

general {
    layout = dwindle
    allow_tearing = true
}

# For 540 Hz primary monitor, ensure no vsync locks compositor to lower rate
render {
    direct_scanout = true
}
```

### 11.4 Display latency

- Use DisplayPort for the 540 Hz monitor (already DP-1).
- Disable VRR/G-Sync if competitive latency is prioritized over smoothness.
- Set `direct_scanout = true` in Hyprland so fullscreen apps bypass the compositor.

---

## 12. Audio Latency

The current PipeWire setup is already highly optimized. Key checks:

```bash
# Real-time priority
pw-top -b -n 1
# Check quantum / rate / wait / busy columns

# Current default sink format
pactl list sinks | grep -A 5 "Name: \|Sample Specification:"
```

Ensure the DX5 uses bit-perfect sample-rate matching. Current WirePlumber config already sets:

```
audio.format = "S32LE"
api.alsa.period-size = 1024
api.alsa.headroom = 0
session.suspend-timeout-seconds = 0
```

For lower latency, try `period-size = 512` or `256` if no dropouts occur.

USB autosuspend for the DAC is already handled by `scripts/fix-dx5-stutter-comprehensive.sh`.

---

## 13. Display / Compositor

### 13.1 Hyprland tuning for 540 Hz

Current monitor config:

```ini
monitor = DP-1, 1920x1080@540, 3000x420, 1
monitor = DP-2, 1920x1080@240, 1920x0, 1, transform, 1
monitor = HDMI-A-1, 1920x1080@75, 0x420, 1
```

Recommended additions:

```ini
general {
    allow_tearing = true
}

render {
    direct_scanout = true
}

input {
    follow_mouse = 1
    accel_profile = flat
    force_no_accel = true
}

# Disable unneeded effects
animations {
    enabled = false
}

decoration {
    blur {
        enabled = false
    }
    drop_shadow = false
}
```

### 13.2 Wallpaper Engine overhead

`linux-wallpaperengine` is consuming ~7% CPU across two instances. For maximum performance:

- Disable wallpapers during heavy workloads, or
- Lower FPS caps from 120 to 30/60 on secondary monitors, or
- Pause wallpapers when a fullscreen app is active.

### 13.3 Kitty terminal

Current `sync_to_monitor yes` may add one frame of latency. For lowest latency:

```ini
sync_to_monitor no
repaint_delay 2
input_delay 0
```

---

## 14. Network

### 14.1 TCP tuning

Current congestion control is `cubic`. Switch to `bbr` for throughput and lower bufferbloat:

```bash
sudo modprobe tcp_bbr
sudo sysctl -w net.ipv4.tcp_congestion_control=bbr
# persist in /etc/sysctl.d/99-network.conf
```

Repo already sets:

```
net.core.somaxconn = 65535
net.ipv4.ip_local_port_range = 10000 65535
net.netfilter.nf_conntrack_max = 1048576
```

Add:

```bash
net.core.netdev_max_backlog = 65536
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 10
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.tcp_no_metrics_save = 1
```

### 14.2 IRQ affinity for network

If using the I225-V Ethernet heavily:

```bash
# Find IRQ for eth controller
grep eth0 /proc/interrupts
# Pin to CPU 8 (last core)
echo 256 > /proc/irq/<IRQ>/smp_affinity
```

### 14.3 Disable unused wireless

If always wired:

```bash
sudo systemctl stop NetworkManager-wait-online.service
sudo systemctl mask NetworkManager-wait-online.service
# or disable Wi-Fi in BIOS
```

---

## 15. Application-Specific Optimization

### 15.1 AI agents (Kimi / Codex / Claude)

Current `ananicy-cpp` rules in the repo:

```json
{ "name": "kimi", "nice": -1, "ioclass": "best-effort", "ionice": 2 }
{ "name": "kimi-code", "nice": -1, ... }
{ "name": "codex", "nice": -1, ... }
{ "name": "claude", "nice": -1, ... }
```

These are good. With sched-ext active, `ananicy-cpp` may conflict; disable it when using `scx_loader`.

Limit agent parallelism if memory is tight. Each agent window spawns worker processes. Consider:

- Closing unused agent tabs.
- Using a single agent per project.
- Setting `NODE_OPTIONS=--max-old-space-size=4096` for Node-based agents.

### 15.2 Rust builds

Create `~/.cargo/config.toml`:

```toml
[build]
rustflags = ["-C", "target-cpu=native", "-C", "link-arg=-fuse-ld=mold"]

[target.x86_64-unknown-linux-gnu]
linker = "clang"
rustflags = ["-C", "link-arg=-fuse-ld=mold", "-C", "target-cpu=native"]
```

Use `mold` or `lld` linker:

```bash
sudo pacman -S mold
```

For release builds:

```bash
cargo build --release --config 'profile.release.lto=true' --config 'profile.release.codegen-units=1'
```

### 15.3 Python / pytest / numpy

Set OpenBLAS/MKL thread limits to avoid oversubscription:

```bash
export OPENBLAS_NUM_THREADS=10
export MKL_NUM_THREADS=10
export NUMEXPR_NUM_THREADS=10
export OMP_NUM_THREADS=10
export VECLIB_MAXIMUM_THREADS=10
```

For pytest:

```bash
pytest -n auto --maxprocesses=10
```

### 15.4 Browsers

Zen Browser / Firefox performance flags (`~/.config/zen/zen.cfg` or `user.js`):

```javascript
user_pref("browser.cache.disk.enable", false);
user_pref("browser.cache.memory.enable", true);
user_pref("browser.sessionstore.interval", 300000);
user_pref("dom.ipc.processCount", 8);
user_pref("media.hardware-video-decoding.enabled", true);
```

Limit content processes if memory is tight:

```javascript
user_pref("dom.ipc.processCount", 4);
```

### 15.5 Docker / containers

If running many agent containers, use cgroup v2 limits:

```bash
# Example: limit container to 4 CPUs and 8 GB
sudo docker run --cpus=4 --memory=8g --memory-swap=8g ...
```

Use `podman` rootless to reduce daemon overhead, or tune `dockerd`:

```bash
/usr/bin/dockerd --max-concurrent-downloads=10 --max-concurrent-uploads=10
```

---

## 16. Windows Dual-Boot Notes

If Windows is installed on the Toshiba/SSD dual-boot partition:

- Use SceWin/AMISCE on Windows to inspect hidden BIOS settings.
- Apply Ultimate Performance power plan:
  ```powershell
  powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61
  ```
- Disable HPET, fullscreen optimizations, and game mode per competitive-gaming guides.
- Use MSI Afterburner for GPU undervolt/OC on Windows.

---

## 17. Verification & Monitoring

### 17.1 Verification checklist

After applying changes, verify:

```bash
# Governor
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do cat $cpu; done | sort | uniq -c

# Scheduler
systemctl is-active scx_loader
scxctl status

# IRQ balance
systemctl is-active irqbalance

# Kernel params
cat /proc/cmdline

# Memory
free -h
swapon --show
zramctl

# Storage scheduler
cat /sys/block/nvme0n1/queue/scheduler

# GPU state
nvidia-smi

# Audio latency
pw-top -b -n 1

# UEFI diff
python3 scripts/uefi-hidden-settings-inspector.py diff
```

### 17.2 Latency benchmarks

```bash
# Install
sudo pacman -S rt-tests rtla

# Cyclic latency test
sudo cyclictest -m -S -p 90 -i 200 -n -h 500 -l 100000

# OS noise analysis
sudo rtla osnoise -c 0-9 -d 60

# Interrupt latency overview
cat /proc/interrupts
```

### 17.3 Continuous monitoring

Use `btop` or `nvtop` to watch CPU/GPU/RAM. The repo already has `scripts/verify-multiagent-swarm.sh`.

---

## 18. Action Plan

### Phase 1 — Apply now (safe, reversible, no hardware)

1. Run `sudo cpupower frequency-set -g performance`.
2. Run `scripts/optimize-multiagent-swarm.sh`.
3. Enable `scx_loader` with `scx_flow`.
4. Add `intel_pstate=passive threadirqs` to kernel cmdline and reboot.
5. Create `~/.cargo/config.toml` with `target-cpu=native` and `mold`.
6. Set Python thread env vars in `~/.zshenv` or shell profile.
7. Run `python3 scripts/uefi-hidden-settings-inspector.py diff` and review `uefi-hidden-settings-diff.md`.

### Phase 2 — BIOS changes (reboot required)

1. Enable **Hyper-Threading**.
2. Enable **XMP/DOCP**.
3. Enable **Resizable BAR / Above 4G Decoding**.
4. Limit **C-states** to C1/C1E.
5. Save profile, clear CMOS if unstable.

### Phase 3 — Hardware upgrade

1. **Install 32–64 GB DDR4-3600+ RAM.**
2. (Optional) Add a second NVMe SSD for build scratch/agent workspaces.
3. (Optional) Better CPU cooler if overclocking.

### Phase 4 — Advanced tuning

1. Extract IFR from BIOS dump and map hidden settings.
2. Modify hidden settings via `setup_var.efi` or SceWin on Windows.
3. Undervolt GPU with CoolBits / `nvidia-settings`.
4. Tune CPU cache/ring and memory secondary timings.

---

## 19. Appendices

### A. Sources and references

- [CachyOS sched-ext documentation](https://wiki.cachyos.org/configuration/sched-ext/)
- [scx_lavd scheduler](https://github.com/sched-ext/scx/tree/main/scheds/rust/scx_lavd)
- [NVIDIA Tips and tricks — ArchWiki](https://wiki.archlinux.org/title/NVIDIA/Tips_and_tricks)
- [CachyOS NVIDIA undervolting discussion](https://discuss.cachyos.org/t/undervolting-nvidia-gpu-under-wayland-and-x11/3293)
- [datasone/setup_var.efi](https://github.com/datasone/setup_var.efi)
- [ab3lkaizen/SCEHUB](https://github.com/ab3lkaizen/SCEHUB)
- [PN-Tester/NVRAMap](https://github.com/PN-Tester/NVRAMap)
- [AMI NVAR format explained (Habr)](https://habr.com/ru/articles/281901/)
- [Win-Raid SceWin guide](https://winraid.level1techs.com/t/guide-fix-scewin-for-protected-z690-z790-to-easily-modify-hidden-bios-settings/94069)

### B. Files created or updated

| File | Purpose |
|---|---|
| `scripts/uefi-hidden-settings-inspector.py` | New app: dump/diff UEFI hidden settings |
| `uefi-hidden-settings-diff.md` | Generated diff report (run the script to refresh) |
| `claudedocs/performance-optimization-master-report.md` | This report |

### C. Safety warnings

- BIOS/UEFI modifications can brick hardware. Always have a recovery method.
- `mitigations=off` improves performance but disables CPU security mitigations.
- Overclocking/undervolting can cause instability or data corruption if too aggressive.
- Always benchmark after changes; "fastest" settings are workload-dependent.
