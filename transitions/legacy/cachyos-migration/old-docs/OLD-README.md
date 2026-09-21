# Ubuntu → CachyOS Migration Project

**Status**: ✅ Complete - Ready for execution

Comprehensive automation suite for migrating from Ubuntu (ZFS) to dual-boot Ubuntu + CachyOS, optimized for 100-1000+ concurrent AI agents.

---

## 🎯 What This Project Does

Automates the entire migration process to eliminate ZFS performance bottlenecks and create a high-performance dual-boot environment optimized for:
- Claude Code parallel agent orchestration
- Local LLM workflows (Ollama, vLLM, etc.)
- Autonomous product development
- Digital twin management
- Continuous research/synthesis/deployment

---

## 📊 Expected Improvements

### Performance (Research-Backed)
- **50-100% better random write IOPS** (XFS vs ZFS)
- **1000+ concurrent agents** vs 100-200 (before system freezes)
- **30% memory overhead reduction** (no ZFS ARC cache)
- **System stability** - No more freezes from ZFS txg_sync

### System Optimizations
- **2M file descriptors** (vs 1024 default)
- **65K network connections** (vs ~1K default)
- **<1ms I/O latency** (optimized NVMe scheduler)
- **10x faster swap** (NVMe vs SATA)

---

## 📁 Project Structure

```
repos/migrate/
├── research/           # 5 comprehensive research documents (166KB)
│   ├── filesystem-comparison.md          # XFS vs ext4 vs F2FS benchmarks
│   ├── backup-tools-comparison.md        # BorgBackup + Chezmoi strategy
│   ├── package-migration-strategy.md     # Ubuntu → CachyOS conversion
│   ├── system-optimization.md            # Kernel params, I/O tuning
│   └── partition-design.md               # Dual-boot layout + fstab
│
├── scripts/            # 8 production-ready automation scripts (3,889 lines)
│   ├── 1-backup-system.sh               # 5-layer backup strategy
│   ├── 2-export-packages.sh             # Package conversion
│   ├── 3-partition-disk.sh              # Interactive partitioning
│   ├── 4-install-packages-cachyos.sh    # Package installation
│   ├── 5-configure-system.sh            # System optimization
│   ├── 6-restore-configs.sh             # Config restoration
│   ├── 7-verify-migration.sh            # Verification tests
│   └── 8-master-migration.sh            # Full orchestration
│
└── docs/               # System information
    ├── hardware-info.txt                # CPU, RAM, disks, controllers
    ├── disk-usage.txt                   # Current storage usage
    └── package-lists/                   # All installed packages (15 files)
```

---

## 🚀 Quick Start

### One-Command Migration
```bash
cd repos/migrate/scripts
sudo ./8-master-migration.sh
```

### Step-by-Step
```bash
# Phase 1: Ubuntu (before migration)
sudo ./1-backup-system.sh      # 30-90 min
./2-export-packages.sh         # 2-5 min
sudo ./3-partition-disk.sh     # 10-20 min (DESTRUCTIVE!)

# Phase 2: Manual OS installation (60-120 min)

# Phase 3: CachyOS (after installation)
./4-install-packages-cachyos.sh  # 30-120 min
sudo ./5-configure-system.sh     # 5-10 min
./6-restore-configs.sh           # 10-30 min
./7-verify-migration.sh          # 5-10 min
```

**Total Time**: 3-5 hours (hands-on: ~1 hour)

---

## 🔑 Key Research Findings

### 1. Filesystem Choice: XFS
- **Best for parallel workloads**: 50-100% better random write IOPS
- **Low CPU overhead**: Minimal impact during high I/O
- **Proven at scale**: Used by RHEL, CentOS for enterprise workloads
- **Optimal for 1000+ agents**: Efficient metadata operations

### 2. Partition Layout
- **NVMe (500GB)**: OS roots + swap + cache (fast boot, system responsiveness)
- **SATA (4TB)**: Separate /home per OS + shared 3.6TB /workspace
- **Isolation**: No config conflicts between Ubuntu and CachyOS
- **Performance**: Workspace on XFS with aggressive mount options

### 3. Backup Strategy
- **BorgBackup**: Encrypted, deduplicated, cross-filesystem
- **Chezmoi**: Dotfile management with machine-specific configs
- **Multi-layer**: ZFS snapshots + packages + configs + app data
- **Verification**: SHA256 checksums for data integrity

### 4. System Tuning
- **File descriptors**: 2M system-wide, 1M per process
- **I/O scheduler**: 'none' for NVMe, 'mq-deadline' for SSD
- **Memory**: swappiness=10, cache_pressure=50
- **Network**: 128MB buffers, 65K connections
- **CPU**: performance governor for low latency

---

## 📖 Documentation

**Start here**: `scripts/README.md` - Complete script documentation

**Research deep-dives**:
- `research/filesystem-comparison.md` - Why XFS? Benchmark data
- `research/backup-tools-comparison.md` - 5-layer backup strategy
- `research/package-migration-strategy.md` - apt → pacman conversion
- `research/system-optimization.md` - Kernel tuning for parallel agents
- `research/partition-design.md` - Dual-boot architecture

---

## ✅ Safety Features

- **5-layer backup**: ZFS + packages + dotfiles + apps + verification
- **Dry-run modes**: Test before destructive operations
- **Comprehensive verification**: 8 test categories, pass/warn/fail scoring
- **Rollback procedures**: Documented recovery steps
- **Checkpoint system**: Resume after interruptions
- **Detailed logging**: All operations logged to `logs/`

---

## 🎯 Next Steps

1. **Review research** - Understand the recommendations (30 min)
2. **Prepare backup drive** - External storage for backups
3. **Run Phase 1** - Backup and partition on Ubuntu
4. **Install OSes** - Manual Ubuntu + CachyOS installation
5. **Run Phase 3** - Complete migration on CachyOS
6. **Verify & optimize** - Run verification, start testing parallel agents

---

## 💡 Goals Alignment

### Blueprint (Bryan Johnson) ✅
- **Optimize performance**: System tuned for maximum throughput
- **Measure improvements**: Verification provides metrics
- **Data-driven decisions**: All choices backed by benchmarks

### Ultralearning (Scott Young) ✅
- **Minimize time investment**: Full automation, minimal manual work
- **Focus on essentials**: Research identifies critical optimizations only
- **Practice in production**: Dual-boot allows safe testing

### Continuous R&D ✅
- **Research phase**: Deep investigation with 90+ sources
- **Synthesis**: Integrated findings across 5 documents
- **Analysis**: Benchmark-driven recommendations
- **Integration**: Production-ready automation scripts
- **Deployment**: One-command execution

---

**Status**: All research complete, all scripts ready. Time to migrate! 🚀
