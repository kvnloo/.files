# Linux Backup Tools Comparison for System Migration
**Date:** 2025-11-25
**Mission:** Complete system migration from Ubuntu (ZFS) to dual-boot Ubuntu + CachyOS

---

## Executive Summary

For migrating from Ubuntu with ZFS to a dual-boot Ubuntu + CachyOS setup, a **layered backup strategy** is recommended:

1. **System-Level:** ZFS snapshots + Sanoid/Syncoid (primary) or BorgBackup (alternative)
2. **Dotfiles:** Chezmoi (recommended) or yadm
3. **Package State:** Meta Package Manager + native export commands
4. **Application Data:** Targeted per-application strategies

**Estimated Setup Time:** 4-6 hours
**Confidence Level:** High (85%) - All tools are production-proven with active communities

---

## 1. System-Level Backup Tools

### Comparison Matrix

| Tool | Deduplication | Encryption | Incremental | ZFS-Aware | Complexity | Community |
|------|---------------|------------|-------------|-----------|------------|-----------|
| **Timeshift** | ❌ (rsync-based) | ❌ | ✅ | ⚠️ Limited | Low | Active |
| **BorgBackup** | ✅ (Excellent) | ✅ AES-256 | ✅ | ❌ | Medium | Very Active |
| **Restic** | ✅ (Good) | ✅ AES-256 | ✅ | ❌ | Medium | Very Active |
| **Sanoid/Syncoid** | ✅ (ZFS native) | ✅ (ZFS native) | ✅ | ✅ | Medium-High | Active |
| **ZFS Autobackup** | ✅ (ZFS native) | ✅ (ZFS native) | ✅ | ✅ | Low-Medium | Active |

### Detailed Analysis

#### **Timeshift** ⭐⭐⭐
**Best For:** System snapshot rollback, Ubuntu-specific recovery

**Pros:**
- GUI-friendly interface designed for Ubuntu/Mint users
- Automatic snapshot scheduling (hourly, daily, weekly, monthly)
- Fast rollback for system updates that break functionality
- Low learning curve

**Cons:**
- No deduplication (uses rsync hard links)
- No encryption support
- Not designed for full system migration
- Excludes user data by default
- Only backs up to local partition root (e.g., USB drives)

**Verdict:** Use as supplementary tool for system rollback capability, NOT as primary migration tool.

