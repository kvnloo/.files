#!/usr/bin/env bash
# Install a latency-first RAM -> zram -> NVMe -> SATA SSD swap hierarchy.
set -euo pipefail

if ((EUID != 0)); then
  printf 'Run with sudo: sudo %q\n' "$0" >&2
  exit 1
fi

swap_size=${SWAP_SIZE:-128G}
swap_dir=/mnt/zer0models/.swap
swap_file=$swap_dir/emergency.swap
emergency_priority=10
mount_point=/mnt/zer0models
sysctl_file=/etc/sysctl.d/99-z-memory-latency.conf
zram_file=/etc/systemd/zram-generator.conf
fstab=/etc/fstab
backup_dir=/var/tmp/memory-latency-backup-$(date +%Y%m%d-%H%M%S)

command -v btrfs >/dev/null 2>&1 || { printf 'btrfs-progs is required\n' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { printf 'python3 is required\n' >&2; exit 1; }
mountpoint -q "$mount_point" || { printf '%s is not mounted\n' "$mount_point" >&2; exit 1; }
[[ $(findmnt -n -o FSTYPE "$mount_point") == btrfs ]] || {
  printf '%s must be a Btrfs mount\n' "$mount_point" >&2
  exit 1
}

install -d -m 0700 "$backup_dir"
for source in "$sysctl_file" "$zram_file" "$fstab"; do
  [[ -e $source ]] && cp -a "$source" "$backup_dir/"
done
printf 'Backup: %s\n' "$backup_dir"

cat >"$sysctl_file" <<'EOF'
# Latency-first memory policy for 16 GiB RAM, compressed swap, and heavy agents.
# Zram remains cheap enough to prefer over refaulting files; physical swap is
# ordered by priority and exists for survival, not as working memory.
vm.swappiness = 150
vm.vfs_cache_pressure = 50
vm.watermark_scale_factor = 125
vm.page-cluster = 0
vm.dirty_bytes = 268435456
vm.dirty_background_bytes = 67108864
vm.overcommit_memory = 0
vm.overcommit_ratio = 100
EOF

cat >"$zram_file" <<'EOF'
[zram0]
# The device size is uncompressed capacity and allocates RAM only as pages arrive.
# 24 GiB is the measured sweet spot for this 16 GiB machine's ~2.7:1 ratio.
zram-size = min(ram * 3 / 2, 24576)
compression-algorithm = zstd
swap-priority = 200
options = discard
EOF

install -d -m 0700 "$swap_dir"
if [[ ! -e $swap_file ]]; then
  printf 'Creating %s emergency swap on the SATA SSD...\n' "$swap_size"
  btrfs filesystem mkswapfile --size "$swap_size" "$swap_file"
fi
chown root:root "$swap_file"
chmod 0600 "$swap_file"
btrfs inspect-internal map-swapfile -r "$swap_file" >/dev/null

python3 - "$fstab" "$swap_file" "$emergency_priority" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
swap_file = sys.argv[2]
emergency_priority = sys.argv[3]
lines = path.read_text().splitlines()
output = []
seen_emergency = False
for line in lines:
    stripped = line.strip()
    fields = stripped.split()
    if not stripped or stripped.startswith("#") or len(fields) < 4:
        output.append(line)
        continue
    if fields[0] == swap_file and fields[2] == "swap":
        fields[3] = f"defaults,nofail,pri={emergency_priority}"
        output.append("\t".join(fields))
        seen_emergency = True
        continue
    if fields[2] == "swap" and fields[0] != swap_file:
        options = [
            option
            for option in fields[3].split(",")
            if option != "defaults" and not option.startswith("pri=")
        ]
        fields[3] = ",".join(["defaults", *options, "pri=50"])
        output.append("\t".join(fields))
        continue
    output.append(line)
if not seen_emergency:
    output.extend([
        "",
        "# Low-priority emergency capacity; zram and NVMe swap are used first.",
        f"{swap_file}\tnone\tswap\tdefaults,nofail,pri={emergency_priority}\t0\t0",
    ])
path.write_text("\n".join(output) + "\n")
PY

emergency_state=$(
  swapon --show=NAME,TYPE,USED,PRIO --bytes --noheadings |
    awk -v target="$swap_file" '$1 == target {print $3, $4}'
)
if [[ -n $emergency_state ]]; then
  read -r emergency_used active_priority <<<"$emergency_state"
  if [[ $active_priority != "$emergency_priority" ]]; then
    if ((emergency_used == 0)); then
      swapoff "$swap_file"
    else
      printf 'Emergency swap is in use at priority %s; reboot is required to change it safely.\n' "$active_priority"
    fi
  fi
fi

if ! swapon --show=NAME --noheadings | grep -Fxq "$swap_file"; then
  fastest_disk_priority=$(
    swapon --show=NAME,TYPE,PRIO --noheadings |
      awk '$2 == "partition" && $1 != "/dev/zram0" {if (!seen || $3 > max) {max=$3; seen=1}} END {print seen ? max : -1}'
  )
  if ((fastest_disk_priority > emergency_priority)); then
    swapon --priority "$emergency_priority" "$swap_file"
  else
    printf 'Emergency swap stays disabled until reboot establishes NVMe priority 50.\n'
  fi
fi

sysctl --system >/dev/null
systemctl daemon-reload

printf '\nActive swap hierarchy:\n'
swapon --show=NAME,TYPE,SIZE,USED,PRIO
printf '\nInstalled VM policy:\n'
sysctl vm.swappiness vm.page-cluster vm.dirty_bytes vm.dirty_background_bytes vm.overcommit_memory
printf '\nZram expands to 24 GiB on the next reboot; existing active zram cannot be resized safely under pressure.\n'
printf 'Emergency swap size defaults to 128 GiB. Override only when justified: SWAP_SIZE=256G sudo %q\n' "$0"
