# Groot root-system activation handoff

## Status and provenance

Source: `.files` deploy/live normal merge **7e61208**, PR https://github.com/kvnloo/.files/pull/86 (feature head32dc7a5). The merge/push used `/tmp/files-live-deploy.lock`; subsequent manifest conflict resolution preserved UserLayer and BWS declarations. **Nothing in this report was executed as root by SystemLayer. All root changes remain staged.**

Correction: PR94 supersedes the rejected zram ram/8 and overcommit0 choices
from PR86. Corrected tested source is **db111c5**: zram unchanged, overcommit1.
Use the corrected PR94 merge, not the original7e61208 tree, for root activation.

Managed sources: `config/host/etc/`, `config/host/groot.toml`; installer: `scripts/apply-host-system`. Detailed inventory/assignment chains: `config/host/groot-audit-20261024.json`; corrected exercised receipt: `config/host/groot-preserved-policy-test-receipt.json` (older `groot-system-test-receipt.json` is historical).

`pacman -Qkk` ran outside the harness, streamed to `/tmp/groot-system-pacman-qkk.log`, completed in349.85s, exit1 (alterations and permission gaps, not clean). Backup metadata from `pacman -Qii` identified42 modified/missing/unreadable entries. Nine readable `.pacnew` files remain; no `.pacsave` in readable directories. Root-only paths, generated Limine config under `/boot`, and credential/environment contents remain explicitly UNKNOWN until the sudo audit. Account databases, credentials, resolver/mirror generated state and firewall policy were not copied blindly into dotfiles.

## Deviation table

| Setting | Observed live at inventory | Desired/staged action | Evidence / owner |
| --- | --- | --- | --- |
| Sysctl ownership | Five active local `.conf` files plus inactive `.pre-migration` backup | One tracked `99-groot.conf`; back up and retire old active files | Full per-key assignment chains in audit JSON |
| Dirty writeback | dirty_bytes0/background0, ratios20/10 despite later-on-disk byte policy | 268435456/67108864 byte limits; ratios become zero | Runtime divergence; installed CachyOS70 file already chooses256/64MiB |
| Swappiness |180, conflicting older150 | Retain180 | Historical file refaults3.6e9 vs anon0.9e9; zram-only swap |
| Watermark scale |200, conflicting older125 | Retain200, not claimed optimum | Historical36% direct reclaim |
| Page-cluster/VFS |0/50 | Let distro own these correct values | Installed70-cachyos-settings.conf |
| Overcommit |Runtime1, last-on-disk0 | **Keep1**, ratio100 | No measured reason to risk ENOMEM for large llama.cpp/Node/Bun/JVM mmap reservations; old file order is not compatibility evidence |
| CFS scheduler keys |Four obsolete keys absent | Remove invalid writes | Current7.2.9 sysctl inventory |
| Other networking/watch/process limits |Existing custom values | Preserve without claiming measured optimality | Avoid unrelated network/container behavior changes |
| Zram |logical=ram, resident=ram/2, zstd/prio200; historical failed_writes8655925; parent reports current11.63GB swapped/5.14GB resident (~2.2:1) | **Kept**; reconsider only with measured A/B (PSI + failed_writes + OOM count over >=24h) | Correct overcommitted workload budgets first; rejected ram/8 would remove most currently used swap capacity |
| sdb SSD |mq-deadline; current utilization99.4/98.9%, r_await8.81/8.10ms, w_await15.27/13.94ms | Keep distro mq-deadline; no BFQ A/B evidence | Current iostat samples; no SSD bandwidth cap |
| NVMe |kyber despite old local none writes | Remove redundant local scheduler rules; distro retains kyber | Vendor60-ioschedulers.rules sorts after singular local names |
| Mounts |sdb2 btrfs noatime/compress=zstd:3; NVMe XFS root/workspace noatime/lazytime; sda NTFS unmounted | Preserve, no remount | fstab, mount unit, findmnt, lsblk |
| Trim |fstrim.timer enabled/active weekly | Preserve; fleet declaration added | Packaged timer status |
| Boot |/proc/cmdline equals /etc/kernel/cmdline | Preserve source; generated Limine config UNKNOWN | Limine12.9; /boot permission denied |
| Oomd |system.slice and user-1000 broad candidates, pressure80%/30s, swap90% | Explicit --oomd stage removes broad monitored set; daemon remains on | Broad candidates can kill desktop/harness-containing cgroups |
| Earlyoom |active -m5 -s65; Python/node preferred victims | Remove --prefer; anchored harness/session --avoid; keep thresholds | Verified comm omp/hermes/tern/node-MainThread; packaged earlyoom1.9 help |
| Reclaim protection |session peak6346428416; Min0/Low4GiB | Root ancestor Min/Low7GiB; matching session settings owned by UserLayer | Measured5.91GiB peak plus~18% margin |
| Kernel victim ranking |manager adj100; sampled desktop/harness adj200 | Stage user@1000 OOMScoreAdjust0 for next manager lifecycle; UserLayer owns live disposable-child score800 | /proc sampled scores; never restart manager/desktop here |
| Journal |Packaged50MiB ceiling; usage43.5MiB; same-day incident history missing | SystemMaxUse1G, SystemKeepFree2G, MaxRetentionSec30day | <1% of~132GiB root; storage policy targets20GiB free upstream |