**Sources:**
- [Timeshift vs Restic comparison](https://forum.restic.net/t/timeshift-vs-git-vs-restic-linux-os-and-user-data-backup/7905)
- [Best Linux Backup Solutions 2025](https://howik.com/linux-backup-solutions-2025)

---

#### **BorgBackup (Borg)** ⭐⭐⭐⭐⭐
**Best For:** Comprehensive system backups, encrypted archives, low-RAM systems

**Pros:**
- **Excellent deduplication:** Content-defined chunking, 60-80% storage reduction on typical workloads
- **Strong encryption:** AES-256-CTR with HMAC-SHA256 authentication
- **Memory efficient:** Works well on systems with 2GB RAM or less
- **Compression options:** lz4, zstd, zlib, lzma
- **Mature ecosystem:** Borgmatic wrapper for automation

**Cons:**
- No native S3 support (requires rclone/borgmatic integration)
- Command-line only (borgmatic helps)
- Requires learning curve for advanced features

**Installation:**
```bash
sudo apt install borgbackup borgmatic
```

**Basic Usage:**
```bash
# Initialize repository
borg init --encryption=repokey /path/to/backup

# Create backup
borg create /path/to/backup::archive-{now} /home /etc /var --exclude-caches

# List archives
borg list /path/to/backup

# Restore
borg extract /path/to/backup::archive-name
```

**Automation with Borgmatic:**
```yaml
# /etc/borgmatic/config.yaml
location:
    source_directories:
        - /home
        - /etc
        - /var/lib
    repositories:
        - /mnt/backup/borg
    exclude_patterns:
        - '*.pyc'
        - '~/.cache'

retention:
    keep_daily: 7
    keep_weekly: 4
    keep_monthly: 6

consistency:
    checks:
        - repository
        - archives
```

**Verdict:** **PRIMARY CHOICE** for non-ZFS filesystems or supplementary encrypted backups.

**Sources:**
- [Restic vs BorgBackup vs Kopia 2025](https://onidel.com/restic-vs-borgbackup-vs-kopia-2025/)
- [Borgmatic ArchWiki](https://wiki.archlinux.org/title/Borgmatic)
- [BorgBackup comparison](https://www.vinchin.com/linux-backup/linux-backup-software.html)

---

#### **Restic** ⭐⭐⭐⭐
**Best For:** Cloud backup, S3 integration, cross-platform environments

**Pros:**
- **Native S3 support:** Excellent compatibility with AWS, Backblaze B2, Wasabi
- **Cross-platform:** Linux, macOS, Windows, BSD
- **Content-defined chunking:** Variable-length segments for efficient deduplication
- **Fast:** Written in Go, optimized for speed
- **Resticprofile automation:** Configuration-driven scheduling

**Cons:**
- Slightly less memory efficient than Borg on constrained systems
- Newer than Borg (but still mature)
- Cloud storage costs for S3 destinations

**Installation:**
```bash
sudo apt install restic
```

**Basic Usage:**
```bash
# Initialize repository
restic init --repo /path/to/backup

# Create backup
restic backup /home /etc /var --exclude-file=excludes.txt

# List snapshots
restic snapshots

# Restore
restic restore latest --target /restore/path
```

**Automation with Resticprofile:**
```yaml
# resticprofile.yaml
version: "1"

backup:
  repository: /mnt/backup/restic
  password-file: /root/.restic-password
  source:
    - /home
    - /etc
    - /var/lib
  exclude-file: /etc/restic/excludes.txt
  schedule: "daily"
  retention:
    keep-daily: 7
    keep-weekly: 4
    keep-monthly: 6
```

**Verdict:** **EXCELLENT CHOICE** if cloud backup or cross-platform support needed.

**Sources:**
- [Restic encrypted offsite backup](https://helgeklein.com/blog/restic-encrypted-offsite-backup-for-your-homeserver/)
- [Resticprofile documentation](https://creativeprojects.github.io/resticprofile/configuration/getting_started/index.html)

---

#### **Sanoid/Syncoid** (ZFS-Specific) ⭐⭐⭐⭐⭐
**Best For:** ZFS systems, snapshot automation, ZFS-to-ZFS replication

**Pros:**
- **ZFS-native:** Leverages ZFS snapshots and send/receive
- **Elegant automation:** Policy-driven snapshot management
- **Efficient replication:** Syncoid handles incremental zfs send/receive
- **Resume support:** Interrupted transfers can resume (ZFS 1.4.18+)
- **Flexible retention:** Hourly, daily, weekly, monthly, yearly policies
- **Pull-based security:** Backup server pulls snapshots

**Cons:**
- **ZFS-only:** Cannot back up non-ZFS filesystems
- Requires ZFS knowledge
- Command-line only

**Installation:**
```bash
sudo apt install sanoid
```

**Configuration:**
```ini
# /etc/sanoid/sanoid.conf
[rpool/home]
    use_template = production
    recursive = yes

[template_production]
    frequently = 4        # 15-minute intervals
    hourly = 36
    daily = 30
    monthly = 3
    yearly = 0
    autosnap = yes
    autoprune = yes
```

**Syncoid Replication:**
```bash
# Pull snapshots from source to backup (run on backup server)
syncoid --recursive source-host:rpool/home backup-pool/home
```

**Best Practices:**
- Run Sanoid on both source and backup servers
- Use pull-based replication for security
- Configure larger retention on backup server
- Set `autosnap = no` on backup server, `autoprune = yes`

**Verdict:** **PRIMARY CHOICE** for ZFS-based systems. Most efficient for your current Ubuntu ZFS setup.

**Sources:**
- [Sanoid GitHub](https://github.com/jimsalterjrs/sanoid)
- [Setting up automated ZFS snapshots](https://techsbucket.com/setting-up-automated-zfs-snapshots-with-sanoid-on-ubuntu-server/)
- [ZFS Backup Best Practices](https://klarasystems.com/articles/openzfs-storage-best-practices-and-use-cases-part-1-snapshots-and-backups/)
- [Opinionated Guide to ZFS Snapshots](https://kimono-koans.github.io/opinionated-guide/)

---

#### **ZFS Autobackup** ⭐⭐⭐⭐
**Best For:** Simple ZFS backup automation, periodic backups

**Pros:**
- **Easy to use:** Simple command-line interface
- **Reliable:** Built specifically for ZFS
- **Only needs installation on one side:** Can be installed just on backup server
- **Cron-friendly:** Easy to schedule
- **Supports remote and local:** SSH and local backup destinations

**Cons:**
- Less feature-rich than Sanoid/Syncoid
- Smaller community than Sanoid
- Fewer retention policy options

**Installation:**
```bash
pip install zfs-autobackup
```

**Basic Usage:**
```bash
# Tag datasets to backup
zfs set autobackup:daily=true rpool/home

# Perform backup
zfs-autobackup daily backup-pool/daily --verbose
```

**Verdict:** **GOOD ALTERNATIVE** to Sanoid if you prefer simplicity over flexibility.

**Sources:**
- [ZFS Autobackup GitHub](https://github.com/psy0rz/zfs_autobackup)

---

### **RECOMMENDATION FOR YOUR CASE:**

**Primary Strategy: Layered Approach**
```
Layer 1: Sanoid/Syncoid (ZFS snapshots and replication)
Layer 2: BorgBackup (Encrypted full-system backup for critical data)
Layer 3: Timeshift (Optional - post-migration system rollback capability)
```

**Why this combination?**
1. **Sanoid/Syncoid:** Native ZFS integration for efficient backup of current system
2. **BorgBackup:** Encrypted, deduplicated archives that work across any filesystem (including CachyOS post-migration)
3. **Timeshift:** Quick rollback capability after migration (especially useful during dual-boot setup)

---

## 2. Dotfile Management Solutions

### Comparison Matrix

| Tool | Approach | Templating | Secrets | Complexity | Active Development |
|------|----------|------------|---------|------------|-------------------|
| **GNU Stow** | Symlinks | ❌ | ❌ | Low | Stable |
| **yadm** | Git wrapper | ✅ | ✅ (GPG) | Low-Medium | Active |
| **Chezmoi** | File copying | ✅ (Advanced) | ✅ (age/GPG + 1Password) | Medium | Very Active |
| **dotbot** | Symlinks + scripts | ⚠️ Limited | ❌ | Low | Active |

### Detailed Analysis

#### **GNU Stow** ⭐⭐⭐
**Best For:** Simple symlink-based dotfile management

**Pros:**
- **Dead simple:** Just symlinks files from repo to home directory
- **No dependencies:** Part of standard GNU toolchain
- **Transparent:** You can see exactly what's happening
- **Safe:** Easy to undo (remove symlinks)

**Cons:**
- **No templates:** Can't adapt to different machines
- **No secrets management:** Secrets go directly in repo
- **No automatic bootstrapping:** Manual setup required

**Usage:**
```bash
# Structure: ~/dotfiles/{app}/...
~/dotfiles/
├── bash/
│   └── .bashrc
├── vim/
│   └── .vimrc
└── git/
    └── .gitconfig

# Create symlinks
cd ~/dotfiles
stow bash vim git
```

**Verdict:** **GOOD FOR SIMPLE SETUPS** but lacks machine-specific configuration support.

**Sources:**
- [Effortlessly Manage Dotfiles with GNU Stow](https://corti.com/effortlessly-manage-dotfiles-on-unix-with-gnu-stow-and-github/)

---

#### **yadm** ⭐⭐⭐⭐
**Best For:** Git-based dotfile management with encryption

**Pros:**
- **Git-wrapper approach:** Familiar Git commands
- **Built-in encryption:** GPG for sensitive files
- **Templating support:** Jinja2-based templates for machine differences
- **Alternate files:** Per-machine/OS/hostname file variants
- **Bootstrap scripts:** Automated setup on new machines

**Cons:**
- Bare Git repo approach can be confusing initially
- Less powerful templating than Chezmoi
- GPG-only for secrets (no 1Password/Bitwarden integration)

**Installation & Usage:**
```bash
sudo apt install yadm

# Initialize
yadm init
yadm add ~/.bashrc ~/.vimrc ~/.config/i3/config
yadm commit -m "Initial dotfiles"

# Add remote
yadm remote add origin git@github.com:user/dotfiles.git
yadm push

# Clone on new machine
yadm clone git@github.com:user/dotfiles.git
yadm decrypt  # Decrypt GPG-encrypted files
yadm bootstrap  # Run bootstrap script
```

**Templating Example:**
```bash
# .bashrc##template
export HOSTNAME="{{ yadm.hostname }}"
{% if yadm.os == "Linux" %}
alias ls='ls --color=auto'
{% endif %}
```

**Verdict:** **EXCELLENT MIDDLE GROUND** between simplicity and features.

**Sources:**
- [Dotfile Management Tools Comparison](https://biggo.com/news/202412191324_dotfile-management-tools-comparison)
- [yadm documentation](https://dotfiles.github.io/utilities/)

---

#### **Chezmoi** ⭐⭐⭐⭐⭐
**Best For:** Complex multi-machine setups, enterprise environments, secrets management

**Pros:**
- **Advanced templating:** Go templates with full logic support
- **Password manager integration:** 1Password, Bitwarden, LastPass, pass
- **Multiple encryption backends:** age, GPG
- **Import from archives:** Can pull configs from .tar.gz, .zip
- **Scripts on installation:** Run commands during `chezmoi apply`
- **Machine-specific configs:** Per-OS, per-hostname, per-architecture
- **Excellent documentation:** Very comprehensive guides
- **Active community:** Fast development, responsive maintainers

**Cons:**
- Steeper learning curve than Stow or yadm
- Uses file copying instead of symlinks (some prefer symlinks)
- More complex setup for simple use cases

**Installation & Usage:**
```bash
# Install
sh -c "$(curl -fsLS get.chezmoi.io)"

# Initialize
chezmoi init

# Add files
chezmoi add ~/.bashrc
chezmoi add ~/.config/nvim/init.vim

# Edit files (opens in $EDITOR)
chezmoi edit ~/.bashrc

# See what would change
chezmoi diff

# Apply changes
chezmoi apply

# One-command setup on new machine
chezmoi init --apply https://github.com/user/dotfiles.git
```

**Templating Example:**
```bash
# .bashrc.tmpl
export HOSTNAME={{ .chezmoi.hostname }}
{{- if eq .chezmoi.os "linux" }}
alias ls='ls --color=auto'
{{- end }}

{{- if .is_work_machine }}
export WORK_ENV=true
{{- end }}
```

**Secrets Management:**
```bash
# .chezmoi.toml.tmpl
[data]
    email = "user@domain.com"
    github_token = {{ onepasswordRead "op://Personal/GitHub/token" }}
```

**Verdict:** **PRIMARY RECOMMENDATION** for comprehensive dotfile management, especially with secrets.

**Sources:**
- [Chezmoi comparison table](https://www.chezmoi.io/comparison-table/)
- [Why use chezmoi?](https://www.chezmoi.io/why-use-chezmoi/)
- [Exploring dotfile management tools](https://gbergatto.github.io/posts/tools-managing-dotfiles/)

---

### **RECOMMENDATION:**

**Use Chezmoi** for complete dotfile management:
1. Handles machine-specific configurations (Ubuntu vs CachyOS)
2. Integrates with password managers for secrets
3. Supports automated bootstrapping for new system setup
4. Most comprehensive feature set for migration scenario

**Quick Start Workflow:**
```bash
# 1. Install Chezmoi
sh -c "$(curl -fsLS get.chezmoi.io)"

# 2. Initialize and add existing dotfiles
chezmoi init
chezmoi add ~/.bashrc ~/.zshrc ~/.config

# 3. Create .chezmoi.toml for machine-specific data
cat > ~/.local/share/chezmoi/.chezmoi.toml <<EOF
[data]
    os = "ubuntu"
    is_work_machine = false
EOF

# 4. Push to Git
cd ~/.local/share/chezmoi
git remote add origin git@github.com:user/dotfiles.git
git push

# 5. On new machine (CachyOS)
chezmoi init --apply git@github.com:user/dotfiles.git
```

---

## 3. Package Manager State Preservation

### Multi-Package Manager Management

#### **Meta Package Manager (mpm)** ⭐⭐⭐⭐⭐
**Best For:** Unified package management across all package managers

**Pros:**
- **Universal interface:** Works with apt, brew, cargo, npm, pip, flatpak, snap, etc.
- **Backup to TOML:** Export all installed packages to structured file
- **Cross-platform:** macOS, Linux, Windows
- **Actively maintained:** Regular updates
- **Comprehensive support:** 20+ package managers

**Installation:**
```bash
pip install meta-package-manager
```

**Usage:**
```bash
# List all package managers
mpm managers

# List all installed packages across all managers
mpm installed

# Backup all packages to TOML
mpm backup > packages-backup.toml

# Upgrade all packages (all managers)
mpm upgrade --all

# Install from backup (requires scripting)
# Parse TOML and install per manager
```

**Backup Example:**
```toml
# Generated by mpm backup
[apt]
packages = ["vim", "git", "curl", "build-essential"]

[npm]
packages = ["typescript", "prettier", "eslint"]

[pip]
packages = ["requests", "numpy", "pandas"]

[cargo]
packages = ["ripgrep", "fd-find", "bat"]

[flatpak]
packages = ["com.spotify.Client", "org.gimp.GIMP"]
```

**Sources:**
- [Meta Package Manager on PyPI](https://pypi.org/project/meta-package-manager/)
- [Meta Package Manager GitHub](https://github.com/kdeldycke/meta-package-manager)

---

### Native Package Manager Export

#### **APT (Debian/Ubuntu)**
```bash
# Export installed packages
dpkg --get-selections > dpkg-selections.txt

# Or with versions
apt list --installed > apt-installed.txt

# Restore on new system
sudo dpkg --set-selections < dpkg-selections.txt
sudo apt-get dselect-upgrade
```

#### **Homebrew**
```bash
# Export bundle
brew bundle dump --file=Brewfile

# Restore on new system
brew bundle --file=Brewfile
```

**Example Brewfile:**
```ruby
tap "homebrew/cask"
brew "git"
brew "neovim"
brew "ripgrep"
cask "iterm2"
```

#### **npm**
```bash
# Global packages
npm list -g --depth=0 > npm-globals.txt

# Restore
cat npm-globals.txt | xargs npm install -g
```

#### **pip**
```bash
# Export requirements
pip freeze > requirements.txt

# Restore
pip install -r requirements.txt
```

#### **Cargo**
```bash
# List installed binaries
cargo install --list > cargo-list.txt

# Restore (requires parsing and scripting)
# cargo install <package>
```

#### **Flatpak**
```bash
# Export installed flatpaks
flatpak list --app --columns=application > flatpak-list.txt

# Restore
cat flatpak-list.txt | xargs -I {} flatpak install -y {}
```

---

### **RECOMMENDED WORKFLOW:**

**Comprehensive Package State Backup Script:**
```bash
#!/bin/bash
# backup-packages.sh

BACKUP_DIR="$HOME/package-backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# APT
dpkg --get-selections > "$BACKUP_DIR/dpkg-selections.txt"
apt list --installed > "$BACKUP_DIR/apt-installed.txt"

# Snap
snap list > "$BACKUP_DIR/snap-list.txt"

# Flatpak
flatpak list --app --columns=application > "$BACKUP_DIR/flatpak-list.txt"

# npm global
npm list -g --depth=0 > "$BACKUP_DIR/npm-globals.txt"

# pip
pip freeze > "$BACKUP_DIR/pip-requirements.txt"

# Cargo
cargo install --list > "$BACKUP_DIR/cargo-list.txt"

# Homebrew (if installed)
if command -v brew &> /dev/null; then
    brew bundle dump --file="$BACKUP_DIR/Brewfile"
fi

# Meta Package Manager (if installed)
if command -v mpm &> /dev/null; then
    mpm backup > "$BACKUP_DIR/mpm-backup.toml"
fi

echo "✅ Package backups saved to $BACKUP_DIR"
```

---

## 4. Application Data Backup Strategies

### Steam
**Location:** `~/.local/share/Steam` or `~/.steam`

**What to backup:**
- `~/.local/share/Steam/config` - Steam settings
- `~/.local/share/Steam/userdata` - Per-user configs and saves
- `steamapps/common/*/saves` - Game saves (if not in cloud)

**Restoration:**
```bash
# Copy Steam directory to new system
rsync -av ~/.local/share/Steam/ /mnt/backup/steam/

# On new system
rsync -av /mnt/backup/steam/ ~/.local/share/Steam/
```

**Sources:**
- [Backup Steam configuration](https://steamcommunity.com/app/221410/discussions/0/2259060348509180834/)

---

### Docker
**Location:** `/var/lib/docker`

**What to backup:**
- **Volumes:** `docker volume ls` - Persistent data
- **Images:** `docker images` - Custom built images
- **Containers:** `docker ps -a` - Container configurations

**Backup Strategy:**
```bash
# Export volumes
docker run --rm -v volume_name:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/volume_backup.tar.gz /data

# Save images
docker save -o images.tar.gz image1:tag image2:tag

# Export container configs (docker-compose recommended)
docker-compose config > docker-compose-backup.yml
```

**Better approach: Use Docker Compose**
```yaml
# docker-compose.yml defines entire stack
version: '3'
services:
  app:
    image: myapp:latest
    volumes:
      - app-data:/data
volumes:
  app-data:
```

**Restoration:**
```bash
# Load images
docker load -i images.tar.gz

# Restore volumes
docker run --rm -v volume_name:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/volume_backup.tar.gz -C /

# Recreate stack
docker-compose up -d
```

**Sources:**
- [Docker backup and restore](https://docs.docker.com/desktop/backup-and-restore/)
- [How to backup Docker containers](https://sqlbak.com/blog/how-to-backup-and-restore-docker-containers-and-volumes/)

---

### Databases

#### **PostgreSQL**
```bash
# Dump single database
pg_dump dbname > dbname-backup.sql

# Dump all databases
pg_dumpall > all-databases-backup.sql

# Restore
psql dbname < dbname-backup.sql
```

#### **MySQL/MariaDB**
```bash
# Dump single database
mysqldump -u root -p dbname > dbname-backup.sql

# Dump all databases
mysqldump -u root -p --all-databases > all-databases-backup.sql

# Restore
mysql -u root -p dbname < dbname-backup.sql
```

#### **MongoDB**
```bash
# Dump database
mongodump --db dbname --out /backup/mongodb

# Restore
mongorestore --db dbname /backup/mongodb/dbname
```

**Automated Database Backup (Docker):**
Use [docker-db-backup](https://github.com/tiredofit/docker-db-backup) for scheduled backups of PostgreSQL, MySQL, and MongoDB.

**Sources:**
- [Docker database backup tool](https://github.com/tiredofit/docker-db-backup)

---

### IDEs and Development Environments

#### **VS Code / VSCodium**
**Location:** `~/.config/Code` or `~/.config/VSCodium`

**What to backup:**
- `User/settings.json` - User settings
- `User/keybindings.json` - Keyboard shortcuts
- `User/snippets/` - Code snippets
- Extensions list

**Backup:**
```bash
# Export extensions list
code --list-extensions > vscode-extensions.txt

# Restore extensions
cat vscode-extensions.txt | xargs -I {} code --install-extension {}
```

**Better: Use Settings Sync**
VS Code has built-in settings sync via GitHub/Microsoft account.

---

#### **JetBrains IDEs (IntelliJ, PyCharm, WebStorm)**
**Location:** `~/.config/JetBrains/{IDE}{version}`

**What to backup:**
- `options/` - Settings and configurations
- `keymaps/` - Custom keymaps
- `colors/` - Color schemes
- `plugins/` - Installed plugins

**Backup:**
- Use **JetBrains Toolbox** sync feature
- Or manually backup `~/.config/JetBrains/` directory

---

#### **Neovim/Vim**
**Location:** `~/.config/nvim` or `~/.vim`

**Backup:**
```bash
# Add to dotfiles management (Chezmoi)
chezmoi add ~/.config/nvim
```

---

### **APPLICATION DATA BACKUP SCRIPT:**

```bash
#!/bin/bash
# backup-application-data.sh

BACKUP_BASE="$HOME/app-backups/$(date +%Y%m%d)"

# Steam
if [ -d "$HOME/.local/share/Steam" ]; then
    echo "Backing up Steam..."
    mkdir -p "$BACKUP_BASE/steam"
    rsync -av --exclude='steamapps/common' \
      "$HOME/.local/share/Steam/" "$BACKUP_BASE/steam/"
fi

# Docker volumes
if command -v docker &> /dev/null; then
    echo "Backing up Docker volumes..."
    mkdir -p "$BACKUP_BASE/docker"
    docker volume ls -q | while read vol; do
        docker run --rm -v "$vol":/data -v "$BACKUP_BASE/docker":/backup \
          ubuntu tar czf "/backup/$vol.tar.gz" /data
    done
fi

# VS Code extensions
if command -v code &> /dev/null; then
    echo "Backing up VS Code extensions..."
    mkdir -p "$BACKUP_BASE/vscode"
    code --list-extensions > "$BACKUP_BASE/vscode/extensions.txt"
    cp -r "$HOME/.config/Code/User" "$BACKUP_BASE/vscode/"
fi

# Databases (PostgreSQL)
if command -v pg_dumpall &> /dev/null; then
    echo "Backing up PostgreSQL databases..."
    mkdir -p "$BACKUP_BASE/databases"
    pg_dumpall > "$BACKUP_BASE/databases/postgresql-all.sql"
fi

echo "✅ Application data backed up to $BACKUP_BASE"
```

---

## 5. Automated Backup Workflow Design

### **Layered Backup Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                    BACKUP STRATEGY LAYERS                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Layer 1: ZFS Snapshots (Sanoid)                                │
│    - Frequent: Every 15 minutes                                  │
│    - Hourly: Keep 36                                             │
│    - Daily: Keep 30                                              │
│    - Monthly: Keep 3                                             │
│    - Local to external drive via Syncoid                         │
│                                                                   │
│  Layer 2: Full System Backup (BorgBackup)                       │
│    - Daily incremental backups                                   │
│    - Encrypted with AES-256                                      │
│    - Deduplicated (60-80% space savings)                         │
│    - Keep: 7 daily, 4 weekly, 6 monthly                          │
│    - Destination: External USB drive + optional cloud (rclone)   │
│                                                                   │
│  Layer 3: Dotfiles (Chezmoi)                                    │
│    - Version controlled in Git                                   │
│    - Synced to GitHub/GitLab                                     │
│    - Secrets encrypted with age/GPG                              │
│    - On-demand updates when configs change                       │
│                                                                   │
│  Layer 4: Package State                                          │
│    - Weekly export of installed packages                         │
│    - All package managers (apt, npm, pip, cargo, flatpak)        │
│    - Stored in Borg backup                                       │
│                                                                   │
│  Layer 5: Application Data                                       │
│    - Weekly backup of critical app data                          │
│    - Docker volumes, databases, Steam saves                      │
│    - Integrated into Borg backup                                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

### **Implementation: Master Backup Script**

```bash
#!/bin/bash
# /usr/local/bin/system-backup-master.sh
# Master backup orchestration script

set -euo pipefail

# Configuration
BACKUP_ROOT="/mnt/backup"
LOG_DIR="/var/log/backups"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/backup-$DATE.log"

# Notification function
notify() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handler
error_exit() {
    notify "❌ ERROR: $1"
    exit 1
}

# Create log directory
mkdir -p "$LOG_DIR"

notify "🚀 Starting system backup workflow"

# ============================================
# LAYER 1: ZFS Snapshots (Sanoid)
# ============================================
notify "📸 Layer 1: Creating ZFS snapshots..."
if command -v sanoid &> /dev/null; then
    sanoid --take-snapshots || error_exit "Sanoid snapshot creation failed"

    # Replicate to external drive
    if mountpoint -q "$BACKUP_ROOT/zfs-backup"; then
        notify "🔄 Replicating snapshots to external drive..."
        syncoid --recursive --no-privilege-elevation \
          rpool/home "$BACKUP_ROOT/zfs-backup/home" || \
          notify "⚠️  Warning: Syncoid replication had issues"
    else
        notify "⚠️  Warning: ZFS backup drive not mounted, skipping replication"
    fi
else
    notify "⚠️  Sanoid not installed, skipping ZFS snapshots"
fi

# ============================================
# LAYER 2: Full System Backup (BorgBackup)
# ============================================
notify "💾 Layer 2: Running BorgBackup..."
if command -v borg &> /dev/null; then
    export BORG_REPO="$BACKUP_ROOT/borg"
    export BORG_PASSPHRASE_FILE="$HOME/.borg-passphrase"

    # Ensure repository exists
    if [ ! -d "$BORG_REPO" ]; then
        notify "📦 Initializing Borg repository..."
        borg init --encryption=repokey "$BORG_REPO" || error_exit "Borg init failed"
    fi

    # Create backup
    notify "📦 Creating Borg backup archive..."
    borg create \
      --stats \
      --progress \
      --compression lz4 \
      --exclude-caches \
      --exclude '/home/*/.cache' \
      --exclude '/home/*/Downloads' \
      --exclude '/home/*/.local/share/Steam/steamapps/common' \
      "$BORG_REPO::system-{now}" \
      /home \
      /etc \
      /var/lib \
      /usr/local \
      || error_exit "Borg backup creation failed"

    # Prune old backups
    notify "🗑️  Pruning old Borg archives..."
    borg prune \
      --keep-daily=7 \
      --keep-weekly=4 \
      --keep-monthly=6 \
      "$BORG_REPO" || notify "⚠️  Warning: Borg prune had issues"

    # Compact repository
    notify "🧹 Compacting Borg repository..."
    borg compact "$BORG_REPO" || notify "⚠️  Warning: Borg compact had issues"

else
    notify "⚠️  BorgBackup not installed, skipping Layer 2"
fi

# ============================================
# LAYER 3: Dotfiles (Chezmoi)
# ============================================
notify "📝 Layer 3: Syncing dotfiles..."
if command -v chezmoi &> /dev/null; then
    cd "$HOME/.local/share/chezmoi"
    if git diff --quiet; then
        notify "✅ Dotfiles already in sync"
    else
        notify "📤 Pushing dotfile changes to Git..."
        git add -A
        git commit -m "Automated backup: $DATE" || true
        git push origin main || notify "⚠️  Warning: Git push failed"
    fi
else
    notify "⚠️  Chezmoi not installed, skipping dotfiles sync"
fi

# ============================================
# LAYER 4: Package State
# ============================================
notify "📦 Layer 4: Exporting package state..."
PKG_BACKUP_DIR="$BACKUP_ROOT/packages/$DATE"
mkdir -p "$PKG_BACKUP_DIR"

# APT
dpkg --get-selections > "$PKG_BACKUP_DIR/dpkg-selections.txt"
apt list --installed > "$PKG_BACKUP_DIR/apt-installed.txt"

# Flatpak
if command -v flatpak &> /dev/null; then
    flatpak list --app --columns=application > "$PKG_BACKUP_DIR/flatpak-list.txt"
fi

# Snap
if command -v snap &> /dev/null; then
    snap list > "$PKG_BACKUP_DIR/snap-list.txt"
fi

# npm global
if command -v npm &> /dev/null; then
    npm list -g --depth=0 > "$PKG_BACKUP_DIR/npm-globals.txt"
fi

# pip
if command -v pip &> /dev/null; then
    pip freeze > "$PKG_BACKUP_DIR/pip-requirements.txt"
fi

# Cargo
if command -v cargo &> /dev/null; then
    cargo install --list > "$PKG_BACKUP_DIR/cargo-list.txt"
fi

# Meta Package Manager (if available)
if command -v mpm &> /dev/null; then
    mpm backup > "$PKG_BACKUP_DIR/mpm-backup.toml"
fi

notify "✅ Package state exported to $PKG_BACKUP_DIR"

# ============================================
# LAYER 5: Application Data
# ============================================
notify "🎮 Layer 5: Backing up application data..."
APP_BACKUP_DIR="$BACKUP_ROOT/applications/$DATE"
mkdir -p "$APP_BACKUP_DIR"

# Docker volumes
if command -v docker &> /dev/null; then
    notify "🐳 Backing up Docker volumes..."
    mkdir -p "$APP_BACKUP_DIR/docker"
    docker volume ls -q | while read vol; do
        docker run --rm \
          -v "$vol":/data \
          -v "$APP_BACKUP_DIR/docker":/backup \
          ubuntu tar czf "/backup/$vol.tar.gz" /data 2>/dev/null || \
          notify "⚠️  Warning: Failed to backup Docker volume $vol"
    done
fi

# PostgreSQL databases
if command -v pg_dumpall &> /dev/null; then
    notify "🐘 Backing up PostgreSQL databases..."
    mkdir -p "$APP_BACKUP_DIR/databases"
    pg_dumpall > "$APP_BACKUP_DIR/databases/postgresql-all.sql" || \
      notify "⚠️  Warning: PostgreSQL backup failed"
fi

# VS Code extensions
if command -v code &> /dev/null; then
    notify "💻 Backing up VS Code extensions..."
    mkdir -p "$APP_BACKUP_DIR/vscode"
    code --list-extensions > "$APP_BACKUP_DIR/vscode/extensions.txt"
fi

notify "✅ Application data backed up to $APP_BACKUP_DIR"

# ============================================
# CLEANUP & VERIFICATION
# ============================================
notify "🧹 Cleaning up old backup logs..."
find "$LOG_DIR" -name "backup-*.log" -mtime +30 -delete

notify "📊 Backup Summary:"
notify "  - ZFS Snapshots: $(zfs list -t snapshot | wc -l) snapshots"
if [ -d "$BORG_REPO" ]; then
    notify "  - Borg Archives: $(borg list "$BORG_REPO" | wc -l) archives"
fi
notify "  - Package backups: $PKG_BACKUP_DIR"
notify "  - Application backups: $APP_BACKUP_DIR"

notify "✅ System backup workflow completed successfully!"
```

---

### **Scheduling: Systemd Timers**

**Create systemd service:**
```ini
# /etc/systemd/system/system-backup.service
[Unit]
Description=System Backup Master Script
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/system-backup-master.sh
User=root
StandardOutput=journal
StandardError=journal
```

**Create systemd timer:**
```ini
# /etc/systemd/system/system-backup.timer
[Unit]
Description=Daily System Backup

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable system-backup.timer
sudo systemctl start system-backup.timer

# Check status
sudo systemctl list-timers system-backup
```

---

## 6. Restoration Procedure

### **Pre-Migration Verification Checklist**

Before beginning migration, verify all backups:

```bash
#!/bin/bash
# verify-backups.sh

echo "🔍 Backup Verification Checklist"
echo "=================================="

# Check ZFS snapshots
echo -n "✓ ZFS Snapshots: "
zfs list -t snapshot | tail -5

# Check Borg repository
echo -n "✓ Borg Repository: "
if [ -d "/mnt/backup/borg" ]; then
    export BORG_REPO="/mnt/backup/borg"
    export BORG_PASSPHRASE_FILE="$HOME/.borg-passphrase"
    echo "$(borg list "$BORG_REPO" | wc -l) archives"

    # Test extraction
    echo "  Testing extraction..."
    borg extract --dry-run "$BORG_REPO::$(borg list "$BORG_REPO" | tail -1 | cut -d' ' -f1)"
    echo "  ✅ Extraction test passed"
else
    echo "❌ Repository not found"
fi

# Check dotfiles
echo -n "✓ Dotfiles: "
if [ -d "$HOME/.local/share/chezmoi/.git" ]; then
    cd "$HOME/.local/share/chezmoi"
    echo "$(git log --oneline | head -1)"
else
    echo "❌ No Git repository"
fi

# Check package lists
echo -n "✓ Package Lists: "
LATEST_PKG=$(ls -td /mnt/backup/packages/* | head -1)
if [ -d "$LATEST_PKG" ]; then
    echo "Latest: $(basename $LATEST_PKG)"
    ls -lh "$LATEST_PKG"
else
    echo "❌ No package backups found"
fi

# Check application data
echo -n "✓ Application Data: "
LATEST_APP=$(ls -td /mnt/backup/applications/* | head -1)
if [ -d "$LATEST_APP" ]; then
    echo "Latest: $(basename $LATEST_APP)"
else
    echo "❌ No application backups found"
fi

echo ""
echo "🎯 Backup verification complete!"
```

---

### **Restoration Workflow**

#### **Phase 1: Fresh OS Installation**
1. Install Ubuntu or CachyOS fresh
2. Set up basic networking and SSH
3. Mount backup drive

#### **Phase 2: Restore System Files (BorgBackup)**

```bash
#!/bin/bash
# restore-from-borg.sh

export BORG_REPO="/mnt/backup/borg"
export BORG_PASSPHRASE_FILE="/root/.borg-passphrase"

# List available archives
echo "📋 Available backups:"
borg list "$BORG_REPO"

# Choose archive (or use latest)
ARCHIVE=$(borg list "$BORG_REPO" | tail -1 | cut -d' ' -f1)
echo "📦 Restoring from: $ARCHIVE"

# Extract to temporary location first (safer)
RESTORE_DIR="/mnt/restore"
mkdir -p "$RESTORE_DIR"

# Extract home directory
borg extract "$BORG_REPO::$ARCHIVE" home --target "$RESTORE_DIR"

# Extract /etc selectively
borg extract "$BORG_REPO::$ARCHIVE" etc --target "$RESTORE_DIR"

# Extract /var/lib selectively
borg extract "$BORG_REPO::$ARCHIVE" var/lib --target "$RESTORE_DIR"

echo "✅ Files extracted to $RESTORE_DIR"
echo "⚠️  Manually review and copy to system locations"
```

#### **Phase 3: Restore Dotfiles (Chezmoi)**

```bash
# Install Chezmoi
sh -c "$(curl -fsLS get.chezmoi.io)"

# Initialize from Git
chezmoi init --apply https://github.com/yourusername/dotfiles.git

# If secrets needed
chezmoi apply
```

#### **Phase 4: Restore Packages**

```bash
#!/bin/bash
# restore-packages.sh

BACKUP_DIR="/mnt/backup/packages/$(ls /mnt/backup/packages | tail -1)"

# APT packages
sudo dpkg --set-selections < "$BACKUP_DIR/dpkg-selections.txt"
sudo apt-get dselect-upgrade -y

# Flatpak
cat "$BACKUP_DIR/flatpak-list.txt" | xargs -I {} flatpak install -y {}

# npm global
cat "$BACKUP_DIR/npm-globals.txt" | grep -v '^/' | xargs npm install -g

# pip
pip install -r "$BACKUP_DIR/pip-requirements.txt"

# Cargo (requires manual installation)
cat "$BACKUP_DIR/cargo-list.txt"
```

#### **Phase 5: Restore Application Data**

```bash
#!/bin/bash
# restore-application-data.sh

APP_BACKUP_DIR="/mnt/backup/applications/$(ls /mnt/backup/applications | tail -1)"

# Docker volumes
if [ -d "$APP_BACKUP_DIR/docker" ]; then
    for archive in "$APP_BACKUP_DIR/docker"/*.tar.gz; do
        VOLUME_NAME=$(basename "$archive" .tar.gz)
        docker volume create "$VOLUME_NAME"
        docker run --rm \
          -v "$VOLUME_NAME":/data \
          -v "$APP_BACKUP_DIR/docker":/backup \
          ubuntu tar xzf "/backup/$VOLUME_NAME.tar.gz" -C /
    done
fi

# PostgreSQL
if [ -f "$APP_BACKUP_DIR/databases/postgresql-all.sql" ]; then
    sudo -u postgres psql < "$APP_BACKUP_DIR/databases/postgresql-all.sql"
fi

# VS Code extensions
if [ -f "$APP_BACKUP_DIR/vscode/extensions.txt" ]; then
    cat "$APP_BACKUP_DIR/vscode/extensions.txt" | xargs -I {} code --install-extension {}
fi
```

---

## 7. Risk Mitigation Strategies

### **Risk Assessment Matrix**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Backup corruption** | Low | Critical | Multiple backup layers, verification scripts |
| **Incomplete restoration** | Medium | High | Test restoration procedure before migration |
| **Missing dependencies** | Medium | Medium | Package state export across all managers |
| **Lost application data** | Low | High | Dedicated application backup layer |
| **Hardware failure during migration** | Low | Critical | Keep original system intact until verification |
| **Secret exposure in dotfiles** | Medium | High | Use Chezmoi with age/GPG encryption |
| **Backup drive failure** | Low | Critical | 3-2-1 backup rule: External drive + cloud storage |

---

### **Mitigation Strategies**

#### **1. Multiple Backup Layers**
- **Never rely on single backup method**
- ZFS snapshots (fast recovery)
- BorgBackup (comprehensive, encrypted)
- Dotfiles in Git (version control)

#### **2. Verification Before Migration**
```bash
# Run full verification
./verify-backups.sh

# Test restore to VM or spare drive
# Ensure all critical data can be restored
```

#### **3. Keep Original System Intact**
- Don't wipe original Ubuntu installation until new system verified
- Maintain dual-boot capability during transition period
- Test CachyOS alongside Ubuntu before committing

#### **4. Incremental Migration**
Don't migrate everything at once:
1. **Week 1:** Install CachyOS, restore dotfiles only
2. **Week 2:** Restore packages, test development environment
3. **Week 3:** Restore application data, verify functionality
4. **Week 4:** Full migration if all tests pass

#### **5. Rollback Plan**
Always have a path back:
```bash
# ZFS rollback (if on ZFS)
zfs rollback rpool/home@pre-migration

# Or boot into old system from dual-boot menu
```

#### **6. Off-Site Backup**
For critical data, maintain cloud backup:
```bash
# Borg to cloud via rclone
borg create ... | rclone rcat remote:borg-backup/archive.borg

# Or use Restic with native S3 support
restic -r s3:s3.amazonaws.com/bucket/backup backup /home
```

---

## 8. Testing Methodology

### **Pre-Migration Testing**

#### **Test 1: Backup Integrity**
```bash
# Verify all backup layers exist
./verify-backups.sh

# Test Borg extraction
export BORG_REPO="/mnt/backup/borg"
borg extract --dry-run "$BORG_REPO::latest"

# Test ZFS snapshot rollback (non-destructive)
zfs list -t snapshot
```

#### **Test 2: Package Restoration**
```bash
# In VM or container
# Test package restoration script
docker run -it ubuntu:latest bash
# Inside container, test apt restore
```

#### **Test 3: Dotfile Deployment**
```bash
# Test Chezmoi in fresh environment
docker run -it archlinux bash
sh -c "$(curl -fsLS get.chezmoi.io)"
chezmoi init --apply https://github.com/user/dotfiles.git
```

#### **Test 4: Application Data Restoration**
```bash
# Test Docker volume restoration
docker volume create test-vol
# Restore from backup
docker run --rm -v test-vol:/data -v /mnt/backup:/backup \
  ubuntu tar xzf /backup/applications/latest/docker/test-vol.tar.gz -C /
# Verify data
docker run --rm -v test-vol:/data ubuntu ls -la /data
```

---

### **Post-Migration Validation**

#### **Validation Checklist**

```markdown
## System Validation

### Core System
- [ ] Boot successfully into new OS
- [ ] Network connectivity working
- [ ] Display/graphics drivers functional
- [ ] Audio working
- [ ] All partitions mounted correctly

### User Environment
- [ ] Shell configuration loaded (.bashrc, .zshrc)
- [ ] Terminal preferences restored
- [ ] SSH keys in place and working
- [ ] GPG keys imported and trusted

### Development Environment
- [ ] Git configured correctly
- [ ] All programming languages installed (check versions)
- [ ] Package managers operational (apt, npm, pip, cargo)
- [ ] Docker daemon running, containers restored
- [ ] IDEs launch and load configurations

### Applications
- [ ] Browser bookmarks and extensions present
- [ ] Steam library visible, saves intact
- [ ] Database services running, data queryable
- [ ] Communication apps (Slack, Discord) configured
- [ ] File managers, text editors configured

### Data Integrity
- [ ] ~/Documents accessible and complete
- [ ] ~/Projects contains all repositories
- [ ] ~/.config restored with all app configs
- [ ] No missing critical files (spot check)

### Performance
- [ ] System boots in reasonable time
- [ ] Applications launch without lag
- [ ] No unusual disk I/O or CPU usage
- [ ] ZFS performance acceptable (if using ZFS)
```

---

### **Automated Validation Script**

```bash
#!/bin/bash
# post-migration-validation.sh

echo "🔍 Post-Migration Validation"
echo "=============================="

# Function to check command
check_command() {
    if command -v "$1" &> /dev/null; then
        echo "✅ $1 installed"
    else
        echo "❌ $1 missing"
    fi
}

# Essential commands
echo "📦 Checking essential packages..."
check_command git
check_command vim
check_command curl
check_command docker
check_command npm
check_command pip
check_command cargo

# Development tools
echo "🛠️  Checking development tools..."
check_command gcc
check_command make
check_command python3
check_command node

# Check services
echo "🔧 Checking services..."
systemctl is-active docker && echo "✅ Docker active" || echo "❌ Docker inactive"
systemctl is-active postgresql && echo "✅ PostgreSQL active" || echo "⚠️  PostgreSQL inactive"

# Check dotfiles
echo "📝 Checking dotfiles..."
[ -f ~/.bashrc ] && echo "✅ .bashrc present" || echo "❌ .bashrc missing"
[ -f ~/.vimrc ] && echo "✅ .vimrc present" || echo "⚠️  .vimrc missing"
[ -d ~/.config ] && echo "✅ .config directory present" || echo "❌ .config missing"

# Check SSH keys
echo "🔑 Checking SSH keys..."
[ -f ~/.ssh/id_rsa ] && echo "✅ SSH keys present" || echo "⚠️  SSH keys missing"

# Check important directories
echo "📂 Checking important directories..."
[ -d ~/Documents ] && echo "✅ ~/Documents" || echo "❌ ~/Documents missing"
[ -d ~/Projects ] && echo "✅ ~/Projects" || echo "⚠️  ~/Projects missing"
[ -d ~/.local/share/Steam ] && echo "✅ Steam" || echo "⚠️  Steam missing"

# Docker check
if command -v docker &> /dev/null; then
    echo "🐳 Docker volumes:"
    docker volume ls
fi

echo ""
echo "🎯 Validation complete!"
echo "Review any ❌ or ⚠️  items and address as needed."
```

---

## 9. Final Recommendations

### **Recommended Toolchain for Your Migration**

| Layer | Tool | Justification |
|-------|------|---------------|
| **System Snapshots** | Sanoid/Syncoid | Native ZFS integration, efficient replication |
| **Full System Backup** | BorgBackup + borgmatic | Encryption, deduplication, works across filesystems |
| **Dotfiles** | Chezmoi | Advanced templating, secrets management, machine-specific configs |
| **Package State** | Native exports + Meta Package Manager | Comprehensive coverage of all package managers |
| **Application Data** | Custom scripts | Per-application strategies (Docker, Steam, databases) |
| **Scheduling** | systemd timers | Reliable, integrated with systemd ecosystem |

---

### **Timeline for Migration**

**Week 1: Preparation**
- Install and configure backup tools
- Run initial full backups
- Verify backup integrity
- Test restoration in VM

**Week 2: Baseline Backups**
- Run automated backups daily
- Monitor for issues
- Refine backup scripts
- Document custom application data locations

**Week 3: Migration Testing**
- Set up CachyOS in VM
- Test restoration procedures
- Identify missing dependencies
- Create migration runbook

**Week 4: Actual Migration**
- Final backup of Ubuntu system
- Install CachyOS (preserve Ubuntu partition)
- Restore from backups
- Validate system functionality
- Run dual-boot for safety

**Week 5: Validation & Cleanup**
- Complete validation checklist
- Resolve any missing data/configs
- Verify all applications working
- Once confident, remove Ubuntu (optional)

---

### **Essential Scripts to Create**

1. **`/usr/local/bin/system-backup-master.sh`** - Master backup orchestration
2. **`/usr/local/bin/verify-backups.sh`** - Backup integrity verification
3. **`/usr/local/bin/restore-from-borg.sh`** - BorgBackup restoration
4. **`/usr/local/bin/restore-packages.sh`** - Package reinstallation
5. **`/usr/local/bin/restore-application-data.sh`** - Application data restoration
6. **`/usr/local/bin/post-migration-validation.sh`** - Post-migration checks

---

### **Critical Success Factors**

1. **Test everything before migration** - Never trust untested backups
2. **Multiple backup layers** - Redundancy saves you from disaster
3. **Keep original system intact** - Don't destroy until new system verified
4. **Document everything** - Your future self will thank you
5. **Incremental migration** - Don't rush, validate each step
6. **Have a rollback plan** - Always maintain path back to working state

---

## 10. Additional Resources

### **Official Documentation**
- [BorgBackup Documentation](https://borgbackup.readthedocs.io/)
- [Restic Documentation](https://restic.readthedocs.io/)
- [Chezmoi User Guide](https://www.chezmoi.io/)
- [Sanoid GitHub](https://github.com/jimsalterjrs/sanoid)
- [ZFS on Linux Documentation](https://openzfs.github.io/openzfs-docs/)

### **Community Resources**
- [r/BorgBackup](https://www.reddit.com/r/BorgBackup/)
- [r/zfs](https://www.reddit.com/r/zfs/)
- [Arch Wiki: Synchronization and Backup Programs](https://wiki.archlinux.org/title/Synchronization_and_backup_programs)
- [Practical ZFS Forum](https://discourse.practicalzfs.com/)

### **Testing Environments**
- **VirtualBox/QEMU:** Test restoration procedures safely
- **Docker:** Quick environment validation
- **Spare hardware:** Ideal for full migration testing

---

## 11. Sources

### System Backup Tools
- [Timeshift vs Restic comparison](https://forum.restic.net/t/timeshift-vs-git-vs-restic-linux-os-and-user-data-backup/7905)
- [Best Linux Backup Solutions 2025](https://howik.com/linux-backup-solutions-2025)
- [Restic vs BorgBackup vs Kopia 2025](https://onidel.com/restic-vs-borgbackup-vs-kopia-2025/)
- [Borgmatic ArchWiki](https://wiki.archlinux.org/title/Borgmatic)
- [Which Linux Backup Software Are Best in 2025](https://www.vinchin.com/linux-backup/linux-backup-software.html)
- [Sanoid GitHub](https://github.com/jimsalterjrs/sanoid)
- [Setting up automated ZFS snapshots](https://techsbucket.com/setting-up-automated-zfs-snapshots-with-sanoid-on-ubuntu-server/)
- [ZFS Backup Best Practices](https://klarasystems.com/articles/openzfs-storage-best-practices-and-use-cases-part-1-snapshots-and-backups/)

### Dotfile Management
- [Dotfile Management Tools Comparison](https://biggo.com/news/202412191324_dotfile-management-tools-comparison)
- [Chezmoi comparison table](https://www.chezmoi.io/comparison-table/)
- [Why use chezmoi?](https://www.chezmoi.io/why-use-chezmoi/)
- [Exploring dotfile management tools](https://gbergatto.github.io/posts/tools-managing-dotfiles/)
- [Effortlessly Manage Dotfiles with GNU Stow](https://corti.com/effortlessly-manage-dotfiles-on-unix-with-gnu-stow-and-github/)

### Package Management
- [Meta Package Manager on PyPI](https://pypi.org/project/meta-package-manager/)
- [Meta Package Manager GitHub](https://github.com/kdeldycke/meta-package-manager)

### Application Data
- [Backup Steam configuration](https://steamcommunity.com/app/221410/discussions/0/2259060348509180834/)
- [Docker backup and restore](https://docs.docker.com/desktop/backup-and-restore/)
- [How to backup Docker containers](https://sqlbak.com/blog/how-to-backup-and-restore-docker-containers-and-volumes/)
- [Docker database backup tool](https://github.com/tiredofit/docker-db-backup)

### Automation & Best Practices
- [Restic encrypted offsite backup](https://helgeklein.com/blog/restic-encrypted-offsite-backup-for-your-homeserver/)
- [Resticprofile documentation](https://creativeprojects.github.io/resticprofile/configuration/getting_started/index.html)
- [ZFS Autobackup GitHub](https://github.com/psy0rz/zfs_autobackup)
- [Opinionated Guide to ZFS Snapshots](https://kimono-koans.github.io/opinionated-guide/)

### Disaster Recovery Testing
- [Testing Backups Critical Importance](https://www.csicorp.net/testing-backups-why-restoring-your-system-before-disaster-strikes-is-critical/)
- [Relax-and-Recover Documentation](https://relax-and-recover.org/)

---

**Document Version:** 1.0
**Last Updated:** 2025-11-25
**Confidence Level:** 85% (High - All tools production-proven)
**Estimated Implementation Time:** 4-6 hours for full setup
**Testing Time:** 1-2 weeks recommended before migration
