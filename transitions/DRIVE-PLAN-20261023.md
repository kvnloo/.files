# Drive organisation and tiering plan — 2026-10-23

Status: research and decision document only. Do not execute this document as a migration script. Leave this file untracked. No storage configuration, partitions, mounts, services, or data changed during this investigation.

## 1. Recommendation and the important correction

**Use option B now: retain XFS on NVMe and Btrfs on the 4 TB capacity drive. Apply explicit placement rules and controlled moves.** Do not partition the capacity drive or add a cache layer now.

Kevin's desired end state remains valid: one data filesystem with automatic NVMe foreground writes, background storage, and read promotion. Option A, bcachefs, directly provides that mechanism. Option B does **not** provide transparent extent-level tiering. It is the recommended current operating state, not a claim that the original goal is complete.

The evidence does not justify making all development and container state depend on bcachefs today. Package support exists, but exact-kernel operation, application compatibility, recovery, and independent backup remain unproved. Keep option A available through the explicit decision gates in section 8. If Kevin chooses it, use the complete evacuation-and-restore route in section 9 rather than the old same-disk seed scheme.

**The 4 TB drive is not an HDD.** Live `lsblk` identifies `/dev/sdb` as `WDC WDS400T2B0A-00SM50`. Western Digital identifies WDS400T2B0A as a WD Blue SATA SSD.[W1] The actual HDD is the separate 3 TB Toshiba `/dev/sdc`. Thus, the existing performance comparison is NVMe versus SATA SSD, not NVMe versus rotating disk. This materially reduces the likely benefit of another cache layer. Adding the Toshiba as a background member would be a different design, with less backup capacity and a slower authoritative tier.

Keep `/` and `/boot` outside any initial data-pool migration. “Everything” must receive an explicit scope decision. Combining application data is different from converting the operating-system root or absorbing Windows disks.

## 2. Current evidence and capacity

These are live, read-only observations from this investigation. Device names describe the current session only. Future destructive work must use verified serial numbers and `/dev/disk/by-id` identities.

| Current device | Physical medium | Current use | Capacity and available space |
|---|---|---|---|
| `nvme0n1`, Samsung 960 EVO 500 GB | NVMe SSD | Root, workspace, boot | 500,107,862,016 physical bytes |
| `nvme0n1p1` | NVMe partition | XFS `/` | 132 GiB partition, about 26.8 GiB available, 80% used |
| `nvme0n1p3` | NVMe partition | XFS `/workspace`, supplied inventory reports `reflink=1` | 331.8 GiB partition, about 49.8 GiB available, 85% used |
| `nvme0n1p4` | NVMe partition | FAT32 `/boot` | 2 GiB |
| `sdb`, WD Blue 4 TB | SATA SSD | `sdb2`: Btrfs `/mnt/zer0models` | 3,999,657,885,696 filesystem bytes, about 732.4 GiB available, 81% used |
| `sdb2[/containerd]` | Same SATA SSD and filesystem | Mounted at `/var/lib/containerd` | Not another independent copy or another capacity pool |
| `sda`, Samsung 850 EVO 500 GB | SATA SSD | Two NTFS partitions, currently unmounted | Roughly 500 GB combined, contents and free space unknown |
| `sdc`, Toshiba HDWD130 3 TB | HDD | Large NTFS `sdc3`, small boot/recovery partitions, currently unmounted | Large NTFS partition is 2,999,934,327,296 bytes, or 2.728 TiB. Free space unknown |

The capacity mount currently uses `noatime,compress=zstd:3,ssd,discard=async,space_cache=v2`. `findmnt` resolves `/var/lib/containerd` to `/dev/sdb2[/containerd]`.

`btrfs filesystem usage -b` reports approximately 3.173 TB used, data `single`, and metadata `DUP`. `DUP` stores metadata copies on the **same** device. It is not device redundancy. The command could not read detailed per-device chunk information without root. No scrub or SMART health claim follows from this metadata query.

Live `df -B1` observations:

- Capacity filesystem used: **3,173,577,895,936 bytes**, about 3.174 TB or 2.886 TiB.
- Workspace used: **302,620,180,480 bytes**, about 0.303 TB or 0.275 TiB.
- Combined data-filesystem usage: **3,476,198,076,416 bytes**, about 3.476 TB or 3.162 TiB.
- Root adds approximately 112.9 GB. Including it raises the observed usage sum to approximately **3.589 TB**.

These are filesystem accounting figures, not an exact backup size. Btrfs metadata, compression, snapshots, shared extents, sparse files, and reflinks affect restored space. A normal file copy can expand shared or compressed data. Do not size the backup or destination solely from `df`.

## 3. Reconstructed plan lineage

### 3.1 Original Ubuntu-to-CachyOS research and conflicting old layouts

The archive removed by `.files` commit `4b2cb42` remains readable with `git show 4b2cb42^:<path>`. It contains multiple proposals, not one consistent final layout.[H1]

- `old-docs/improved-prompt.md` asked for a shared development workspace and performance under many concurrent agents. It started from Ubuntu/ZFS problems.
- `research/filesystem-comparison.md`, dated 2025-11-25, selected XFS and rejected bcachefs at that time. Its numerical performance promises are not measurements of this machine. Do not reuse its claims that a filesystem change guarantees no freezes or a particular speed increase.
- `old-scripts/3-partition-disk.sh` proposed NVMe EFI + two 80 GB OS roots + 32 GB swap + a cache partition. It proposed two 200 GB home partitions and an XFS workspace on the 4 TB SATA SSD.
- The later archived `MIGRATION-PLAN.md` instead proposed CachyOS root and workspace on NVMe, with Ubuntu on the 4 TB SATA SSD retained as a fallback. It later contemplated reclaiming SATA for home storage.

