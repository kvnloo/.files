# Ubuntu 24.04 -> CachyOS Migration Plan

> **Day-to-day setup** (new machines or re-link after clone) uses the dual onboarding
> paths in [docs/SETUP.md](../docs/SETUP.md): `./install` or the LLM harness flow in
> [AGENTS.md](../AGENTS.md). This document is the one-shot **rebuild / migration** plan.

## System Profile
- **Machine**: groot | RTX 3080 Ti | Triple 1080p (75/240/540Hz)
- **Current**: Ubuntu 24.04 LTS, i3/X11, ZFS root (encrypted), NVIDIA 580 open
- **Target**: CachyOS (Arch-based), Hyprland/Wayland, XFS root, NVIDIA 580 open

## Strategy: Safe NVMe Install (Keep Ubuntu as Fallback)

Install CachyOS on the **NVMe (Samsung 960 EVO 500GB)** -- wipe Windows data on it.
Keep **Ubuntu on SATA 4TB (WD Blue SSD)** completely untouched as safety net.
Once CachyOS is confirmed stable (1-2 weeks), optionally wipe SATA and reclaim as `/home`.

### Why This Strategy
- Zero risk to current Ubuntu system -- it stays bootable on SATA
- NVMe speed for CachyOS root + workspace (fast boots, fast builds)
- Can dual-boot back to Ubuntu via BIOS boot menu if anything goes wrong
- No need for complex backup/restore of Ubuntu -- it's still there

---

## Disk Layout

### NVMe (Samsung 960 EVO 500GB) -- Repartition for CachyOS

**Current layout** (before migration):
| Partition | Disk position | Size | FS | Label | Purpose |
|-----------|---------------|------|----|-------|---------|
| nvme0n1p1 | start | 458 GB | NTFS | fast | Windows data (back up first!) |
| nvme0n1p2 | end | 8 GB | ext4 | arch | Bootable installer (reuse for CachyOS) |

**Target layout** (after Calamares manual partitioning):

Delete p1 (NTFS). Keep p2 (installer, physically at end of disk). Create new partitions in freed space:

| Disk position | Partition | Size | FS | Mount | Purpose |
|---------------|-----------|------|----|-------|---------|
| 1st | nvme0n1p1 (new) | 1 GB | FAT32 | /boot/efi | EFI System Partition |
| 2nd | nvme0n1p3 (new) | 100 GB | XFS | / | CachyOS root |
| 3rd | nvme0n1p4 (new) | 32 GB | swap | [SWAP] | Swap (2x 16GB RAM) |
| 4th | nvme0n1p5 (new) | ~318 GB | XFS | /workspace | Dev projects (NVMe speed) |
| 5th (end) | nvme0n1p2 (keep) | 8 GB | ext4 | -- | CachyOS installer (delete later) |

Note: p2 has number "2" but sits physically at the **end** of the disk (from the original Arch layout).
After deleting p2, just extend p5 rightward -- no partition shifting needed.

### SATA 4TB (WD Blue SSD) -- UNTOUCHED (Ubuntu safety net)
- Keep all existing ZFS partitions intact
- Ubuntu remains bootable from BIOS boot menu
- After CachyOS confirmed stable: optionally wipe and format as XFS `/home`

### Other Drives -- UNTOUCHED
- sdb (3TB HDD): Windows/data
- sdc (500GB SSD): Windows/data

---

## Phase 0: Pre-Migration (On Ubuntu) -- ~20 min

### 0.1 Back Up NVMe Windows Data
```bash
./migration/00a-backup-nvme-windows.sh
```
Archives the NTFS partition (nvme0n1p1, "fast") as compressed tarball to SATA before wipe.

### 0.2 Prepare CachyOS Installer on NVMe
```bash
# Download CachyOS Desktop ISO from https://cachyos.org/download/
# Then run:
./migration/00b-prepare-nvme-installer.sh ~/Downloads/cachyos-desktop-linux-*.iso
```
Replaces the Arch ISO on nvme0n1p2 with CachyOS ISO and updates the GRUB loopboot entry.
No USB drive needed -- the installer boots from the 8GB NVMe partition directly into RAM.

