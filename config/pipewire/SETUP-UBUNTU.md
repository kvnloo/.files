# Audio Stack Setup — Ubuntu (No Nix)

Manual setup steps for the PipeWire native filter-chain audiophile stack on Ubuntu.
These are system-level changes that require sudo and cannot be managed by dotfile symlinks alone.

## Current State

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| PipeWire version | 1.4+ | 1.5.85 | OK |
| RT scheduling | SCHED_FIFO/88 | SCHED_FIFO/88 | OK |
| pipewire group membership | kvn in pipewire | kvn in pipewire | OK |
| ulimit -r | 95 | 95 | OK |
| threadirqs kernel param | present | present | OK |
| vm.swappiness | 10 | 10 | OK |
| audio.format | S32LE | S32LE | OK |
| resample.quality | 14 | 14 | OK |
| lsp-plugins-lv2 | installed | installed | OK |
| zam-plugins | installed | installed | OK |
| bs2b-ladspa | installed | installed | OK |
| Filter-chain DSP | 3 sinks loaded | 3 sinks loaded | OK |

---

## Phase 1: Fix RT Scheduling (Critical)

PipeWire requests SCHED_FIFO priority 88, but without proper group/limits config,
it falls all the way back to SCHED_OTHER/0 — the default Linux scheduler with zero
real-time priority. This means any CPU load (browser, compilation) can cause audio
dropouts.

### 1a. Add user to pipewire group

```bash
sudo groupadd -f pipewire
sudo usermod -aG pipewire kvn
```

### 1b. Create RT scheduling limits

```bash
sudo tee /etc/security/limits.d/99-pipewire.conf << 'EOF'
# Real-time scheduling for PipeWire audio
@pipewire - rtprio 95
@pipewire - nice -19
@pipewire - memlock unlimited
EOF
```

### 1c. Reboot (or log out completely and back in)

Group changes and limits.d files only take effect on new login sessions.
A full reboot is most reliable.

### 1d. Verify

```bash
# Check group membership
groups kvn | grep -o pipewire

# Check RT limits (in a NEW terminal after relogin)
ulimit -r
# Expected: 95

# Check PipeWire scheduling (after PipeWire restarts with new session)
chrt -p $(pgrep -x pipewire)
# Expected: SCHED_FIFO priority 88

# If still SCHED_OTHER after relogin, try:
systemctl --user restart pipewire wireplumber
chrt -p $(pgrep -x pipewire)
```

---

## Phase 2: Kernel Parameters

### 2a. Add threadirqs

Forces interrupt handlers into schedulable kernel threads, reducing worst-case
interrupt latency during audio playback under system load.

```bash
# Edit GRUB config
sudo sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash threadirqs"/' /etc/default/grub

# Regenerate GRUB (Ubuntu with ZFS uses different update command)
sudo update-grub

# Reboot to apply
sudo reboot
```

Verify after reboot:
```bash
cat /proc/cmdline | grep -o threadirqs
# Expected: threadirqs
```

### 2b. Set vm.swappiness

Reduces swap aggressiveness to keep audio buffers in RAM.

```bash
# Apply immediately
sudo sysctl vm.swappiness=10

# Make persistent
echo 'vm.swappiness = 10' | sudo tee /etc/sysctl.d/99-audio.conf
```

### 2c. Disable USB autosuspend for DX5

Prevents the kernel from suspending the USB DAC during idle periods,
which would cause click/pop on wake.

```bash
# Find DX5 vendor:product ID
lsusb | grep -i topping
# Example output: Bus 001 Device 005: ID 152a:8856 Topping DX5

# Create udev rule (adjust ID if needed)
sudo tee /etc/udev/rules.d/99-topping-dx5.rules << 'EOF'
# Disable USB autosuspend for Topping DX5 DAC
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="152a", ATTR{power/autosuspend}="-1"
EOF

sudo udevadm control --reload-rules
```

---

## Phase 3: Install Required Packages

```bash
# LV2 plugins: loudness compensator, multiband compressor, parametric EQ
sudo apt install lsp-plugins-lv2

# Brickwall limiter
sudo apt install zam-plugins

# bs2b crossfeed LADSPA plugin
sudo apt install bs2b-ladspa

# Optional: audio analysis and null testing
sudo apt install sox
```

---

## Phase 4: Activate PipeWire Filter-Chain DSP

The filter-chain config defines 3 simultaneous virtual sinks:

| Sink Name | DSP Chain |
|-----------|-----------|
| Headphone DSP (clean) | AutoEQ → Loudness Comp → GentleDynamics MBC → Limiter |
| Headphone DSP + Crossfeed | AutoEQ → bs2b Crossfeed → Loudness Comp → MBC → Limiter |
| Headphone DSP + Room | AutoEQ → BRIR True Stereo → Loudness Comp → MBC → Limiter |

### 4a. Symlink configs