Those layouts predate the live installation. They are **not** instructions for today's partition numbers. The old partition script wipes selected disks and includes unsafe journal/barrier settings. Do not run it or revive its tuning recommendations.

### 3.2 August 24: the actual automatic-tiering proposal

Hermes `chiefstaff_archive`, session `20260824_000407_adedc0`, message **22535**, dated 2026-08-24, describes the requested staged migration. Message **22518** contains the preceding layout and risk discussion.[H2]

The proposed final members were:

- Existing NVMe workspace partition, roughly 332 GiB: `foreground_target` and `promote_target`.
- Existing 4 TB SATA SSD: `background_target`.
- Root and boot remained outside the unified data pool.

At the time, the discussion reported roughly 944 GB on SATA and 331 GB in workspace. Those historical units were approximate. Enough capacity appeared available for this sequence:

1. Check Btrfs and make an independent backup.
2. Shrink Btrfs and its partition to roughly 1.4–1.6 TiB.
3. Create an approximately 2 TiB bcachefs seed in the released tail.
4. Copy both source trees into the seed. Stop agents and databases for final synchronisation and verification.
5. Reclaim the old Btrfs partition and add it to bcachefs.
6. Either leave two SATA partitions as members or evacuate the seed and consolidate them.
7. Evacuate and recreate the NVMe workspace partition as the fast member.
8. Restore stable logical paths and mount relationships.

The discussion distinguished ordinary write-back members from a `durability=0` NVMe cache. It required backup, health checks, rescue media, exact-kernel rehearsal, workload tests, and human approval.

**Why that seed scheme no longer fits:** today's combined usage is roughly 3.476 TB, while only 0.786 TB is available inside Btrfs. There is no room for a complete second copy in a tail partition. Btrfs internal unallocated space is also not unpartitioned disk space. Shrinking now cannot recreate the old 2 TiB seed opportunity without first evacuating substantial data.

Two partitions on one physical SATA drive would never be two independent replicas. A bcachefs partition on SATA alone would not be NVMe tiering. The old planner's phrase “is cache” is imprecise: alone it is simply another filesystem.

### 3.3 August 25: a read-only blocker report, not a completed migration

`/mnt/zer0models/ops/bcachefs-tier-plan.json`, generated 2026-08-25, explicitly says `mutates_disks=false`. It records no bcachefs CLI/module, XFS constraints, existing Btrfs data, and the need for independent backup.[H3]

It recommends a disposable mount/fsck/reboot rehearsal and either a second NVMe or evacuation of `/workspace`. It forbids formatting or shrinking from the planner. Its old claim that XFS cannot convert in place is too broad for current bcachefs tooling. XFS cannot shrink, but bcachefs has a separate gated migration mechanism. See section 4.3.

### 3.4 September: controlled placement and organisation work

Hermes `chiefstaff`, session `20260919_120228_b9b756`, message **214398**, dated 2026-09-19, reconstructed these tools:[H4]

- `zer0_storage_tier.py`: rsync copy, checksum comparison, rename, symlink, and transition ledger.
- `zer0_storage_autotier.py`: reserve checks and restricted bulk-directory candidates.
- Whole-project and containerd migration tools were also reported in that history. Their current implementations were not examined here.

The first two Python tools still exist under `/workspace/zer0/portfolios/chief-of-staff/scripts/`. Current source does not justify treating them as a fully safe general service mover:

- The tier mover checks process references before copying, not throughout the entire cutover.
- Its copy uses `-aHAX --numeric-ids`, without explicit sparse-file preservation.
- It removes the renamed source immediately after symlink verification.
- Its ledger path is inside the logical company tree.
- The current autotier source also contains deletion/pruning behavior. It is not merely a copy-only mover.

Therefore, reuse its existing copy/verify/ledger pattern, but do not invoke it unchanged for databases, shared environments, sparse trees, or the whole pool. A future implementation must close these specific gaps before unattended use.

The September 22 organisation request was explicitly **read-only**. It required the logical company namespace `/workspace/zer0`, protected active paths, and prohibited mounting NTFS disks. Its report records `/workspace/zer0` pointing to `/mnt/zer0models/workspace/zer0`, separate task/worktree pools, model stores, archives, home offloads, and runtime state.[H5] These are historical classifications, not fresh size measurements.

### 3.5 Current transition stub and why work stalled

`/workspace/.files/transitions/workspace-xfs-bcachefs.toml` remains **disabled**. It records minimum tools `1.39.6` and these gates:

- Stable device identity.
- Source unmounted and offline environment.
- Verified P0 backup.
- Verified alternate-superblock mount and content comparison.
- Verified filesystem semantics.
- Explicit human commit.

It forbids partition changes, `migrate-superblock`, and fstab changes during normal IaC apply. `transitions/README.md` confirms that destructive transitions require a separate boundary.[H6]

The evidence supports several reasons for the stall, not one failed conversion:

1. Bcachefs tools/module were absent. They are still absent today.
2. There is no demonstrated completed backup/recovery/canary acceptance packet.
3. Existing XFS and live Btrfs data require gated work, not an automatic format operation.
4. The organisation request authorised inventory, not data movement.
5. The full-history audit documents repeated pressure relief rather than complete prevention. Early guards were disabled or watched only workspace.[H7]
6. Capacity growth invalidated the original same-disk migration arithmetic.

