#!/usr/bin/env bash
# expand-root-from-rescue.sh v1.0.0
# Bounded, host-specific removal of obsolete disk swap to grow the adjacent XFS root.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

readonly VERSION="1.0.0"
readonly TARGET_BY_ID="/dev/disk/by-id/nvme-Samsung_SSD_960_EVO_500GB_S3EUNB0J523446Z"
readonly EXPECTED_DISK="/dev/nvme0n1"
readonly EXPECTED_MODEL="Samsung SSD 960 EVO 500GB"
readonly EXPECTED_SERIAL="S3EUNB0J523446Z"
readonly SERIAL_SUFFIX="23446Z"
readonly SECTOR_SIZE=512
readonly DISK_SECTORS=976773168
readonly P1_START=4196352
readonly P1_OLD_SIZE=209715200
readonly P1_NEW_SIZE=276824064
readonly ROOT_UUID="9e575c2d-52cc-41ec-8b3f-15afd8191c81"
readonly P2_START=213911552
readonly P2_SIZE=67108864
readonly SWAP_UUID="316f4699-5371-4798-9873-68f2b6194cb4"
readonly P3_START=281020416
readonly P3_SIZE=695752719
readonly WORKSPACE_UUID="f70404dd-c13b-4070-8d7c-d6d5e91db153"
readonly CONFIRM_TEXT="EXPAND 23446Z P1 4196352-281020415 DELETE P2 KEEP P3 281020416"
readonly MIN_RECEIPT_BYTES=1048576

MODE=plan
OUTPUT_DIR=""
CONFIRM=""
MOUNT_DIR="/mnt/installed-root-expand"
STATE="init"
RECEIPT_DIR=""
TABLE_BACKUP=""
FSTAB_BACKUP=""
ROOT_MOUNTED_BY_US=0
GROW_STARTED=0
TEST_MODE="${RESCUE_EXPAND_TEST_MODE:-0}"
FIXTURE="${RESCUE_EXPAND_FIXTURE:-}"

usage() {
  cat <<EOF
Usage: sudo $0 [--plan | --verify-only | --apply] --output-dir PATH [--confirm TEXT]

Default: --plan. All modes are rescue/live-only and require root. --apply also
requires this exact typed confirmation:
  $CONFIRM_TEXT

Receipts must be stored on a persistent filesystem that is not target p1/p2/p3.
No mode formats, reboots, or modifies p3. Version: $VERSION
EOF
}

die() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command missing: $1"; }