Distro reference: https://wiki.cachyos.org/features/cachyos_settings/ . Kernel semantics: https://docs.kernel.org/admin-guide/sysctl/vm.html . Installed vendor files, not latest web versions, define this host's baseline.

## Unified host memory budget

All peaks below are lifetime MemoryPeak observations, not simultaneous demand. Parent/child peaks overlap. Full byte-valued table is `host_memory_budget.groups` in the audit JSON.

| Group | Measured peak bytes | Current cap | Proposed/retained cap |
| --- | ---: | --- | --- |
| session.slice |6346428416 |infinity; Min0/Low4GiB |infinity; **Min/Low7GiB** |
| agent.slice |14181822464 |10GiB |10GiB; historical peak predates cap |
| z0-farm-llama |3126669312 |8GiB |8GiB; approved model envelope |
| ctx |5368709120 |5GiB |5GiB; owner CtxRootCause |
| T3 agent slice |1229709312 |20787200000 bytes |4GiB; UserLayer |
| telemetry-refresh |1365536768 |2621440000 bytes |Retain |
| neuroforge Anki |45793280 |768MiB |Retain |
| neuroforge game |109916160 |768MiB |Retain |
| neuroforge dashboard |32784384 |128MiB |Retain |
| dash-log-watch |54677504 |768MiB |Retain |
| service-watch |136204288 |256MiB |Retain |
| z0-ghcache |104251392 |256MiB |Retain |
| t3code server |1818808320 |infinity |Unbounded residual |
| hermes-web |311656448 |infinity |Unbounded residual |
| background.slice |1241526272 |infinity |Unbounded mixed-service residual |
| kubepods.slice |552407040 |20787200000 bytes |~3.36GiB after20GiB host reserve; verify actual Allocatable/cgroup |
| k3s server |1086623744 |infinity |No untested essential-service cap |
| docker daemon |163450880 |infinity |Unbounded daemon; containers separately bounded |
| containerd daemon |151011328 |infinity |Unbounded daemon; pods separately bounded |
| Ollama system endpoint |444395520 |infinity |Unbounded model service; no new cap without fit evidence |

Initial17 non-overlapping finite caps totalled **69.8657GiB**, against25082167296 bytes (~23.36GiB) physical RAM. This sum includes additional Docker/earlyoom/polkit and short-lived bounded groups in `memory.disjoint_caps`; nested agent/pod limits and the census's own transient scope were excluded. The T3/Kubernetes corrections lower the nominal sum to~38.5GiB, still greater than RAM.

Rule adopted in manifest `[budget]`: physical RAM minus effective session.slice MemoryMin must be at least the largest non-desktop group cap. With7GiB protected, remaining17565974528 bytes (~16.36GiB) exceeds largest proposed finite10GiB cap. Missing/unbounded groups remain UNKNOWN, never silently omitted to manufacture a pass. This necessary single-cap guard is not aggregate reservation accounting and is not a global-OOM guarantee. Root user.slice -> user-1000.slice -> user@1000.service Min/Low must all read7516192768; UserLayer owns matching session7GiB.

## Exact ordered activation commands

Run these yourself from the intended merged checkout. Preserve each printed backup path; oomd and system stages create separate receipts. Do not paste audit output into public services.