### 0.3 Commit Dotfiles
```bash
cd ~/workspace/.files
git add -A
git commit -m "pre-cachyos: migration scripts and untracked configs"
git push origin dev
```

### 0.4 Pre-Flight Checklist
- [ ] NVMe Windows backup verified on SATA (`ls -lh` the archive)
- [ ] CachyOS installer on nvme0n1p2 (`lsblk /dev/nvme0n1`)
- [ ] GRUB entry visible (`grep -A5 "CachyOS" /boot/grub/grub.cfg`)
- [ ] Git remote up to date (`git log --oneline -3 origin/dev`)
- [ ] Note: Tailscale auth key, GitHub SSH keys are on SATA (safe)

---

## Phase 1: CachyOS Installation -- ~20 min

### 1.1 Boot CachyOS Installer
- Reboot and select **"CachyOS Installer (loopboot from NVMe)"** from GRUB menu
- The ISO loads entirely into RAM (`copytoram=y`), so the NVMe is free to repartition
- No USB drive needed

### 1.2 Partitioning (Manual -- CRITICAL)

**Target disk: nvme0n1 (500GB Samsung 960 EVO)**

In Calamares, select **Manual Partitioning** (never "Erase Disk"):
1. **Delete** p1 (458GB NTFS "fast") -- this frees space at the start of the disk
2. **Do NOT touch** p2 (8GB ext4 "arch") -- this is the installer, physically at the end
3. In the freed ~458GB space, create:
   - **p1**: 1 GB, FAT32, mount `/boot/efi`, flags: boot,esp
   - **p3**: 100 GB, XFS, mount `/`
   - **p4**: 32 GB, swap
   - **p5**: remaining (~318 GB), XFS, mount `/workspace`

Key points:
- XFS for root and workspace (no ZFS/DKMS headaches)
- 32GB swap (2x RAM for hibernation support)
- `/workspace` on NVMe for fast dev I/O
- **DO NOT TOUCH sda, sdb, sdc**

### 1.3 Desktop Environment
- Select **Hyprland** (CachyOS offers it in installer)
- Or select **minimal** and install via `01-install-packages.sh`

### 1.4 User Setup
- Username: `kvn`
- Hostname: `groot`
- Timezone: `America/Chicago`
- Locale: `en_US.UTF-8`

### 1.5 Bootloader
- CachyOS defaults to **systemd-boot**
- Can chainload Ubuntu GRUB from SATA EFI if needed
- Can chainload Windows from sdb/sdc EFI

---

## Phase 2: First Boot & Base Setup -- ~15 min

### 2.1 Connect to Network
```bash
nmcli device status
nmcli device connect enp4s0  # if needed
```

### 2.2 Clone Dotfiles
```bash
sudo pacman -S git
mkdir -p ~/workspace
git clone https://github.com/kvnloo/.files ~/workspace/.files
cd ~/workspace/.files
git checkout dev
git submodule update --init --recursive
```

### 2.3 Run Automation Scripts
```bash
./migration/01-install-packages.sh    # All packages (pacman + AUR + flatpak)
./migration/02-deploy-dotfiles.sh     # Symlink all configs
```

---

## Phase 3: Audio Stack -- ~10 min

```bash
./migration/03-setup-audio.sh
```

Deploys:
- PipeWire filter-chain DSP (convolver + loudness comp + limiter)
- WirePlumber 0.5 config (Topping DX5 bit-perfect)
- AutoEQ WAV files + BRIR room impulses
- Browser bypass DSP service
- Realtime-privileges group membership
- LV2/LADSPA plugin paths

Verify:
```bash
./scripts/verify-bitperfect-audio.sh
./config/pipewire/headphone-switch.sh status
```

---

## Phase 4: Hyprland & Display -- ~10 min

```bash
./migration/04-setup-hyprland.sh
```

Deploys:
- `config/hyprland/hyprland.conf` (translated from i3 config)
- `config/hyprland/hyprlock.conf` + `config/hyprland/hypridle.conf`
- `config/waybar/config.jsonc` + `config/waybar/style.css` (from polybar blocks)
- Rofi-wayland config, dunst config, pywal integration
- Monitor layout (3 displays, portrait rotation on DP-2)