while (($#)); do
  case "$1" in
    --plan) MODE=plan ;;
    --verify-only) MODE=verify ;;
    --apply) MODE=apply ;;
    --output-dir) shift; (($#)) || die "--output-dir requires PATH"; OUTPUT_DIR=$1 ;;
    --confirm) shift; (($#)) || die "--confirm requires TEXT"; CONFIRM=$1 ;;
    --help|-h) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

# Tests may only consume regular JSON fixtures and can never enter apply.
if [[ "$TEST_MODE" == 1 ]]; then
  [[ "$MODE" != apply ]] || die "apply is disabled in test mode"
  [[ -n "$FIXTURE" && -f "$FIXTURE" && ! -L "$FIXTURE" ]] || die "test mode requires a regular fixture"
else
  [[ $EUID -eq 0 ]] || die "must run as root from the CachyOS rescue/live environment"
fi
if [[ "$MODE" == apply ]]; then
  [[ "$CONFIRM" == "$CONFIRM_TEXT" ]] || die "typed confirmation mismatch; nothing changed"
fi

[[ -n "$OUTPUT_DIR" ]] || die "--output-dir is required (persistent external storage)"
[[ "$OUTPUT_DIR" = /* ]] || die "output directory must be absolute"
if [[ "$TEST_MODE" != 1 ]]; then
  case "$OUTPUT_DIR" in /tmp|/tmp/*|/run|/run/*|/dev|/dev/*|/proc|/proc/*|/sys|/sys/*) die "output directory cannot be live RAM or a virtual filesystem";; esac
fi

if [[ "$TEST_MODE" != 1 ]]; then
  grep -Eq '(^| )(archisobasedir|cow_spacesize|copytoram)=' /proc/cmdline || \
    [[ -d /run/archiso || -e /etc/cachyos-release ]] || \
    die "boot environment is not recognized as CachyOS/Arch rescue/live"
  root_source=$(findmnt -rn -o SOURCE /)
  root_fstype=$(findmnt -rn -o FSTYPE /)
  [[ "$root_source" != "$EXPECTED_DISK"p1 && "$root_source" != "$TARGET_BY_ID"-part1 ]] || \
    die "installed root is mounted as /; boot the rescue USB"
  [[ "$root_fstype" == overlay || "$root_source" == overlay || -d /run/archiso ]] || \
    die "live root is not an overlay/archiso environment"
fi

for cmd in python3 sha256sum date; do need "$cmd"; done

collect_json() {
  if [[ "$TEST_MODE" == 1 ]]; then
    printf '%s\n' "$FIXTURE"
  else
    local path resolved
    [[ -L "$TARGET_BY_ID" ]] || die "stable target by-id is absent: $TARGET_BY_ID"
    resolved=$(readlink -f -- "$TARGET_BY_ID")
    [[ "$resolved" == "$EXPECTED_DISK" ]] || die "by-id resolves to $resolved, expected $EXPECTED_DISK"
    path="$RECEIPT_DIR/lsblk.json"
    lsblk --json -b -o NAME,PATH,TYPE,SIZE,START,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,MODEL,SERIAL,LOG-SEC,PHY-SEC "$TARGET_BY_ID" >"$path"
    printf '%s\n' "$path"
  fi
}

validate_geometry() {
  local json=$1
  python3 - "$json" "$MODE" <<'PY'
import json,sys
p,mode=sys.argv[1:]
d=json.load(open(p,encoding='utf-8'))
xs=d.get('blockdevices',[])
if len(xs)!=1: raise SystemExit('REFUSED: expected exactly one target disk')
disk=xs[0]
def req(ok,msg):
    if not ok: raise SystemExit('REFUSED: '+msg)
req(disk.get('type')=='disk','target is not a disk')
req(disk.get('size')==500107862016,'disk size drift')
req(disk.get('model')=='Samsung SSD 960 EVO 500GB','disk model drift')
req(disk.get('serial')=='S3EUNB0J523446Z','disk serial drift')
req(disk.get('log-sec')==512 and disk.get('phy-sec')==512,'sector size drift')
parts={x.get('name','').split('p')[-1]:x for x in disk.get('children',[])}
expected={
'1':(4196352,209715200,'xfs','9e575c2d-52cc-41ec-8b3f-15afd8191c81','5fed8d1d-f6a6-44d3-9608-0408425a9383'),
'2':(213911552,67108864,'swap','316f4699-5371-4798-9873-68f2b6194cb4','c3c2176b-e843-4490-958c-c73eb542a22d'),
'3':(281020416,695752719,'xfs','f70404dd-c13b-4070-8d7c-d6d5e91db153','ffbd4444-5995-4ed1-abd1-c0ac108848ef'),
'4':(2048,4194304,'vfat','DBCE-C10E','11878bd8-0fee-471e-90b7-3c18db40fa85'),
}
# already-grown is valid only for verify; plan reports it; apply must refuse later.
already=(set(parts)=={'1','3','4'} and
         parts['1'].get('start')==4196352 and parts['1'].get('size')==276824064*512 and
         parts['1'].get('fstype')=='xfs' and parts['1'].get('uuid')=='9e575c2d-52cc-41ec-8b3f-15afd8191c81' and
         parts['3'].get('start')==281020416 and parts['3'].get('size')==695752719*512 and
         parts['3'].get('fstype')=='xfs' and parts['3'].get('uuid')=='f70404dd-c13b-4070-8d7c-d6d5e91db153' and
         parts['3'].get('partuuid')=='ffbd4444-5995-4ed1-abd1-c0ac108848ef' and
         parts['4'].get('start')==2048 and parts['4'].get('size')==4194304*512 and
         parts['4'].get('fstype')=='vfat' and parts['4'].get('uuid')=='DBCE-C10E' and
         parts['4'].get('partuuid')=='11878bd8-0fee-471e-90b7-3c18db40fa85')
if already:
    req(not any(parts['1'].get('mountpoints') or []),'grown p1 is mounted/in use')
    req(not any(parts['3'].get('mountpoints') or []),'grown p3 is mounted/in use')
    print('already-grown'); raise SystemExit(0)
req(set(parts)=={'1','2','3','4'},'partition set drift or ambiguity')
for n,(start,size,fs,uuid,partuuid) in expected.items():
    x=parts[n]
    req(x.get('type')=='part',f'p{n} type ambiguity')
    req(x.get('start')==start and x.get('size')==size*512,f'p{n} geometry drift')
    req(x.get('fstype')==fs,f'p{n} filesystem drift')
    req(x.get('uuid')==uuid,f'p{n} UUID drift')
    req(x.get('partuuid')==partuuid,f'p{n} PARTUUID drift')
    mounts=x.get('mountpoints') or []
    req(not mounts or (n=='2' and mounts==['[SWAP]']),f'p{n} is mounted/in use')
req(parts['1']['start']+parts['1']['size']//512==parts['2']['start'],'p1/p2 are not adjacent')
req(parts['2']['start']+parts['2']['size']//512==parts['3']['start'],'p2 is not exactly between p1 and p3')
for x in parts.values():
    req((x.get('fstype') or '') not in {'crypto_LUKS','LVM2_member','linux_raid_member'},'LUKS/LVM/RAID ambiguity')
print('original')
PY
}

prepare_receipts() {
  [[ "$TEST_MODE" == 1 ]] && { RECEIPT_DIR=$OUTPUT_DIR; return; }
  [[ -d "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || die "output directory must already exist and not be a symlink"
  local out_source out_type avail
  out_source=$(findmnt -rn -o SOURCE --target "$OUTPUT_DIR")
  out_type=$(findmnt -rn -o FSTYPE --target "$OUTPUT_DIR")
  case "$out_source" in "$EXPECTED_DISK"p1|"$EXPECTED_DISK"p2|"$EXPECTED_DISK"p3|"$TARGET_BY_ID"-part1|"$TARGET_BY_ID"-part2|"$TARGET_BY_ID"-part3) die "receipt path is on a modified/at-risk target partition";; esac
  [[ "$out_type" != tmpfs && "$out_type" != overlay ]] || die "receipt path is not persistent"
  avail=$(df -PB1 --output=avail "$OUTPUT_DIR" | tr -cd '0-9')
  [[ -n "$avail" && "$avail" -ge "$MIN_RECEIPT_BYTES" ]] || die "receipt filesystem has insufficient free space"
  RECEIPT_DIR="$OUTPUT_DIR/expand-root-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mkdir -m 700 "$RECEIPT_DIR"
  TABLE_BACKUP="$RECEIPT_DIR/partition-table.sfdisk"
  date -u +%FT%TZ >"$RECEIPT_DIR/started-at.txt"
  printf '%s\n' preflight >"$RECEIPT_DIR/checkpoint"
  STATE=preflight
  sfdisk --dump "$TARGET_BY_ID" >"$TABLE_BACKUP"
  lsblk --json -b -o NAME,PATH,TYPE,SIZE,START,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,MODEL,SERIAL,LOG-SEC,PHY-SEC "$TARGET_BY_ID" >"$RECEIPT_DIR/lsblk.json"
  findmnt --json >"$RECEIPT_DIR/findmnt.json"
  blkid >"$RECEIPT_DIR/blkid.txt" || true
  swapon --show --bytes >"$RECEIPT_DIR/swapon.txt" || true
  udevadm info --query=property --name="$EXPECTED_DISK" >"$RECEIPT_DIR/disk-identity.txt"
  if command -v smartctl >/dev/null 2>&1; then smartctl -H -i "$EXPECTED_DISK" >"$RECEIPT_DIR/smart-summary.txt" 2>&1 || true; fi
  sha256sum "$TABLE_BACKUP" "$RECEIPT_DIR/lsblk.json" "$RECEIPT_DIR/findmnt.json" "$RECEIPT_DIR/blkid.txt" >"$RECEIPT_DIR/preflight.sha256"
}

cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "$ROOT_MOUNTED_BY_US" == 1 ]]; then umount "$MOUNT_DIR" || true; fi
  if ((rc != 0)); then
    if [[ "$GROW_STARTED" == 0 && "$STATE" == table_changed && -n "$TABLE_BACKUP" ]]; then
      log "Failure before XFS growth: attempting exact partition-table rollback from $TABLE_BACKUP"
      sfdisk "$TARGET_BY_ID" <"$TABLE_BACKUP" || log "ROLLBACK FAILED: preserve receipts and stop"
      partprobe "$TARGET_BY_ID" || true; udevadm settle || true
    elif [[ "$GROW_STARTED" == 1 ]]; then
      log "FAILURE AFTER XFS GROW STARTED: XFS cannot shrink. Do not restore the old table; restore/reimage from backup."
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT

prepare_receipts
json=$(collect_json)
geometry_state=$(validate_geometry "$json") || exit $?

if [[ "$geometry_state" == already-grown ]]; then
  [[ "$MODE" != apply ]] || die "root is already grown; refusing non-idempotent apply"
  log "Verified: root is already expanded and p3 starts at sector $P3_START."
  exit 0
fi

if [[ "$TEST_MODE" == 1 ]]; then
  log "Fixture verified: exact original geometry; no device commands executed."
  exit 0
fi

# Cross-check the partition-table parser, not just lsblk's view.
sfdisk --json "$TARGET_BY_ID" >"$RECEIPT_DIR/sfdisk.json"
python3 - "$RECEIPT_DIR/sfdisk.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))['partitiontable']
if p.get('sectorsize') != 512: raise SystemExit('REFUSED: sfdisk sector size drift')
q=p.get('partitions',[])
if len(q)!=4: raise SystemExit('REFUSED: sfdisk partition count drift')
by={int(x['node'].rsplit('p',1)[1]):x for x in q}
for n,start,size in [(1,4196352,209715200),(2,213911552,67108864),(3,281020416,695752719)]:
    x=by.get(n,{})
    if x.get('start')!=start or x.get('size')!=size: raise SystemExit(f'REFUSED: sfdisk p{n} drift')
PY

# Capture and validate installed fstab read-only in every real mode. This is a
# read-only mount with log replay disabled; apply later proves the hash unchanged.
for cmd in mount umount findmnt; do need "$cmd"; done
mkdir -m 700 "$MOUNT_DIR"
mount -t xfs -o ro,norecovery "$EXPECTED_DISK"p1 "$MOUNT_DIR"
ROOT_MOUNTED_BY_US=1
[[ -f "$MOUNT_DIR/etc/fstab" && -f "$MOUNT_DIR/etc/machine-id" && -d "$MOUNT_DIR/usr" ]] || die "installed-root identity markers missing"
[[ "$(findmnt -rn -o UUID --target "$MOUNT_DIR")" == "$ROOT_UUID" ]] || die "mounted root UUID mismatch"
FSTAB_BACKUP="$RECEIPT_DIR/fstab.before"
cp --preserve=mode,timestamps "$MOUNT_DIR/etc/fstab" "$FSTAB_BACKUP"
[[ $(grep -Ec "^[[:space:]]*UUID=$SWAP_UUID[[:space:]]" "$MOUNT_DIR/etc/fstab") -eq 1 ]] || die "fstab must contain exactly one active target swap UUID line"
FSTAB_SHA=$(sha256sum "$FSTAB_BACKUP" | cut -d' ' -f1)
umount "$MOUNT_DIR"; ROOT_MOUNTED_BY_US=0

if [[ "$MODE" == plan ]]; then
  log "PLAN ONLY — zero disk writes performed."
  log "Validated $TARGET_BY_ID serial suffix $SERIAL_SUFFIX, 512-byte sectors."
  log "Delete only p2 [$P2_START..$((P2_START+P2_SIZE-1))], then grow only p1 to [$P1_START..$((P3_START-1))]."
  log "p3 remains byte-for-byte positioned at start $P3_START; XFS growth follows table verification."
  log "Receipts: $RECEIPT_DIR"
  exit 0
fi

if [[ "$MODE" == verify ]]; then
  log "VERIFY ONLY — exact original pre-expansion geometry is valid; zero disk writes performed."
  log "Receipts: $RECEIPT_DIR"
  exit 0
fi

for cmd in sfdisk partprobe udevadm mount umount xfs_repair xfs_growfs findmnt blkid swapon swapoff; do need "$cmd"; done

# Recheck every target partition is unmounted. Only the exact obsolete swap may be active.
for p in 1 2 3; do
  [[ -z "$(findmnt -rn -S "$EXPECTED_DISK"p$p)" ]] || die "p$p is mounted"
done
while read -r swapdev; do
  [[ -z "$swapdev" || "$swapdev" == "$EXPECTED_DISK"p2 ]] || true # zram/swapfiles are preserved
 done < <(swapon --show=NAME --noheadings)

# Verify XFS while unmounted. -n is non-modifying.
xfs_repair -n "$EXPECTED_DISK"p1 >"$RECEIPT_DIR/xfs-repair-n.txt" 2>&1 || die "xfs_repair -n did not pass"
swapoff "$EXPECTED_DISK"p2
STATE=table_changed; printf '%s\n' "$STATE" >"$RECEIPT_DIR/checkpoint"
sfdisk --delete "$TARGET_BY_ID" 2
printf 'start=%s, size=%s, type=linux, uuid=%s\n' \
  "$P1_START" "$P1_NEW_SIZE" "5fed8d1d-f6a6-44d3-9608-0408425a9383" | \
  sfdisk --no-reread --force -N 1 "$TARGET_BY_ID"
partprobe "$TARGET_BY_ID"; udevadm settle

# Hard gate after mutation and before irreversible filesystem growth.
lsblk --json -b -o NAME,PATH,TYPE,SIZE,START,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,MODEL,SERIAL,LOG-SEC,PHY-SEC "$TARGET_BY_ID" >"$RECEIPT_DIR/lsblk-after-table.json"
python3 - "$RECEIPT_DIR/lsblk-after-table.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))['blockdevices'][0]
p={i['name'].split('p')[-1]:i for i in x['children']}
if set(p)!={'1','3','4'}: raise SystemExit('post-table partition set is not p1,p3,p4')
if p['1']['start']!=4196352 or p['1']['size']!=276824064*512: raise SystemExit('post-table p1 mismatch')
if (p['3']['start']!=281020416 or p['3']['size']!=695752719*512 or
    p['3']['uuid']!='f70404dd-c13b-4070-8d7c-d6d5e91db153' or
    p['3']['partuuid']!='ffbd4444-5995-4ed1-abd1-c0ac108848ef'):
    raise SystemExit('post-table p3 changed')
PY

mount -t xfs -o rw,noatime "$EXPECTED_DISK"p1 "$MOUNT_DIR"
ROOT_MOUNTED_BY_US=1
[[ -f "$MOUNT_DIR/etc/fstab" && -f "$MOUNT_DIR/etc/machine-id" && -d "$MOUNT_DIR/usr" ]] || die "installed-root identity markers missing"
[[ "$(findmnt -rn -o UUID --target "$MOUNT_DIR")" == "$ROOT_UUID" ]] || die "mounted root UUID mismatch"
[[ "$(sha256sum "$MOUNT_DIR/etc/fstab" | cut -d' ' -f1)" == "$FSTAB_SHA" ]] || die "fstab changed after preflight"
[[ $(grep -Ec "^[[:space:]]*UUID=$SWAP_UUID[[:space:]]" "$MOUNT_DIR/etc/fstab") -eq 1 ]] || die "fstab must contain exactly one active target swap UUID line"

GROW_STARTED=1
xfs_growfs "$MOUNT_DIR" >"$RECEIPT_DIR/xfs-growfs.txt" 2>&1
STATE=grown; printf '%s\n' "$STATE" >"$RECEIPT_DIR/checkpoint"

# Remove only the exact disk-swap line; zram and emergency swapfile entries survive.
python3 - "$MOUNT_DIR/etc/fstab" "$SWAP_UUID" <<'PY'
import os,sys,tempfile
p,u=sys.argv[1:]; lines=open(p,encoding='utf-8').readlines()
hits=[i for i,s in enumerate(lines) if s.lstrip().startswith('UUID='+u) and not s.lstrip().startswith('#')]
if len(hits)!=1: raise SystemExit('fstab target count changed')
out=[s for i,s in enumerate(lines) if i!=hits[0]]
st=os.stat(p); fd,tmp=tempfile.mkstemp(prefix='.fstab.expand.',dir=os.path.dirname(p),text=True)
try:
 os.fchmod(fd,st.st_mode & 0o7777)
 with os.fdopen(fd,'w',encoding='utf-8') as f: f.writelines(out); f.flush(); os.fsync(f.fileno())
 os.replace(tmp,p)
 d=os.open(os.path.dirname(p),os.O_DIRECTORY); os.fsync(d); os.close(d)
finally:
 if os.path.exists(tmp): os.unlink(tmp)
PY
STATE=fstab_updated; printf '%s\n' "$STATE" >"$RECEIPT_DIR/checkpoint"

xfs_info "$MOUNT_DIR" >"$RECEIPT_DIR/xfs-info.txt"
df -PTh "$MOUNT_DIR" >"$RECEIPT_DIR/df.txt"
df -PTi "$MOUNT_DIR" >"$RECEIPT_DIR/df-inodes.txt"
avail_pct=$(df -P --output=pcent "$MOUNT_DIR" | tail -n1 | tr -cd '0-9')
((100-avail_pct >= 15)) || die "grown root has less than 15% free"
grep -q "$SWAP_UUID" "$MOUNT_DIR/etc/fstab" && die "obsolete swap UUID remains in fstab"
grep -q '/mnt/zer0models/.swap/emergency.swap' "$MOUNT_DIR/etc/fstab" || die "emergency swapfile entry was not preserved"
sha256sum "$FSTAB_BACKUP" "$MOUNT_DIR/etc/fstab" "$RECEIPT_DIR"/*.json >"$RECEIPT_DIR/postflight.sha256"
STATE=verified; printf '%s\n' "$STATE" >"$RECEIPT_DIR/checkpoint"

log "VERIFIED. Receipts: $RECEIPT_DIR"
log "Remove the rescue USB, then reboot manually. After boot verify: lsblk; findmnt / /workspace; swapon --show."
log "Expected: no disk p2 swap; zram and emergency swapfile remain. The script never reboots."