```sh
cd /mnt/zer0models/worktrees/files-live
sudo scripts/apply-host-system --audit
sudo scripts/apply-host-system --oomd --apply
sudo scripts/apply-host-system --apply
```

`--oomd` alone and no flags are dry-run plans; `--apply` is required for mutation. Optional previews, without sudo: `scripts/apply-host-system --oomd` and `scripts/apply-host-system`.

### 1. Read-only audit

Command: `sudo scripts/apply-host-system --audit`.

Expected: JSON path/link/hash records, names of upgrade leftovers, streamed package integrity findings, `PACKAGE_INTEGRITY_EXIT=...`, and `AUDIT unreadable=N; values/credentials were not printed`. Root access should close prior permission gaps; any remaining nonzero unreadable count is still UNKNOWN. Package alterations are expected, not grounds to reset package files blindly. No promise that exit1 means only one problem.

Restarts: none. Rollback: none, this stage makes no changes.

### 2. Oomd candidate cutover

Command: `sudo scripts/apply-host-system --oomd --apply`.

Expected: five root opt-out drop-ins installed/backed up; daemon-reload; oomctl contains **no Path: entries**; line `VERIFIED: oomctl monitored set empty; hard caps/kernel OOM remain, no global OOM guarantee`. A remaining candidate causes failure, not a protection claim. Threshold settings remain swap90%, default pressure60%/30s, but apply to no candidate. No killable slice is introduced.

Restarts: none; oomd stays running. Rollback: run the receipt rollback block below with **this stage's** printed backup directory. Restoring old monitoring can restore the original whole-cgroup kill risk; do so only deliberately.

### 3. Root system configuration

Command: `sudo scripts/apply-host-system --apply`.

Expected output includes:

```text
VERIFIED: root user.slice -> user-1000.slice -> user@1000.service memory.min/low=7516192768
STAGED: user@1000 OOMScoreAdjust=0 for next controlled login/reboot; existing manager/process scores unchanged
vm.swappiness = 180
vm.watermark_scale_factor = 200
vm.page-cluster = 0
vm.dirty_bytes = 268435456
vm.dirty_background_bytes = 67108864
vm.overcommit_memory = 1
VERIFIED: earlyoom active; -m 5 -s 65; anchored harness/session avoid; no --prefer
UNCHANGED: zram logical=ram resident=ram/2 zstd priority=200; no resize/reboot change
```

Dirty ratios should read0 after byte settings. The script prints journal disk usage and merged journald configuration; later `50-groot-retention.conf` must show1G/2G/30day. It prints actual backup/changed/retired counts, not a fabricated fixed count.

Restarts: **earlyoom only if its config changed; systemd-journald only if its config changed**, with logs and verification. No desktop, user manager, terminal, gateway, zram, mount, k3s or application restart. Performs sysctl --system, daemon-reload, udev reload and a narrow block-device trigger; never a USB or live-zram trigger. No journal vacuum command.

Rollback: receipt block below using **this system stage's** backup. That restores retired sysctl/scheduler files as well as changed files and removes only newly installed paths. Zram capacity is unchanged; no zram activation or rollback reboot is required by this deployment.

### Receipt-based rollback command (oomd or system stage)

Substitute the exact backup directory printed by the stage. This is an operator command, not something SystemLayer ran. Restores only receipt-owned paths; refuses path traversal; credentials never appear in argv.