```bash
# WirePlumber DX5 config (S32LE format, resample.quality=14, headroom=0)
mkdir -p ~/.config/wireplumber/main.lua.d
ln -sf ~/workspace/.files/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua \
       ~/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua

# PipeWire daemon config (192kHz default, multi-rate switching)
mkdir -p ~/.config/pipewire
ln -sf ~/workspace/.files/config/pipewire/pipewire.conf \
       ~/.config/pipewire/pipewire.conf

# PipeWire filter-chain DSP (3 virtual sinks with full processing chains)
mkdir -p ~/.config/pipewire/pipewire.conf.d
ln -sf ~/workspace/.files/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf \
       ~/.config/pipewire/pipewire.conf.d/10-headphone-dsp.conf
```

### 4b. Restart PipeWire

```bash
systemctl --user restart pipewire wireplumber
```

### 4c. Set default sink

```bash
# List sinks — should show 3 "Headphone DSP" entries
wpctl status | grep -A10 "Audio/Sink"

# Use headphone-switch.sh for easy switching
~/workspace/.files/config/pipewire/headphone-switch.sh clean

# Or add to PATH and use directly:
headphone-switch.sh clean        # No spatial processing
headphone-switch.sh crossfeed    # bs2b crossfeed
headphone-switch.sh room         # BRIR room simulation
```

### 4d. Set EQ profile for your headphones

```bash
headphone-switch.sh eq hd800s    # Sennheiser HD800S
headphone-switch.sh eq monarch   # ThieAudio Monarch MKII
```

This updates the AutoEQ IR symlinks and restarts PipeWire.

---

## Phase 5: Verification

```bash
# ── RT Scheduling ──
chrt -p $(pgrep -x pipewire)
# Expected: SCHED_FIFO priority 88

# ── Filter-Chain Sinks Loaded ──
pw-cli ls Node | grep -A3 "Headphone DSP"
# Should show 3 filter-chain sink nodes

# ── PipeWire Graph Status ──
pw-top
# Check: RATE tracks source sample rate, XRUN=0, FORMAT=S32LE at DX5 node

# ── DX5 Properties ──
pw-cli info $(pw-cli ls Node | grep "Topping DX5" | head -1 | awk '{print $2}') | grep -E "resample|headroom|audio.format"
# Expected: resample.quality=14, headroom=0, audio.format=S32LE

# ── Current Headphone Profile ──
headphone-switch.sh
# Shows active sink and EQ profile

# ── Kernel Parameters ──
cat /proc/cmdline | grep threadirqs
sysctl vm.swappiness
```

---

## Packages Reference

| Package | Purpose | Required |
|---------|---------|----------|
| `lsp-plugins-lv2` | Loudness compensator, multiband compressor, parametric EQ | Yes |
| `zam-plugins` | ZaMaximX2 brickwall limiter | Yes |
| `bs2b-ladspa` | bs2b crossfeed LADSPA plugin | Yes |
| `sox` | Audio analysis and null testing | Optional |

---

## Troubleshooting

### PipeWire still SCHED_OTHER after group+limits fix
```bash
# Check if PAM is loading limits
grep pam_limits /etc/pam.d/common-session
# Should show: session required pam_limits.so

# If missing:
echo "session required pam_limits.so" | sudo tee -a /etc/pam.d/common-session
```

### Filter-chain not loading
```bash
# Check PipeWire logs
journalctl --user -u pipewire -n 50 --no-pager | grep -i -E "filter|chain|error|fail"

# Verify LV2 plugin paths
ls /usr/lib/lv2/lsp-plugins.lv2/
ls /usr/lib/lv2/ZaMaximX2.lv2/

# Check if LV2_PATH is set (needed for PipeWire to find plugins)
echo $LV2_PATH
# If empty, add to ~/.profile or ~/.bashrc:
# export LV2_PATH="/usr/lib/lv2"
```

### Xruns after headroom=0
If you hear clicks/pops after reducing headroom to 0:
```bash
# Increase headroom incrementally (edit the WirePlumber config)
# Try 256 first, then 512 if needed
# Edit: ~/workspace/.files/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua
# Change: ["api.alsa.headroom"] = 256,
# Then: systemctl --user restart pipewire wireplumber
```

### DX5 not showing up
```bash
# Restart services
systemctl --user restart pipewire wireplumber

# Check USB connection
aplay -l | grep DX5

# Verify PipeWire sees it
pactl list sinks short | grep DX5
```

### Only 1 sink showing instead of 3
```bash
# Check the filter-chain config is symlinked
ls -la ~/.config/pipewire/pipewire.conf.d/10-headphone-dsp.conf

# Check for config parse errors
journalctl --user -u pipewire -n 100 --no-pager | grep -i error

# Verify all required plugins are installed
dpkg -l | grep -E "lsp-plugins|zam-plugins|bs2b"
```