Verify:
- Log out/in or `hyprctl reload`
- Check all 3 monitors: `hyprctl monitors`
- Test keybindings: `$mod+Return`, `$mod+hjkl`, `$mod+space`

---

## Phase 5: Zsh & Dev Environment -- ~10 min

```bash
./migration/06-setup-zsh.sh           # Clean zsh config for Arch
./migration/05-setup-dev-services.sh  # Dev tools + system tuning
```

---

## Phase 6: Verification -- ~5 min

```bash
./migration/07-verify-migration.sh
```

### Manual Verification Checklist

**Audio**
- [ ] `wpctl status` shows DX5 as default sink
- [ ] Three DSP sinks visible (clean/crossfeed/room)
- [ ] Play music through TIDAL -- sound through DX5
- [ ] `headphone-switch.sh` works for all modes
- [ ] Browser audio bypasses DSP (test YouTube)

**Display**
- [ ] All 3 monitors active at correct resolution/refresh
- [ ] DP-2 in portrait mode
- [ ] DP-0 at 240Hz+ (verify with `hyprctl monitors`)
- [ ] Workspace assignments correct

**Desktop**
- [ ] Hyprland keybindings work (mod+Return, mod+hjkl, etc.)
- [ ] Waybar showing (workspaces, audio, clock, etc.)
- [ ] App launcher (rofi-wayland) works
- [ ] Notifications (dunst) work
- [ ] Screenshots (grim+slurp) work
- [ ] Pywal theming applied

**Dev**
- [ ] `node --version` shows v24.x (nvm)
- [ ] `rustc --version` works (rustup)
- [ ] `python3 --version` shows 3.12+
- [ ] `docker run hello-world` works
- [ ] `claude --version` works
- [ ] VS Code / Cursor launches

**Services**
- [ ] `systemctl --user status pipewire` active
- [ ] `systemctl status docker` active
- [ ] `systemctl status tailscaled` active
- [ ] `systemctl status ollama` active

**Network**
- [ ] Internet connectivity
- [ ] Tailscale connected (`tailscale status`)
- [ ] DNS resolution working

---

## Rollback Strategy

If CachyOS fails on NVMe:
1. **Boot Ubuntu from SATA** -- select in BIOS boot menu, Ubuntu is untouched
2. **Git repo on GitHub** -- all configs are recoverable
3. **NVMe Windows backup on SATA** -- can restore Windows to NVMe if needed
4. **Worst case**: Ubuntu is still fully functional, just boot from SATA

---

## Script Execution Order

```
# ON UBUNTU (before NVMe repartition):
./migration/00a-backup-nvme-windows.sh  # Archive NVMe Windows data to SATA
./migration/00b-prepare-nvme-installer.sh ~/Downloads/cachyos*.iso  # Replace Arch ISO with CachyOS
git add -A && git commit && git push    # Save to remote

# REBOOT → Select "CachyOS Installer (loopboot from NVMe)" from GRUB
# INSTALL CACHYOS via Calamares (manual partitioning, keep p2 installer)

# ON CACHYOS (after first boot):
git clone ... ~/workspace/.files
cd ~/workspace/.files && git checkout dev

./migration/01-install-packages.sh      # All packages
./migration/02-deploy-dotfiles.sh       # Symlinks
./migration/03-setup-audio.sh           # PipeWire DSP
./migration/04-setup-hyprland.sh        # Window manager + waybar
./migration/05-setup-dev-services.sh    # Dev tools + system tuning
./migration/06-setup-zsh.sh             # Cleaned zsh config
./migration/07-verify-migration.sh      # Verification suite

# Or run all at once:
./migration/08-master-migration.sh      # Orchestrates everything with checkpoints
```

Total estimated time: **~2 hours** (including CachyOS install)

---

## Post-Stabilization (1-2 Weeks Later)

Once CachyOS is confirmed stable:
1. Delete nvme0n1p2 (installer partition) and extend /workspace to reclaim 8GB
2. Wipe SATA ZFS partitions
3. Format as XFS
4. Mount as `/home` (move home from NVMe root)
5. Update `/etc/fstab`
6. Reclaim ~3.6TB for home directory