No recovered evidence proves that a bcachefs production migration completed and then failed. Archive removal is not proof of such a migration either.

## 4. Bcachefs feasibility on today's CachyOS

### 4.1 Packages exist, but nothing is installed or proven here

Upstream says bcachefs stopped shipping in mainline starting with **Linux 6.18**. It now ships through DKMS and states support for Linux 6.16 and later.[W2]

Local `pacman -Si` metadata and the CachyOS package dashboard agree:[W3]

| Component | Evidence today |
|---|---|
| CachyOS v3 `bcachefs-dkms` | `3:1.39.7-1.1`, built October 4, 2026 |
| CachyOS v3 `bcachefs-tools` | `3:1.39.7-1.1` |
| Arch `extra` variants | `3:1.39.7-1` |
| Installed kernel | `linux-cachyos 7.2.9-1` |
| Installed matching headers | `linux-cachyos-headers 7.2.9-1` |
| Installed DKMS | `3.4.3-1` |
| Installed bcachefs packages | Neither package installed |
| Module lookup | `modinfo bcachefs` returns “Module bcachefs not found” |

`pacman -Si` reads local repository metadata. No package database refresh or install occurred. The matching public dashboard is an independent availability check. Upstream's generic “install bcachefs-tools” wording does not replace Arch's split-package reality: an execution plan must include the DKMS package explicitly.

**Conclusion:** a supported packaging route exists. Successful compilation/loading on this exact kernel is **not established**. Neither availability nor a minimum version proves kernel compatibility, correct boot ordering, or recovery readiness.

A September 18 CachyOS report describes DKMS build failure on `7.2.6-1-cachyos` and recovery through an LTS kernel.[W4] This is one relevant incident, not proof that `7.2.9` fails. It shows why each intended kernel needs a real build, load, reboot, and rescue gate before production use.

### 4.2 Maturity and the 4 TB service workload

The upstream FAQ calls bcachefs stable for production.[W5] That is an upstream position, not an independent guarantee for this host. The current release changelog documents substantive repair, accounting, device-transition, and full-filesystem fixes.[W6]

For example, 1.39.7 corrects insufficient-replica accounting, hangs with a member offline or read-only, device-state checks, and deleted container-layer subvolumes during fsck. Its FUSE mode is described as a recovery option, not a performance-equivalent kernel replacement.

A roughly 4 TB filesystem is not inherently beyond the design's intended scale. The important local risks are one-copy durability, small fast-tier capacity, concurrent services, near-full conditions, and rolling-kernel integration. There is no measured evidence here that replacing Btrfs improves this host's actual latency or reliability.

For k3s/containerd specifically:

- Keep image content, writable snapshots, container runtime metadata, k3s datastore, and persistent volumes distinct in the inventory.
- An image cache can be recreated only when its exact images remain available. Locally built or unavailable images need export and verification.
- Existing `/var/lib/containerd` is already on the SATA Btrfs filesystem. Do not count it twice in capacity or backups.
- Several containerd processes are running. Their exact root/config/snapshotter relationships were not resolved in this investigation.
- There was an old bcachefs OverlayFS whiteout issue. The issue is closed and reports a fix.[W7] It is not evidence that all current overlay use is unsupported.
- Equally, a closed issue is not proof that the installed runtime's snapshotter, whiteouts, xattrs, inode behavior, and crash recovery work on the proposed pool.
- Migration must retain the current snapshotter unless a separate, tested conversion is approved. A Btrfs-native snapshotter cannot simply consume a file copy on a different filesystem.

Do not move containerd to bcachefs until the exact deployed k3s/containerd versions pass the canary. Do not silently substitute a slow VFS snapshotter to claim compatibility.

### 4.3 In-place migration is a separate, high-risk option

Current upstream exposes `bcachefs migrate` and `migrate-superblock`.[W5][W8] The current source describes a reservation file that protects blocks shared during conversion. Removing it after formatting can corrupt both views. The changelog also records migration reservation/free-space fixes.[W6]

Therefore:

- “XFS cannot shrink” remains correct.
- “No XFS-to-bcachefs migration mechanism exists” is not correct.
- This does **not** establish safe conversion of the current compressed Btrfs tree, its snapshots, shared extents, and container state.
- An alternate-superblock mount is not an independent backup. The two views can depend on the same physical blocks.
- `migrate-superblock` is an explicit destructive commit boundary, not a routine IaC action.

The disabled transition preserves this alternative. The recommended plan does not rely on it. Use evacuation and restore if option A is approved. Do not bypass backup because a conversion appears to need less spare space.

## 5. What automatic tiering would buy

Bcachefs operates on observed I/O and configured targets. It does not know which repository, model, or dataset is strategically important. Promotion is reactive. The first cold read still comes from the background device.[W9]

