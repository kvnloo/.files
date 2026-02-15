# Migration Automation Scripts

Comprehensive automation suite for migrating from Ubuntu (with ZFS) to a dual-boot Ubuntu + CachyOS setup, optimized for 100-1000+ concurrent AI agents.

## Overview

This migration preserves all your data, packages, and configurations while creating a high-performance dual-boot system with:

- **Dual-boot**: Ubuntu + CachyOS with systemd-boot or GRUB
- **Optimized partitioning**: NVMe for OS roots, SATA SSD for /home and /workspace
- **XFS workspace**: Shared 3.6TB partition optimized for parallel I/O
- **System tuning**: 2M file descriptors, optimized I/O schedulers, kernel parameters
- **Package migration**: Automated Ubuntu → CachyOS package conversion
- **Configuration preservation**: All dotfiles, configs, and application data

## Quick Start

### Phase 1: Preparation (Ubuntu System)

```bash
# Full automated migration
sudo ./8-master-migration.sh

# Or run individual scripts
sudo ./1-backup-system.sh      # Comprehensive backup
./2-export-packages.sh         # Export package lists
sudo ./3-partition-disk.sh     # Partition disks (DESTRUCTIVE!)
```

### Phase 2: OS Installation (Manual)

1. Install Ubuntu on prepared partitions
2. Install CachyOS on prepared partitions
3. Configure dual-boot bootloader

### Phase 3: Finalization (CachyOS System)

```bash
# Boot into CachyOS and continue
sudo ./8-master-migration.sh

# Or run individual scripts
./4-install-packages-cachyos.sh  # Install packages
sudo ./5-configure-system.sh     # Apply optimizations
./6-restore-configs.sh           # Restore configurations
./7-verify-migration.sh          # Verify everything works
```

## Scripts Overview

### 1-backup-system.sh
**Purpose**: Comprehensive 5-layer backup of entire system
**Runs on**: Ubuntu (before migration)
**Time**: 30-90 minutes
**Sudo**: Required

**Features**:
- ZFS snapshots (if active)
- Package states (apt, snap, flatpak, npm, pip, cargo, gem, brew)
- Dotfiles (.bashrc, .config, .local/share, .ssh, .gitconfig, /etc)
- Application data (Steam, Docker, databases, VS Code)
- SHA256 checksums and verification

**Output**: `/mnt/backup/migration-backup-[date]/`

---

### 2-export-packages.sh
**Purpose**: Export packages and create conversion mappings
**Runs on**: Ubuntu
**Time**: 2-5 minutes
**Sudo**: Not required

**Converts**:
- `python3-*` → `python-*`
- Removes `-dev`, `-common`, `-bin` suffixes
- Removes version numbers

**Output**: `../package-export/` with conversion mappings and auto-install script

---

### 3-partition-disk.sh
**Purpose**: Interactive disk partitioning
**Runs on**: Ubuntu
**Time**: 10-20 minutes
**Sudo**: REQUIRED
**⚠️ DESTRUCTIVE**: Will ERASE selected disks!

**Creates**:
- NVMe: EFI + Ubuntu / + CachyOS / + Swap + Cache
- SATA: Ubuntu /home + CachyOS /home + /workspace (3.6TB XFS)

**Safety**: Requires "YES" and "DESTROY ALL DATA" confirmations

---

### 4-install-packages-cachyos.sh
**Purpose**: Install packages on CachyOS
**Runs on**: CachyOS
**Time**: 30-120 minutes
**Sudo**: Prompted when needed

**Installs**: paru, system packages, npm, pip, cargo, gem, Flatpak apps

---

### 5-configure-system.sh
**Purpose**: Apply system optimizations
**Runs on**: CachyOS
**Time**: 5-10 minutes
**Sudo**: REQUIRED

**Optimizes**:
- File descriptors: 2M (vs default 1024)
- Swappiness: 10
- Network: 128MB buffers, 65K connections
- I/O: 'none' for NVMe, 'mq-deadline' for SSDs
- CPU: performance governor

**Requires reboot after**

---

### 6-restore-configs.sh
**Purpose**: Restore configurations
**Runs on**: CachyOS
**Time**: 10-30 minutes
**Sudo**: Not required

**Restores**: Shell configs, .config, .local/share, SSH, Git, VS Code, application data

**Note**: SSH private keys require manual restoration

---

### 7-verify-migration.sh
**Purpose**: Comprehensive verification
**Runs on**: CachyOS
**Time**: 5-10 minutes
**Sudo**: Not required

**Tests**: Partitions, filesystems, limits, packages, configs, performance, bootloader, workspace

**Output**: Migration report with pass/warn/fail counts

---

### 8-master-migration.sh
**Purpose**: Master orchestration script
**Runs on**: Ubuntu (Phase 1), CachyOS (Phase 3)
**Time**: 2-4 hours total
**Sudo**: REQUIRED

**Phases**:
1. Ubuntu: Backup + Export + Partition
2. Manual: Install both OSes
3. CachyOS: Install + Configure + Restore + Verify

**Options**:
- `--skip-backup` - Use existing backup
- `--auto-confirm` - Auto-confirm prompts (DANGEROUS!)
- `--help` - Show help

---

## File Organization

```
repos/migrate/
├── scripts/                      # This directory
│   ├── 1-backup-system.sh
│   ├── 2-export-packages.sh
│   ├── 3-partition-disk.sh
│   ├── 4-install-packages-cachyos.sh
│   ├── 5-configure-system.sh
│   ├── 6-restore-configs.sh
│   ├── 7-verify-migration.sh
│   ├── 8-master-migration.sh
│   └── README.md
├── logs/                        # Execution logs
├── package-export/              # Package lists
└── research/                    # Design docs
```

## System Requirements

**Ubuntu (Source)**:
- Ubuntu 20.04+
- 100GB free for backup
- Sudo access

**CachyOS (Target)**:
- Latest CachyOS
- Internet connection

**Hardware**:
- NVMe: 500GB
- SATA SSD: 4TB
- RAM: 16GB+ (32GB+ for 1000+ agents)

## Common Issues

**Package install fails**: Check `../logs/failed-packages-[date].txt`, install manually

**Low file descriptors**: Verify `ulimit -n` = 1048576, re-run config script

**Workspace inaccessible**: Check mount `df -h | grep workspace`, fix permissions `sudo chown -R $USER /workspace`

**SSH keys**: Manually restore from backup, `chmod 600 ~/.ssh/id_*`

**Dual-boot missing**: Run `sudo bootctl update` or `sudo update-grub`

## Performance Validation

```bash
ulimit -n                                    # Should be 1048576
cat /sys/block/nvme*/queue/scheduler         # Should be [none]
sysctl vm.swappiness                         # Should be 10
sysctl net.core.somaxconn                    # Should be 65535
cat /sys/.../scaling_governor                # Should be performance
```

## Timeline

**Total**: 3-5 hours (hands-on: ~1 hour)

- Phase 1: 45-120 min (backup 30-90, export 2-5, partition 10-20)
- Phase 2: 60-120 min (manual OS installations)
- Phase 3: 60-150 min (install 30-120, config 5-10, restore 10-30, verify 5-10)

## Support

- **Logs**: `../logs/`
- **Research**: `../research/`
- **Verification**: `./7-verify-migration.sh`

---

**Happy migrating!** 🚀
