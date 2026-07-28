# CachyOS Installation Walkthrough - Prompt for Claude

> After the machine is up, prefer ongoing setup via `./install` or the harness
> onboarding in `AGENTS.md` / `docs/SETUP.md`. The steps below are the original
> migration walkthrough.

Copy everything below this line and paste it into Claude on your phone.

---

You are helping me install and set up CachyOS on my desktop. Walk me through each step one at a time, waiting for my confirmation before moving to the next step. I'm on my phone so keep responses concise.

## My System

- **Machine**: groot | RTX 3080 Ti | 16GB RAM | Triple 1080p monitors (75/240/540Hz)
- **Migrating from**: Ubuntu 24.04 on SATA 4TB SSD (sda) -- keeping this untouched as fallback
- **Migrating to**: CachyOS on NVMe 500GB (nvme0n1)

## Drives (CRITICAL - only touch nvme0n1)

- **nvme0n1** (500GB Samsung 960 EVO) -- TARGET for CachyOS. Currently has CachyOS installer ISO on p2.
- **sda** (4TB WD Blue SATA SSD) -- Ubuntu 24.04 with ZFS root. DO NOT TOUCH. My dotfiles repo is at `/home/kvn/workspace/.files` on this drive.
- **sdb** (3TB HDD) -- Windows/data. DO NOT TOUCH.
- **sdc** (500GB SSD) -- Windows/data. DO NOT TOUCH.

## What's already done (Phase 0)