| Workload | Useful placement | Expected tiering benefit and limitation |
|---|---|---|
| Active agent repos, worktrees, `node_modules`, compilers | NVMe when capacity permits | Repeated small-file access benefits from NVMe. Direct XFS placement avoids warming and cache eviction. A foreground target does not pin a project forever. |
| Hermes/agent SQLite, WAL, locks, runtime metadata | NVMe, with application-consistent backup | Low latency matters. Do not treat live database files as a cold move candidate. Filesystem checksums do not replace database recovery tests. |
| Model weights and HF model blobs | SATA SSD as canonical source, selected active models on NVMe | Repeated loads can benefit. Once weights reside in GPU/RAM, storage tiering does not accelerate token generation. One-pass loads can pollute a small cache. |
| HF caches and shared package/model objects | One canonical store per cache system | Preserve HF blob/snapshot links and hardlink relationships. Do not create duplicate stores merely to change mount locations. Use tool-supported cache paths. |
| Datasets and training caches | Cold source on SATA, active shards/scratch on NVMe | Random revisits benefit more than one-pass streams. Sustained writes eventually run at background-tier speed. |
| k3s image blobs | SATA SSD initially | Cold image pulls/unpacks and repeated reads may benefit, but writable layers and runtime state need stronger compatibility gates. |
| Blender and ComfyUI | Active project caches, selected checkpoints, simulation scratch on NVMe | Large inactive assets and completed renders belong on SATA. GPU compute and already-resident models do not become faster from storage tiering. |
| Archives, completed outputs, reproducible old environments | Capacity tier | Little reason to consume NVMe cache indefinitely. Environment deduplication is a separate semantic and ownership task. |

These are **[INFERENCE] workload expectations**, not benchmark results. No fio, scrub, checksum sweep, container smoke, or migration test ran here.

With roughly 332 GiB available as a whole fast partition, the active working set may exceed the cache. It currently already contains roughly 282 GiB. Bcachefs targets are best-effort. When a target fills, allocation can fall back elsewhere.[W9] Do not promise that all foreground I/O always stays at NVMe speed.

If the background tier were the actual Toshiba HDD, random-read acceleration would be more compelling. However, it cannot hold today's approximately 3.476 TB data set by itself. Using it for the pool also removes a potential independent backup target.

## 6. Comparison of the four options

| Option | Meets transparent tiering goal? | Main benefit | Data risk and migration | Downtime | Reversibility |
|---|---|---|---|---|---|
| **A. Bcachefs NVMe + capacity device** | Yes, via foreground/background/promote targets | Unified free space, checksums, CoW, native placement and read cache | Highest present change risk. Requires independent backup, canary, evacuation, and exact-kernel recovery proof. Ordinary write-back can leave unique data on either member. | Whole-service cutover plus restore and recovery allowance. Prefer an offline maintenance window for reclaiming existing partitions. | Before formatting, retain old sources. After formatting, return to XFS/Btrfs requires recreation and restore. Removing a healthy member is not filesystem-format rollback. |
| **B. XFS NVMe + existing Btrfs capacity** | No. Placement is explicit and moves whole approved units | Smallest change, no new kernel module, existing stable paths and filesystem features | Lowest transition risk. Each move still needs writer exclusion, correct copy semantics, independent backup for unique data, and rollback. | Per-project final cutover. No whole-pool outage required. | Reverse-copy a stopped unit and restore its original path. Retain source copies through acceptance. |
| **C. dm-cache/LVM cache or block bcache** | Automatic caching, not filesystem-aware placement | Keeps the upper filesystem and can accelerate hot blocks. Mainline kernel mechanisms avoid bcachefs DKMS dependency. | Not a non-destructive add-on to today's raw Btrfs partition. LVM requires an appropriate LV origin. Bcache requires backing-device metadata. Rebuild/restore is the safe default. Fast-device space must also be obtained. | Initial block-layout conversion needs evacuation or another proven migration design. Existing LVM origins can attach caches with less disruption, but that is not today's layout. | Flush dirty blocks and detach cleanly. LVM origin can remain usable after cache removal. Bcache backing layout retains its offset/metadata. Returning to a plain raw partition is another migration. |
| **D. Multiple filesystems on the capacity disk** | No | Different policies and hard capacity boundaries for different data classes | Partition resize/rebuild risk, rigid space budgets, no physical failure isolation. Full backup still needed. | Potential whole-disk maintenance window. Future boundary changes can cause more downtime. | Btrfs can shrink with adequate free space. XFS cannot shrink. Recombining normally needs evacuation and restore. |

### 6.1 A: the actual bcachefs topology and durability choices

For the existing data devices, a future schematic is:

```text
Samsung 960 EVO: existing workspace partition -> label fast.nvme
WD Blue SATA SSD: existing capacity partition -> label capacity.sata
foreground_target = fast
promote_target    = fast
background_target = capacity

OS root XFS and FAT32 boot remain separate.
```

These are design labels, not executable format commands. The background target is called `capacity`, not `hdd`, because the observed drive is an SSD.

Choose durability before estimating capacity or performance:

1. **Write-back, one durable copy:** normal durability on both members and one required data copy. Writes can complete on NVMe before background placement. Failure of either member can destroy unique data. Checksums detect errors but cannot reconstruct a missing sole copy.
2. **Disposable NVMe read/write-through cache:** NVMe `durability=0`, capacity device provides required durability. The design must also keep required metadata/journal recoverable without NVMe. Durable writes depend on the capacity device. Prove missing-cache recovery before calling the NVMe disposable.
3. **Two durable copies on these two differently sized devices:** the 356 GB fast partition cannot mirror several TB. Two-copy capacity is constrained by the small member, not half the combined 4.36 TB raw size. Buy adequate independent durable capacity if this is required.

With a disposable cache, do not count NVMe space as additional authoritative capacity. Do not use two partitions on the same drive as independent replicas. Do not enable erasure coding to avoid buying backup storage for this two-device design.

### 6.2 B: exact placement and mover policy

Preserve the current company taxonomy. `/workspace/zer0` remains the logical namespace. Do not create competing `/workspace/products`, `/workspace/agents`, or generic new archive roots.

