# Improved Research Prompt: Ubuntu to CachyOS Migration with Optimal Filesystem

## Executive Summary
Design and implement an automated migration strategy from Ubuntu (ZFS) to a dual-boot Ubuntu + CachyOS environment optimized for extreme parallel agent orchestration (100s-1000s of concurrent AI agents).

## Context

### Current Environment
- **OS**: Ubuntu on ZFS filesystem
- **Problem**: ZFS overhead causes system freezes/crashes during parallel agent workflows
- **Use Case**: Claude Code parallel agent orchestration for autonomous development
- **Scale**: Target 100-1000+ concurrent agents (Claude Code + local LLMs + OpenRouter)

### Performance Requirements
- **Primary Workload**: Massive parallel I/O from concurrent AI agent operations
- **Critical Metrics**:
  - IOPS (Input/Output Operations Per Second)
  - Low latency for small file operations
  - High throughput for log/checkpoint writes
  - Minimal CPU overhead
  - Fast metadata operations

### Target Architecture
- **Dual-Boot**: Ubuntu + CachyOS
- **Partition Strategy**:
  - Separate `/home` directories per OS
  - Shared workspace partition (projects, repos, data)
  - Optimized filesystem for shared workspace

### Personal Optimization Goals
- **Frameworks**: Blueprint (Bryan Johnson), Ultralearning (Scott Young)
- **Objectives**: Performance, intelligence, curiosity, neuroplasticity, flow state
- **Application**: Human-centric apps with exponential growth patterns

## Research Questions

### 1. Filesystem Optimization (PRIORITY: CRITICAL)
**Question**: Which filesystem delivers optimal performance for parallel agent workflows?

**Specific Requirements**:
- Support for 100-1000+ concurrent file handles
- Minimal CPU overhead during high I/O
- Fast small file operations (agent logs, checkpoints, state files)
- Efficient metadata operations
- Low latency for random I/O patterns

**Candidates to Research**:
- XFS (current hypothesis: best for parallel workloads)
- ext4 (mature, well-tested baseline)
- F2FS (flash-optimized, low latency)
- Btrfs (copy-on-write, snapshots)
- bcachefs (modern, performance-focused)

**Deliverables**:
- Benchmark comparisons for parallel agent workloads
- CPU overhead analysis under high I/O
- Real-world performance metrics (if available)
- Hardware-specific recommendations based on gathered system info

### 2. Automated Backup Strategy (PRIORITY: HIGH)
**Question**: What existing tools provide comprehensive Linux system backup?

**Requirements**:
- Full system state preservation
- Package manager awareness (apt, brew, npm, pip, cargo, etc.)
- Configuration file backup (dotfiles, appdata)
- Incremental backup capability
- Restoration automation

**Research Areas**:
- Industry-standard backup tools (Timeshift, Restic, Borg, etc.)
- Package manager state export/import
- Dotfile management strategies
- Application configuration preservation

**Deliverables**:
- Tool recommendations with pros/cons
- Automated backup script architecture
- Restoration workflow design

### 3. Package Manager Migration (PRIORITY: HIGH)
**Question**: How do we map Ubuntu packages to CachyOS equivalents?

**Package Managers to Cover**:
- System: apt, apt-get, dpkg
- Language: npm, npx, pip, pip3, pipx, cargo, gem, go
- Universal: brew (Homebrew on Linux)
- Container: snap, flatpak
- Other: discovered during enumeration

**Research Areas**:
- Ubuntu → CachyOS package name mapping
- AUR (Arch User Repository) equivalents
- Manual compilation requirements
- Version compatibility issues

**Deliverables**:
- Package conversion strategy
- Automated translation scripts
- Manual intervention checklist

### 4. Dual-Boot Partition Design (PRIORITY: MEDIUM)
**Question**: What partition layout optimizes dual-boot with shared workspace?

**Requirements**:
- Bootloader configuration (GRUB/systemd-boot)
- Shared partition accessibility from both OSes
- Permission management for shared files
- Optimal partition sizes based on hardware

**Deliverables**:
- Partition scheme diagram
- Mount point configuration
- Permission/ownership strategies

### 5. Performance Optimization (PRIORITY: MEDIUM)
**Question**: How do we tune the system for massive parallel agent execution?

**Research Areas**:
- Kernel parameters (file descriptors, I/O scheduler)
- Filesystem mount options
- Memory management (swappiness, cache pressure)
- CPU governor settings
- Network stack tuning (for API calls to LLM providers)

**Deliverables**:
- Hardware-specific optimization guide
- Kernel parameter recommendations
- Boot-time configuration scripts

## Hardware Context
**Action Required**: Run `sudo bash repos/migrate/scripts/gather-hardware-info.sh` to generate `hardware-info.txt`

This will provide:
- CPU specs (cores, threads, cache)
- RAM capacity and speed
- Disk types (NVMe, SSD, HDD)
- Storage controllers
- Current ZFS configuration
- I/O performance baselines

## Success Criteria
1. Filesystem choice backed by benchmarks for parallel agent workloads
2. Zero data loss migration with automated backup/restore
3. 100% package coverage across all package managers
4. Configuration preservation (dotfiles, app settings)
5. Performance improvement: system stability under 100+ parallel agents
6. Time minimization: maximum automation, minimal manual steps

## Research Methodology
- Web search for recent benchmarks (2023-2025)
- Technical documentation review
- Community experiences (Reddit, Stack Exchange, forums)
- Academic papers on filesystem performance
- Vendor documentation (CachyOS, Arch Linux)

## Output Format
For each research question, provide:
1. **Summary**: 2-3 sentence key finding
2. **Evidence**: Links to benchmarks, docs, discussions
3. **Recommendation**: Specific actionable advice
4. **Trade-offs**: Pros and cons of each option
5. **Implementation**: Step-by-step guide
6. **Scripts**: Automation code where applicable

## Timeline Priority
1. Filesystem research (blocks everything else)
2. Hardware info gathering (informs optimization)
3. Backup strategy (risk mitigation)
4. Package migration (bulk of automation)
5. Partition design (final architecture)