- NVMe Windows data (nvme0n1p1 NTFS "fast") backed up as 29GB tarball to SATA drive at ~/nvme-windows-backup-20260215-141259/
- CachyOS Desktop ISO copied to nvme0n1p2 (8GB ext4 partition at END of disk)
- GRUB loopboot entry created to boot CachyOS installer from NVMe (copytoram=y, loads to RAM)
- All dotfiles and migration scripts committed to git on local dev branch (can't push -- GitHub suspended)
- Dotfiles repo location on SATA: /home/kvn/workspace/.files (on Ubuntu's ZFS root)

## Phase 1: CachyOS Installation

I'm about to reboot and select "CachyOS Installer (loopboot from NVMe)" from GRUB. The ISO loads entirely into RAM so the NVMe is free to repartition.

### 1.1 Partitioning (Manual in Calamares -- CRITICAL)

Target disk: **nvme0n1 only**. Select **Manual Partitioning** (NEVER "Erase Disk").

Steps:
1. **Delete** nvme0n1p1 (458GB NTFS "fast") -- frees space at the START of the disk
2. **Do NOT delete** nvme0n1p2 (8GB ext4 "arch") -- this is the installer, physically at the END of the disk. Leave it alone.
3. In the freed ~458GB space at the start, create these partitions IN ORDER:

| Order | Size | Filesystem | Mount Point | Flags |
|-------|------|------------|-------------|-------|
| 1st | 1 GB | FAT32 | /boot/efi | boot, esp |
| 2nd | 100 GB | XFS | / | (none) |
| 3rd | 32 GB | linux-swap | [SWAP] | swap |
| 4th | ~318 GB (remaining) | XFS | /workspace | (none) |

The 8GB installer partition (p2) stays at the end, untouched. Physical layout will be: [EFI][Root][Swap][Workspace][Installer]

**DO NOT TOUCH sda, sdb, or sdc in the partitioner.**

### 1.2 Installer Options

- Desktop: **Hyprland** (if offered) or **minimal** (I have install scripts)
- Username: **kvn**
- Hostname: **groot**
- Timezone: **America/Chicago**
- Locale: **en_US.UTF-8**
- Bootloader: CachyOS defaults to **systemd-boot**, that's fine

### 1.3 After install completes, reboot into CachyOS (remove/skip the installer boot entry)

## Phase 2: First Boot & Base Setup

After booting into CachyOS:

### 2.1 Connect to network
```bash
nmcli device status
# If ethernet not connected:
nmcli device connect enp4s0
```

### 2.2 Copy dotfiles from SATA drive (GitHub is suspended, can't clone)

My Ubuntu SATA drive (sda) has ZFS partitions. I need to mount it and copy my dotfiles repo.

```bash
# Install ZFS support to read Ubuntu's drive
sudo pacman -S zfs-utils

# Import the ZFS pool (read-only for safety)
sudo zpool import -o readonly=on -f rpool  # or whatever the pool name is

# If ZFS is too complicated, try mounting individual partitions:
# Check what's on sda:
lsblk -f /dev/sda

# The dotfiles are at: /home/kvn/workspace/.files on the Ubuntu system
# Once mounted (e.g. at /mnt), copy:
mkdir -p ~/workspace
cp -a /mnt/home/kvn/workspace/.files ~/workspace/.files
cd ~/workspace/.files
git checkout dev
```

If ZFS mounting is problematic, an alternative is to just mount the SATA drive from Ubuntu's BIOS boot, plug in a USB, copy the dotfiles repo to USB, then boot back to CachyOS and copy from USB.

### 2.3 Run automation scripts (in order)

```bash
cd ~/workspace/.files

# Install all packages (pacman + AUR via paru + flatpak)
./migration/01-install-packages.sh

# Deploy dotfile symlinks
./migration/02-deploy-dotfiles.sh
```

## Phase 3: Audio Stack

```bash
./migration/03-setup-audio.sh
```

Sets up PipeWire filter-chain DSP, WirePlumber for Topping DX5, AutoEQ, browser bypass, realtime privileges.

Verify:
```bash
systemctl --user status pipewire
wpctl status
```

## Phase 4: Hyprland & Display

```bash
./migration/04-setup-hyprland.sh
```

Sets up Hyprland config (translated from i3), waybar, hyprlock, hypridle, rofi-wayland, monitor layout (3 displays, DP-2 portrait).

Verify: log out and back in, then:
```bash
hyprctl monitors
```
Should show 3 monitors at correct resolutions.

## Phase 5: Dev Environment & Zsh

```bash
./migration/06-setup-zsh.sh
./migration/05-setup-dev-services.sh
```

Sets up zsh with oh-my-zsh (Arch paths), nvm + Node, rustup, Docker, Tailscale, Ollama, sysctl tuning.

## Phase 6: Verification

```bash
./migration/07-verify-migration.sh
```

### Manual checks:
- Audio: `wpctl status` shows DX5, play music through TIDAL
- Display: all 3 monitors active, DP-2 portrait, DP-0 at 240Hz
- Desktop: mod+Return opens terminal, mod+hjkl moves focus, waybar visible
- Dev: `node --version`, `rustc --version`, `docker run hello-world`
- Services: `systemctl status docker tailscaled ollama`
- Network: `ping google.com`, `tailscale status`

## Troubleshooting

- **Can't boot CachyOS after install**: Select Ubuntu from BIOS boot menu (F12/F2/Del at POST). Ubuntu is untouched on SATA.
- **NVIDIA issues**: Ensure `nvidia_drm.modeset=1` is in boot params. Edit `/boot/loader/entries/*.conf` for systemd-boot.
- **No display on Hyprland**: Try TTY (Ctrl+Alt+F2), check `journalctl --user -u hyprland` or fall back to a basic WM.
- **ZFS mount fails for SATA**: Boot Ubuntu from BIOS, copy dotfiles to a USB stick, then boot CachyOS and copy from USB.
- **Script fails**: Each script logs to `~/workspace/.files/logs/`. Check the log, fix the issue, re-run. The master script (08-master-migration.sh) has checkpoints for resuming.
- **Rollback**: Ubuntu is fully intact on SATA. Just select it from BIOS boot menu.

## Important Notes

- Walk me through ONE STEP AT A TIME. Wait for me to confirm before moving on.
- I'm on my phone so keep responses SHORT.
- If something fails, help me debug it before moving on.
- The automation scripts handle most of the work -- I mainly need help with Phase 1 (installer) and Phase 2 (getting dotfiles copied from SATA).