- Keep root, boot, active control databases, active service metadata, and latency-sensitive builds on NVMe.
- Keep bulk model stores, datasets, inactive repositories, completed artifacts, backups, and existing container image storage on the SATA SSD.
- Keep a single canonical physical store for each HF/model/cache system. Set native cache directories where available.
- Preserve existing links and bind mounts unless an individual migration explicitly changes them.
- Do not relocate Git worktrees with a plain directory move. Use Git-aware relocation/repair and check both main repository and worktree relationships.
- Do not classify a virtual environment as disposable because an import succeeds or its size is large. Owners, exact packages, native dependencies, editable paths, and reproducibility matter.
- Treat Unix sockets, locks, live databases, process CWDs, mmap users, and service roots as immovable until writers stop.

Future mover contract:

1. Inventory a named source and destination. Resolve all symlinks, mount boundaries, shared Git metadata, and owners.
2. Confirm destination headroom and an independent backup for unique data. Do not fill SATA merely to free NVMe.
3. Use initial low-priority copy, then stop all writers and repeat the final copy. Process inspection alone does not prevent a new writer.
4. Preserve numeric ownership, ACLs, xattrs, hardlinks, sparse files, and required link topology. Account separately for snapshots and reflink expansion.
5. Compare content and metadata. Run the affected application's filesystem-semantics and startup checks.
6. Rename the old source within its filesystem. Install one canonical symlink, or a bind mount where service path semantics require it.
7. Keep the old source until a named acceptance and retention boundary. Do not automatically delete it immediately after checking the symlink.
8. Record identities, paths, hashes/manifests, previous mount configuration, and reverse-copy instructions in a ledger outside the pressured filesystem.
9. Reverse the move only while writers are stopped. Reconcile writes made after cutover before restoring the old path.

Do not move a parent that already contains links into its proposed destination. Do not allow a missing capacity mount to receive data into the underlying root directory. Service and bind-mount dependencies must fail closed.

Proposed reserve policy, not deployed by this report:

- `/workspace`: warn at 80% used. At 85%, propose only allowlisted idle moves. At 90%, stop admitting avoidable new bulk work.
- After a move, target at most 75–80% usage. Keep at least 30 GiB available and a monitored inode reserve.
- `/`: retain a separate reserve policy. A workspace timer cannot protect root from `~/tmp`, package installs, or runtime growth.
- Capacity Btrfs: warn at 80%. Avoid planned growth beyond 85% without a headroom review. Monitor data and metadata allocation separately.
- The SATA pool is already approximately 81% used. Capacity expansion or measured reclamation is now a prerequisite to large additional offloads.

Subvolumes can separate snapshot/retention policy without creating hard partition boundaries. They do not automatically create independent space reservations. Codify any permanent timer, mount, or mover changes in `.files`, with explicit policy and no unreviewed deletion behavior.

### 6.3 C: block caching details

Both dm-cache and bcache can offer automatic read caching and write modes.[W10][W11] This is a legitimate alternative if a future **HDD-backed** pool needs acceleration while retaining a mature upper filesystem.

- Prefer write-through for the first canary. It keeps the backing data current, but durable write latency still includes the backing device.
- Write-back leaves dirty authoritative blocks on cache. Losing cache data or metadata before flush can corrupt the upper filesystem.
- A UPS reduces some power-loss exposure. It does not protect against SSD failure, firmware defects, or operator error.
- Cache metadata and dirty data require their own recovery plan. “The filesystem is Btrfs” does not protect against a broken lower cache layer.
- dm-cache tracks blocks, not project importance. `dm-writecache` is a different, write-only mechanism. It does not provide read promotion.[W12]
- Bcache normally bypasses large sequential streams. Do not assume a full model scan will become cached.[W11]
- Cache capacity does not enlarge authoritative storage. A 3 TB HDD plus 332 GiB cache is not a 3.476 TB durable pool.
- The fast partition problem remains: XFS cannot shrink to donate a convenient cache slice. Add another SSD or evacuate/recreate workspace.

For this machine's SATA SSD, cache complexity is not justified without measured gains. Do not layer block caching under Btrfs merely to avoid evaluating the bcachefs migration gates.

### 6.4 D: can the HDD use multiple filesystems?

**Yes.** Separate partitions or logical volumes can hold Btrfs, XFS, and NTFS on one disk. Each filesystem needs its own partition/LV and mount. This does not create multiple physical drives or remove seek contention on the actual HDD.

For the 4 TB SATA SSD, the proposed Btrfs/XFS split is also technically possible. It is not the recommended first step:

- Btrfs already supports per-file/directory compression choices. New writes inherit applicable policy. Changing policy does not rewrite existing extents.[W13]
- Large weights are not automatically incompressible. Quantisation, tensor encoding, and archive format affect savings. Measure representative files rather than classify by extension.
- Already compressed media/archives usually gain little. Btrfs heuristics already avoid much pointless compression. Selective `NOCOMPRESS` policy does not require another filesystem.
- Btrfs supports reflink sharing and external deduplication workflows. Deduplication is not automatic merely because the filesystem is Btrfs.
- XFS supports reflinks when enabled, but it does not provide transparent compression or general automatic deduplication.
- Separate filesystems prevent cross-filesystem hardlinks/reflinks and can duplicate cache blobs. Fixed partitions can strand free capacity on the wrong side.
- XFS cannot later shrink to return unused space. Btrfs shrink requires real extent relocation and headroom.
- Do not enable Btrfs NOCOW globally to imitate XFS. It changes compression and data-checksum behavior.

