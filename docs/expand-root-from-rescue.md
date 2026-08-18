# Expand the installed XFS root from a CachyOS rescue USB

Status: destructive procedure prepared, not executed. Independent safety review is required before use.

## Geometry lock

```text
Samsung SSD 960 EVO 500GB / serial …23446Z / 512-byte sectors
stable path: /dev/disk/by-id/nvme-Samsung_SSD_960_EVO_500GB_S3EUNB0J523446Z

before
p1 root XFS  [  4,196,352 .. 213,911,551]  100 GiB
p2 swap      [213,911,552 .. 281,020,415]   32 GiB  DELETE
p3 workspace [281,020,416 .. 976,773,134]  ~332 GiB  IMMUTABLE

intended after
p1 root XFS  [  4,196,352 .. 281,020,415]  132 GiB
p3 workspace [281,020,416 .. 976,773,134]  unchanged
```

The script is host-specific and fail-closed. It validates model, full serial, by-id resolution, disk bytes, logical/physical sector size, all four partitions, starts/sizes, root/swap/workspace filesystem UUIDs, adjacency, mount state, and absence of LUKS/LVM/RAID ambiguity. It never formats, writes p3, reboots, or writes a USB.

Live read-only evidence on 2026-08-18 confirmed the geometry above with `lsblk --json -b`. Installed `/etc/fstab` contains one disk-swap UUID `316f4699-5371-4798-9873-68f2b6194cb4`, plus an independent emergency swapfile. The running installed system was deliberately not used to run the script. Unprivileged `sfdisk --json` and `blkid` were permission-limited, so the script requires fresh root-level rescue verification and records both views before offering apply.

## Prerequisites

1. Have a current, independently verified backup or reimage path for irreplaceable root data. A partition-table dump is not a file backup.
2. Plug in a second persistent drive for receipts. It must not be p1, p2, or p3 of the target NVMe and needs at least 1 MiB free. Do not use `/tmp`, `/run`, the live overlay, or RAM.
3. Put a reviewed copy of `scripts/expand-root-from-rescue.sh` on persistent media. Copying it to USB is intentionally outside this task.
4. Obtain independent destructive-safety approval for the exact script SHA-256 printed below/on the reviewed commit.

## Boot and inspect

1. Boot the CachyOS USB using the firmware one-time boot menu and choose the live/rescue environment. Network is unnecessary.
2. Secure Boot may need to be disabled temporarily if the live image is not accepted. Restore the prior firmware setting after recovery.
3. Do not mount the installed root or workspace in the file manager. If automounted, unmount it before continuing.
4. Mount only the separate receipt medium, for example at `/mnt/receipts`, and locate the reviewed script copy.
5. Become root in the live terminal (`sudo -i`). The script refuses the normal installed system and unrecognized live environments.

## Gates and commands

First create a receipt directory on the external medium, then run plan:

```bash
mkdir -p /mnt/receipts/root-expand
sudo ./expand-root-from-rescue.sh --plan --output-dir /mnt/receipts/root-expand
```

Read the new timestamped receipt directory. Compare `partition-table.sfdisk`, `lsblk.json`, `sfdisk.json`, `blkid.txt`, disk identity, SMART summary, and SHA-256 receipt with this runbook. Any drift is a stop, not an invitation to edit constants live.

Read-only verification uses the same gates:

```bash
sudo ./expand-root-from-rescue.sh --verify-only --output-dir /mnt/receipts/root-expand
```

Apply is intentionally awkward. Type the complete confirmation exactly; do not paste it until the receipt pack and backup have been checked:

```bash
sudo ./expand-root-from-rescue.sh --apply \
  --output-dir /mnt/receipts/root-expand \
  --confirm 'EXPAND 23446Z P1 4196352-281020415 DELETE P2 KEEP P3 281020416'
```

Apply checkpoints are `preflight → table_changed → grown → fstab_updated → verified`. Before the XFS grow starts, the failure trap may restore the exact saved partition table. Once `xfs_growfs` starts, XFS cannot shrink: the trap will not blindly restore the old table. A post-grow failure requires diagnosis and potentially restore/reimage from the real backup.

## What apply does

1. Revalidates two independent partition views and persistent receipts.
2. Mounts p1 read-only with `norecovery`, verifies root UUID/machine markers/fstab, copies fstab, then unmounts it.
3. Runs non-modifying `xfs_repair -n` while p1 is unmounted.
4. Turns off only p2 swap, deletes only p2, and changes only p1's size to end at sector `281020415`.
5. Rereads the table, settles udev, and proves p3 start/size/UUID unchanged before filesystem growth.
6. Mounts p1 read-write, verifies fstab has not changed since preflight, grows XFS, then atomically removes exactly one obsolete disk-swap line. Zram is runtime-managed; the emergency swapfile fstab line is required to survive.
7. Records XFS geometry, free bytes/inodes, final hashes, and requires at least 15% root free.

## Postflight and reboot

The script does not reboot. Preserve the receipt directory, unmount the receipt drive, shut down or reboot manually, and remove the rescue USB. After the installed system starts:

```bash
lsblk -b -o NAME,START,SIZE,FSTYPE,UUID,MOUNTPOINTS /dev/nvme0n1
findmnt / /workspace
xfs_info /
df -hT / /workspace
df -i / /workspace
swapon --show
```

Expected: p1 is 132 GiB and mounted at `/`; p2 is absent; p3 still begins at sector `281020416` and mounts at `/workspace`; zram and `/mnt/zer0models/.swap/emergency.swap` remain available; obsolete UUID `316f4699-5371-4798-9873-68f2b6194cb4` is absent from fstab/swapon; root has at least 15% free.

Do not recreate or format p2. Do not attempt to shrink XFS. Keep the immutable receipt pack with the backup evidence.