```sh
sudo python3 - /var/backups/files-host/REPLACE_WITH_PRINTED_STAGE_DIRECTORY <<'PY'
import json, os, pathlib, shutil, subprocess, sys
backup = pathlib.Path(sys.argv[1]).resolve(strict=True)
if backup.parent != pathlib.Path('/var/backups/files-host'):
    raise SystemExit('Expected one direct stage backup under /var/backups/files-host')
receipt = json.loads((backup / 'receipt.json').read_text())
changed = set()
for entry in receipt['files']:
    target = pathlib.Path(entry['live'])
    if not target.is_absolute() or '..' in target.parts or not str(target).startswith('/etc/'):
        raise SystemExit('Invalid receipt target')
    saved = backup / str(target).lstrip('/')
    if entry['existed'] and not (saved.exists() or saved.is_symlink()):
        raise SystemExit('Missing backup: ' + str(saved))
for entry in receipt['files']:
    target = pathlib.Path(entry['live'])
    saved = backup / str(target).lstrip('/')
    if target.exists() or target.is_symlink():
        target.unlink()
    if entry['existed']:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, target, follow_symlinks=False)
    changed.add(str(target))
subprocess.run(['systemctl', 'daemon-reload'], check=True)
if receipt['stage'] == 'system':
    subprocess.run(['sysctl', '--system'], check=True)
    subprocess.run(['udevadm', 'control', '--reload'], check=True)
    if '/etc/default/earlyoom' in changed:
        subprocess.run(['systemctl', 'restart', 'earlyoom.service'], check=True)
    if '/etc/systemd/journald.conf.d/50-groot-retention.conf' in changed:
        subprocess.run(['systemctl', 'restart', 'systemd-journald.service'], check=True)
else:
    subprocess.run(['oomctl', '--no-pager'], check=True)
print('RESTORED receipt-owned paths; next-manager OOM default waits for controlled lifecycle')
PY
```

Do not delete the backup after rollback. Runtime block schedulers are not reset automatically by rollback; package rules are reloaded and next device lifecycle reapplies them. No online swapoff is part of rollback.

### 4. Separate k3s maintenance window

Only after checkpointing workloads and approving the k3s restart:

```sh
sudo scripts/setup-k3s.sh server
sudo systemctl is-active k3s.service
KUBECONFIG="$HOME/.kube/k3s.yaml" kubectl get node groot -o jsonpath='{.status.capacity.memory}{" capacity; "}{.status.allocatable.memory}{" allocatable\n"}'
sudo systemctl show kubepods.slice -p MemoryMax
```

Expected: `config changed; restarting k3s` if the installed version matches and reserve config differs, or explicit installer output if version differs. `is-active` returns `active`. Node Allocatable and kubepods cap should decrease from~19.36GiB toward~3.36GiB after20GiB host reserve; use actual reported bytes/Ki, not a guessed exact value. The command also maintains firewall rules/kubeconfig and enablement; it is not a narrow sysctl-only operation.

Rollback of the configuration-only reserve change: select the exact timestamped backup created by this invocation, not a wildcard/latest guess:

```sh
sudo cp -a /etc/rancher/k3s/config.yaml.bak.REPLACE_WITH_THIS_INVOCATION_TIMESTAMP /etc/rancher/k3s/config.yaml
sudo systemctl restart k3s.service
sudo systemctl is-active k3s.service
```

Expected restored service active and prior Allocatable. If setup installed/upgraded a different k3s binary or changed firewall state, that broader installation is not reversed by restoring YAML; stop and use the owner's version-specific rollback. This handoff does not invent a safe automatic binary downgrade or delete cluster data.

## Next login / reboot only

- `user@1000.service OOMScoreAdjust=0`: next controlled user-manager lifecycle; existing manager/desktop processes keep their prior scores. No live manager restart is performed.
- Reclaim MemoryMin/Low: intended live reload, explicitly read back in root kernel cgroups. Failure to match is an activation failure, not deferred success.
- Oomd candidate removal, sysctl, earlyoom and journald: take effect during their explicit stages, subject to emitted verification.
- k3s reserve: takes effect at its separate server restart, not at host merge/apply.

## Residual risks (one line each)

- Concurrent capped jobs and unbounded groups can still trigger global OOM; the nominal cap sum remains greater than physical RAM.
- MemoryMin protects reclaim, not immunity from kernel OOM victim selection; largest-cap arithmetic is not aggregate reservation accounting.
- Earlyoom --avoid is a preference, not immunity; node-MainThread also matches some Node tool workers because comm is not identity.
- Earlyoom TERM requires both free memory<5% and free swap<65%; with current23.36GiB logical zram that swap gate is used>~8.18GiB; zram is real RAM, not free capacity.
- Existing manager/desktop score changes require the planned lifecycle; no claim that the staged root OOM default already protects live processes.
- Zram remains logical=ram/resident=ram/2; workload overcommit can still exhaust it, so reassess only with >=24h A/B PSI, failed_writes and OOM-count evidence.
- Journal30day is maximum age, not guaranteed retention; volume/1GiB ceiling may rotate sooner, and root free space below2GiB can still vacuum history.
- Nine pending .pacnew files and root-only audit gaps are not silently resolved by installing these managed files.
- Disposable-only oomd slice migration is not implemented; mixed agent-workloads-v2.scope contains MCP/AgentsView and remains ineligible for kill monitoring.
- Live root/systemd activation, service restarts, reboot and k3s maintenance have not been exercised by this agent.