If Kevin needs a Windows-readable area, retaining an NTFS partition is possible. It remains unsuitable as the live Linux metadata authority for agents, databases, or containerd without explicit semantic proof. Preserve existing Windows/EFI/recovery content until ownership and deletion permission are established.

## 7. Where the data and backup would go

### 7.1 The Toshiba alone cannot hold the migration

The large NTFS partition holds at most approximately **3.000 TB before existing files and filesystem overhead**. Current data-filesystem usage sums to approximately **3.476 TB**. The nominal shortfall is already about **476 GB**. Even the current Btrfs usage alone exceeds the entire NTFS partition's nominal capacity.

The two Samsung 850 EVO NTFS partitions add approximately 500 GB in total. Combining both Windows disks gives only approximately **3.500 TB nominal**. That leaves about **24 GB** against the observed data usage sum, before existing contents, overhead, growth, compression/reflink expansion, or backup metadata. Including root exceeds both disks' combined nominal capacity.

Therefore, “use the 2.7 TB disk” is **not a sufficient backup plan**. Neither NTFS disk was mounted or altered here. Their current free space, Windows obligations, and health remain unknown.

### 7.2 Required backup shape

Preferred: obtain independent storage with at least **5 TB verified usable free space** for the data set and headroom. An 8 TB-class device or suitable NAS is a practical starting point. This is a planning allowance, not a guarantee that all logical snapshots fit.

Before committing:

1. Inventory logical and allocated bytes, snapshots, shared extents, sparse files, and data that exists only locally.
2. Classify data as irreplaceable, reproducible with exact provenance, or approved for exclusion.
3. Prove the chosen backup representation fits. A future Btrfs send stream may preserve Btrfs structure, but the eventual bcachefs restore needs a compatible restoration route.
4. Use an archive/backup repository that preserves Linux metadata if the storage destination is NTFS. Plain file copies onto NTFS are not the authoritative restoration method.
5. Preserve dirty/untracked Git data, LFS objects, local-only image layers, secrets, ACLs/xattrs, hardlinks, sparse files, and application state.
6. Back up SQLite through a consistent application method or a stopped copy. Preserve the matching WAL state where applicable.
7. Back up the actual k3s datastore and persistent volumes separately from container image caches.
8. Restore representative critical trees and databases on spare storage. Check content, permissions, application semantics, and required keys.
9. Keep backup media outside the new pool. A snapshot or second partition on the same disk is not this backup.

A smaller backup can be acceptable only after Kevin explicitly approves the exact reproducible exclusions and recovery cost. Do not assume model downloads, package caches, or private images remain obtainable.

### 7.3 Transfer time and outage planning

**[INFERENCE] planning bounds:** at an effective 100–150 MB/s, one sequential pass over 3.476 TB takes roughly 6.4–9.7 hours. At 300–450 MB/s, it takes roughly 2.1–3.2 hours. Millions of files, compression, verification, USB bridges, and competing I/O can extend this substantially.

Backup, verification, restore, and restored-content verification require multiple passes. A migration is not a short reboot operation. Schedule a full-day or longer maintenance allowance until measured rehearsal throughput narrows it. Initial live copies reduce final deltas but do not eliminate writer downtime or the time needed to recreate the only source disk.

All large copy, hashing, and later scrub work must use idle I/O priority, bounded concurrency, and an agreed maintenance window. None ran for this report.

## 8. Phased recommended operating plan

### Phase 0 — decide scope and protect capacity

1. Accept or reject option B as the current operating state.
2. Confirm that any first bcachefs scope is **data only**, not root/boot or Windows disks.
3. Preserve canonical paths and protected running workloads. Do not mount or repurpose NTFS without explicit approval.
4. Stop new uncontrolled duplicate model/cache stores and unbounded environment creation through policy, not automatic deletion.
5. Review the existing mover/timer implementation before enabling or extending it. Current source includes pruning and immediate source removal.

Exit gate: one approved physical/logical path map, clear owners, and a capacity reserve policy for root, workspace, and SATA.

### Phase 1 — make option B maintainable

1. Classify named hot, warm, cold, and protected trees using existing inventories plus a bounded update.
2. Move only individually approved inactive units with the mover contract in section 6.2.
3. Keep current containerd mounts and snapshotter unchanged.
4. Apply per-directory compression/retention policy only where justified. Do not run a global deduplication, balance, or recompression operation.
5. Codify persistent policy in `.files`. Keep backups and receipts off the pressured source filesystem.

Exit gate: stable paths, application checks, retained rollback copies, and demonstrated reserves. This phase improves organisation without claiming automatic tiering.

### Phase 2 — obtain independent backup and a spare canary environment

1. Select backup destination, usable capacity, retention, encryption, and restore keys.
2. Obtain approval for the maintenance and backup reads. Check physical-device health and complete integrity checks in that window.
3. Build the full application-consistent backup and perform restore checks.
4. Select spare devices or a disposable VM for bcachefs work. Do not carve a canary from the only live capacity copy.

Exit gate: a verified independent recovery copy and an executable recovery procedure. Backup is required before partition changes even if the next phase is optional.

### Phase 3 — evaluate the exact bcachefs target before committing

Use `bcachefs-tools` and `bcachefs-dkms` from the chosen package release with matching headers. Record the version tuple and retain known-good packages/kernel/rescue media.

Required acceptance campaign, **not executed here**:

- Exact `7.2.9-1-cachyos` module build/load, normal mount, unmount, reboot, and recovery boot.
- The next intended kernel update and a known-good fallback. Do not retain an unsafe kernel indefinitely merely to preserve compatibility.
- Foreground writes, background movement, promotion, fast-tier full fallback, and near-full pool behavior.
- Device-loss tests matching the selected durability model, including required metadata recovery without cache.
- Git status/worktree operations, package installations, sparse files, ACLs/xattrs, hardlinks, rename, inotify, mmap, and actual concurrent builds.
- SQLite WAL/fsync/locking, interrupted write recovery, and restart of real representative agent services.
- Exact containerd snapshotter, image unpack, whiteouts, container starts/restarts, persistent volumes, k3s datastore recovery, and service ordering.
- Offline check/repair and an end-to-end restore from backup.

Record p95/p99 application latency, throughput, CPU cost, background I/O, write amplification, and recovery time against the current XFS/SATA Btrfs baseline. Test real traces, not only generic fio. Predeclare acceptable regression and recovery limits with Kevin before testing.

Exit gate: either retain option B, or explicitly approve option A with backup, benefit, service compatibility, and recovery evidence. No silent escalation from a successful canary to production formatting.

## 9. Full option A route if Kevin approves the original end state

This is the complete conditional cutover path, not an instruction to start it now. It replaces the no-longer-feasible same-disk seed plan.

1. **Prepare.** Finalise the data-only map, target labels, durability/metadata policy, backup scope, and rollback deadline. Capture current UUIDs, serials, partition table, fstab, bind mounts, service dependencies, and actual containerd roots/snapshotters. Preserve all required OS boot partitions.
2. **Back up while sources remain intact.** Complete the independent copy and restoration rehearsal. Refresh it before cutover. Protect the backup from source-disk operations.
3. **Stop writers.** Stop agents, databases, k3s workloads, all relevant containerd instances, and other writers to both data filesystems. Account for bind mounts and mount namespaces. Complete the final consistent backup delta and verify it.
4. **Boot the tested recovery environment.** Unmount all source aliases and child mounts. Reconfirm serials and partition boundaries at the point of risk. Obtain explicit human approval for the exact format operations.
5. **Create the pool.** Recreate only the approved data partitions. Use the NVMe workspace partition and 4 TB SATA partition as the chosen bcachefs members. Leave root/boot and other disks untouched. Apply the rehearsed targets, durability, replicas, compression, and metadata policy.
6. **Restore once into the unified data filesystem.** Preserve original directory relationships. Plan separate data roots for former workspace and former capacity content. Avoid recursively copying an existing `/workspace/zer0` link back into itself.
7. **Recreate path contracts.** Use one backing mount and explicit bind mounts/subvolume layout as needed to expose `/workspace`, `/mnt/zer0models`, and `/var/lib/containerd`. Prevent new mounts from hiding restored content. Preserve container runtime backend semantics and the logical company namespace.
8. **Check before service release.** Compare restored manifests and metadata. Check databases, Git/worktrees, links, images, persistent volumes, and the selected durability invariants. Keep services stopped on any discrepancy.
9. **Boot and release in order.** Mount the pool before dependent paths and services. Start databases/control services, then container runtime/k3s, then workloads and agents. Confirm the backup remains separate and accessible.
10. **Retain rollback.** Keep the independent backup and known-good recovery media until the agreed retention boundary. Verify scheduled backup and recovery procedures before accepting the transition.

Do not enable the existing transition stub automatically. Its in-place alternate-superblock gates are a different mechanism. A separately approved evacuation/restore implementation needs its own correct acceptance packet.

Rollback boundaries:

- **Before formatting:** retain sources and their mount configuration. Reverse any isolated approved moves after writer exclusion.
- **After formatting but before release:** recreate XFS/Btrfs and restore the verified backup. This takes another maintenance window. There is no instant undo.
- **After release:** first preserve new writes consistently, then recreate and restore. The pre-cutover backup alone is no longer a current rollback copy.
- **Healthy cache/member removal:** requires data evacuation, clean state, sufficient remaining space, and a supported operation. It does not convert bcachefs back to XFS/Btrfs.

## 10. Decisions Kevin must make

| Decision | Recommended default | Consequence of a different choice |
|---|---|---|
| Current strategy | Option B now | Immediate option A requires all backup and canary gates first |
| Exact end-state scope | Data pool only, root/boot separate | “All Linux files including root” adds bootloader/initramfs and OS-recovery work, outside the existing data transition |
| Background device | Existing 4 TB SATA SSD | Toshiba HDD requires Windows approval, cannot alone hold today's data, and removes a backup candidate |
| New hardware | Independent backup capacity first, then a larger/additional NVMe if the hot set needs it | Reusing existing NVMe means evacuating/recreating workspace. NTFS disks cannot be assumed empty |
| Durability | No unacknowledged unique-write cache risk | Write-back is faster only by accepting unique dirty data on the fast member unless durable copies exist elsewhere |
| Backup scope | Preserve unique state and prove restore | Excluding reproducible data requires exact inventories, approved loss/re-download cost, and verified sources |
| Service outage | Explicit writer stop and maintenance window | Live-only copying cannot guarantee database/container consistency |
| Rolling-kernel operations | Prove the version tuple, retain rescue and fallback, maintain updates | Uncontrolled updates can remove module availability. Permanent update freezes create a different risk |
| Mover authority | Named allowlist, copy/verify/retain, no automatic deletion | General autonomous cleanup needs a separate retention and ownership contract |
| Criteria for option A | Measured useful benefit and acceptable recovery, not package availability alone | If the goal itself outweighs measured speed, explicitly accept the operating and recovery cost |