## Exercised verification

Corrected immutable **db111c5** snapshot, S25 job **20261024-232659-264b**: `Ran 11 tests in1.402s`, `OK`, `command_exit=0`. Covers fake-root render/diff/idempotence/backups, dry-run no writes, separate oomd stage, symlink refusal, secret-safe audit, earlyoom regex, root reclaim/ranking fixtures, retained ram/ram2 zram capacity, overcommit1, budget disclosure and journal settings. Fleet envelope returned false `guest_restarted/76`; KueuePriority owns that lifecycle defect. No overall fleet-success claim. Three own queued MBP duplicates were explicitly deleted; no MBP test pass is claimed. Spool: `/home/kvn/.local/state/fleet/runs/20261024-232659-264b-omarchy-phone.log`. Earlier da69660 receipt remains historical, not proof of the corrected values.

## Nine .pacnew decisions (readable diff review)

All nine live/package pairs were readable; no pair below is classified UNKNOWN.
Evidence: full `diff -u` output in this run, artifact5056 (1532 lines), plus
explicit mirror Server-line review. These decisions preserve functional local
configuration and archive only reviewed package suggestions. They do not run
pacdiff, change TPM keys, regenerate initramfs or replace network configuration.

| .pacnew path | Live vs package diff summary | Decision and reason | Exact action below |
| --- | --- | --- | --- |
| /etc/locale.gen.pacnew | Package adds commented hrx_BR.UTF-8 and removes Calamares footer with enabled en_US.UTF-8 | Keep local; replacing would disable selected locale; added comment has no runtime effect | archive locale.gen.pacnew |
| /etc/mkinitcpio.conf.pacnew | Package changes active HOOKS from udev/keymap/consolefont/plymouth to systemd/sd-vconsole and changes ordering; other changes are comments/microcode examples | Keep local tracked config/host/etc/mkinitcpio.conf; a boot-stack migration needs separate controlled initramfs/boot proof | archive mkinitcpio.conf.pacnew |
| /etc/pacman.d/cachyos-mirrorlist.pacnew | Local is Oct20 rate-mirrors0.31 ranking; April11 package is static geographic/CDN list, adds/removes hosts and changes Sweden URL | Keep generator-owned local; preserve measured ordering, refresh via owning rate-mirrors timer rather than copy an older list | archive cachyos-mirrorlist.pacnew |
| /etc/pacman.d/cachyos-v3-mirrorlist.pacnew | Same ranked-vs-static host changes, both preserve $arch_v3 paths | Keep generator-owned local; do not replace current ranking with older static defaults | archive cachyos-v3-mirrorlist.pacnew |
| /etc/pacman.d/cachyos-v4-mirrorlist.pacnew | Same ranked-vs-static host changes, both preserve $arch_v4 paths | Keep generator-owned local for same reason | archive cachyos-v4-mirrorlist.pacnew |
| /etc/pacman.d/mirrorlist.pacnew | Local has active CachyOS Arch mirror plus Oct20 ranked servers; June10 package is a worldwide list with commented Server lines | Keep local; copying package would remove usable active servers and generator ranking | archive mirrorlist.pacnew |
| /etc/resolv.conf.pacnew | Local NetworkManager file uses nameserver127.0.0.53 with edns0/trust-ad; package is two comments, no nameserver | Keep NetworkManager/resolved owner; blank package file would break DNS | archive resolv.conf.pacnew |
| /etc/tpm2-tss/fapi-profiles/P_ECCP384SHA384.json.pacnew | Package changes TPM2_ALG/curve constants to lowercase aliases, adds noda to SRK template, removes srk_persistent0, lowercases policysecret | Keep local for now; not a harmless comment-only diff; persisted FAPI usage/migration compatibility is unverified, so do not silently change SRK semantics | archive ECC package suggestion, preserve for explicit TPM maintenance |
| /etc/tpm2-tss/fapi-profiles/P_RSA3072SHA384.json.pacnew | Same alias/noda/policy changes; importantly removes srk_persistent1; keyBits3072/PCR selection unchanged | Keep local; removal changes explicit persistence semantics and no verified TPM migration contract exists | archive RSA package suggestion, preserve for explicit TPM maintenance |

The TPM keep decisions are deliberate current-policy preservation, not a claim
that old/new FAPI compatibility was tested. Retain the package suggestions.
No TPM provisioning, clearing, key creation or identity migration is authorized.

### Exact optional review-archive commands Kevin runs

These archive only the nine reviewed .pacnew files, never the live files.
Run after the root audit and only if the diffs still match this review.
If a package upgrade changed a pair, stop and review the new diff instead.

```sh
sudo install -d -m0700 /var/backups/files-host
review=$(sudo mktemp -d /var/backups/files-host/pacnew-review.XXXXXXXX)
sudo mv -n -- /etc/locale.gen.pacnew "$review/locale.gen.pacnew"
sudo mv -n -- /etc/mkinitcpio.conf.pacnew "$review/mkinitcpio.conf.pacnew"
sudo mv -n -- /etc/pacman.d/cachyos-mirrorlist.pacnew "$review/cachyos-mirrorlist.pacnew"
sudo mv -n -- /etc/pacman.d/cachyos-v3-mirrorlist.pacnew "$review/cachyos-v3-mirrorlist.pacnew"
sudo mv -n -- /etc/pacman.d/cachyos-v4-mirrorlist.pacnew "$review/cachyos-v4-mirrorlist.pacnew"
sudo mv -n -- /etc/pacman.d/mirrorlist.pacnew "$review/mirrorlist.pacnew"
sudo mv -n -- /etc/resolv.conf.pacnew "$review/resolv.conf.pacnew"
sudo mv -n -- /etc/tpm2-tss/fapi-profiles/P_ECCP384SHA384.json.pacnew "$review/P_ECCP384SHA384.json.pacnew"
sudo mv -n -- /etc/tpm2-tss/fapi-profiles/P_RSA3072SHA384.json.pacnew "$review/P_RSA3072SHA384.json.pacnew"
printf 'Preserved reviewed package suggestions at %s\n' "$review"
```

Expected: moves exit0, original live configuration untouched; no service restart
or boot change. Preserve the printed review path. Before any rollback, refuse
to overwrite a newly generated .pacnew file. To undo one review decision,
move its archived basename back to the exact source path from its command,
for example `sudo mv -n -- "$review/locale.gen.pacnew" /etc/locale.gen.pacnew`.
Apply that same inverse to any of the other eight paths as required.

## Optional: restore NVIDIA vibrance on driver 615.71.09

Do not disable `nvibrant.service`: Kevin uses its existing `870 870 870 870` settings for gaming. The installed system package is `nvibrant-bin 1.2.1-1` (`/usr/bin/nvibrant`), whose bundled fallback for 610.43 fails `AllocDevice ioctl` on the installed 615.71.09 driver. This is not a boot-ordering diagnosis.

Upstream [v1.3.0](https://github.com/Tremeschin/nvibrant/releases/tag/v1.3.0), released 2026-09-10, explicitly adds [driver 615.71.09 support](https://nvibrant.tremeschin.com/changelog/#v1.3.0). The [AUR package](https://aur.archlinux.org/packages/nvibrant-bin) is currently `1.3.0-1`. Because the installed package is root-owned, no agent performed this upgrade or claimed a successful vibrance application.

Kevin may review the AUR package and run this optional package upgrade (only this package, not a system-wide upgrade):

```sh
paru -S --needed nvibrant-bin
pacman -Q nvibrant-bin
systemctl --user start nvibrant.service
journalctl --user -u nvibrant.service -n 30 --no-pager
systemctl --user show nvibrant.service -p Result -p ExecMainStatus
```

Expected: `nvibrant-bin 1.3.0-1` or a later reviewed release supporting this exact driver, the unit exits 0 and its output reports application of the existing vibrance values, with no unsupported-driver fallback or ioctl failure. Only after that proof, clear the old failed state with `systemctl --user reset-failed nvibrant.service`. No driver upgrade, reboot, desktop restart, or vibrance-value change is authorized here.