**Bottom line:** the original bcachefs topology is technically available through current CachyOS packages. The original same-disk migration order is no longer capacity-feasible. Retain the existing filesystems now, secure independent backup, and require an exact-kernel/service canary before choosing the destructive unified-pool cutover.

## Evidence and references

### Local and historical evidence

- **[H1]** `.files` commit `4b2cb42` and its parent. Read-only `git show` of `transitions/legacy/cachyos-migration/{MIGRATION-PLAN.md,research/filesystem-comparison.md,old-docs/improved-prompt.md,old-scripts/3-partition-disk.sh}`. These are superseded proposals.
- **[H2]** Hermes **chiefstaff_archive**, 2026-08-24, session `20260824_000407_adedc0`, messages `22518` and `22535`. Original device-target and seed-migration discussion. Historical assertions are not current acceptance evidence.
- **[H3]** `/mnt/zer0models/ops/bcachefs-tier-plan.json`, generated 2026-08-25.
- **[H4]** Hermes **chiefstaff**, 2026-09-19, session `20260919_120228_b9b756`, message `214398`. Current mover source inspected at `/workspace/zer0/portfolios/chief-of-staff/scripts/{zer0_storage_tier,zer0_storage_autotier}.py`.
- **[H5]** `/mnt/zer0models/workspace/zer0/data/operations/storage-maintenance/runs/20261008_221218_fc8978/history/pc-reorg-original-request-20260922.txt` and `pc-reorg-original-report-20260922.txt`. `pc-reorg-earlier-recovery.json` also points to the reconstructed lineage.
- **[H6]** `/workspace/.files/transitions/{workspace-xfs-bcachefs.toml,README.md,path-map.toml}`. Disabled gates and explicit one-time transition contract.
- **[H7]** `.../history/disk-full-history-audit-completed/REPORT.md`, particularly its August–October chronology. Repeated temporary relief and guard coverage gaps, not proof of filesystem conversion failure.
- **Live reads, 2026-10-23:** `ionice -c3 lsblk -b -o NAME,SIZE,FSTYPE,FSVER,MOUNTPOINTS,MODEL,SERIAL,UUID`, `df -B1 -T`, `btrfs filesystem usage -b`, `findmnt -T /var/lib/containerd`, `pacman -Si`, `pacman -Q`, `modinfo bcachefs`, and a bounded containerd process listing. Local shell reads used idle I/O priority. No recursive size crawl or full-content scan ran.

### Public primary sources and relevant incident

- **[W1]** [WD Blue 3D NAND SATA SSD datasheet](https://documents.sandisk.com/content/dam/asset-library/en_us/assets/public/western-digital/product/internal-drives/wd-blue-ssd/data-sheet-wd-blue-3d-nand-sata-ssd-2879-800092.pdf): WDS400T2B0A is a SATA SSD. Datasheet speed figures are vendor maxima, not host measurements.
- **[W2]** [Bcachefs upstream](https://bcachefs.org/): distribution outside mainline from 6.18, DKMS support statement.
- **[W3]** [CachyOS v3 DKMS package](https://dashboard.cachyos.org/package/cachyos-extra-v3/x86_64_v3/bcachefs-dkms) and [package base](https://dashboard.cachyos.org/package/cachyos-extra-v3/x86_64_v3/bcachefs-tools): current package release and build date.
- **[W4]** [CachyOS forum: DKMS build failure on 7.2.6](https://discuss.cachyos.org/t/bcachefs-dkms-build-fails-on-7-2-6-1-cachyos/35992), September 18, 2026. One user report, not a compatibility verdict for 7.2.9.
- **[W5]** [Bcachefs FAQ](https://bcachefs.org/FAQ/): upstream production-status, migration, and no-current-deduplication statements.
- **[W6]** [Upstream release changelog](https://evilpiepirate.org/git/bcachefs-tools.git/plain/Changelog.mdwn): 1.39.7, October 4, 2026, and preceding migration fixes.
- **[W7]** [Bcachefs OverlayFS whiteout issue #635](https://github.com/koverstreet/bcachefs/issues/635): closed historical issue, not a current local runtime test.
- **[W8]** [Current upstream migration implementation](https://evilpiepirate.org/git/bcachefs-tools.git/plain/src/commands/migrate.rs): in-place reservation and superblock mechanics. Current source is not proof that this installed host can safely convert its source filesystems.
- **[W9]** [Bcachefs caching and targets](https://bcachefs.org/Caching/) and [getting started](https://bcachefs.org/GettingStarted/): targets, LRU cached extents, best-effort placement, and durability zero.
- **[W10]** [Linux dm-cache documentation](https://docs.kernel.org/admin-guide/device-mapper/cache.html): writeback, writethrough, passthrough, metadata, and clean detach requirements.
- **[W11]** [Linux bcache documentation](https://docs.kernel.org/admin-guide/bcache.html): backing-device preparation, sequential bypass, and missing dirty-cache risk.
- **[W12]** [lvmcache manual](https://man7.org/linux/man-pages/man7/lvmcache.7.html): LV-based cache attachment and distinction from dm-writecache.
- **[W13]** [Btrfs compression documentation](https://btrfs.readthedocs.io/en/latest/Compression.html): inherited policies, existing extents, heuristics, and NOCOMPRESS behavior.

Research used agent-reach's Exa route and direct primary-page reads. Agent Reach reports v1.6.0 available versus installed v1.5.0. No update was installed. Optional update instructions: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md.
