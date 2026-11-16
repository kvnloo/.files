# R09 activation blockers

This review preserves the existing native-updater proposal without activating it. R09 is not complete. No package refresh, installation, timer activation, service restart, or reboot ran in this execution. Evidence directory: `/mnt/zer0models/workspace/zer0/data/operations/intent-analyzer-20261104/ayo-runs/exec-R09`.

## Latest observation, 2026-11-16 at 05:46 UTC

The installed updater changed independently. SHA256 is now `7a0c303a137d89da30aae70c09eb75ebf7998afe07b96e48bcb4167b2a87e87e`. A new DKMS guard checks module availability before reboot. Its comment attributes a missing `/mnt/tier` after the previous maintenance reboot to `bcachefs-dkms`. That comment is incident attribution, not an independently verified cause. Sources: execution `logs/20261116-current/host.log:226-228,280-292`.

The guard runs after `pacman -Su`. If it holds the reboot, installation already occurred. This permits installed reboot-class updates to wait without their intended immediate reboot. Daily classification still precedes a separate live database refresh and installation. Neither mode installs from the staged list. No workload-drain check precedes installation or reboot. These code paths do not meet the requested safety conditions. Source: execution `logs/20261116-current/host.log:255-294`; `ITEM.json:4-6`.

Both custom timers remain active and enabled. The next maintenance deadline is November 22 at 04:00 CST, or 10:00 UTC. The installed timer still labels its window a placeholder requiring Kevin's choice. The supplied item and verdict do not establish approval. Sources: execution `logs/20261116-current/host.log:94-105,154-178,201-203`; `VERDICT.json:12-15`.

The host now reports bcachefs and gpu-unlock installed for both listed kernels. `/mnt/tier` is mounted. The running kernel matches installed `linux-cachyos` at 7.3.4, and loaded NVIDIA matches userspace at 620.70.06. Three recorded boots occurred on November 15. These checks establish current module and mount state, not a tested recovery procedure or workload restoration. Source: execution `logs/20261116-current/boot.log:3-21,55-63`.

The latest three update receipts still end with November 15's `applied-rebooting`, rc 0. The journal retains 6min 29.916s CPU, 4min 43.970s wall time, 5.9G peak memory, and 103M peak swap. No new transaction or guard execution was requested here. Foreground impact, network transfer, and disk IO remain unmeasured. Sources: execution `logs/20261116-current/host.log:181-199,297-301`; `logs/20261116-current/boot.log:23-53`.

Root and cache share XFS with 9,596,356 KiB available, below the native proposal's 15 GiB floor. Native updater and queried snapshot packages remain absent. The installed units' recovery-document target remains missing. This does not prove that no backup exists. The read-only capture exits 1 because the staged file is absent. Missing-package query also exits 1. Sources: execution `logs/20261116-current/host.log:205-224,303-305,319-321`; `logs/20261116-current/boot.log:65-66`; `scripts/setup-native-updates:45-53`.

Fleet admission tests did not start. Kueue's `lanes` lookup failed, exit 1. No local test-suite fallback ran. Native syntax and read-only commands completed, but diagnostic `check` masks missing packages and is not readiness proof. Sources: execution `logs/20261116-current/fleet.log:1-4`; `logs/20261116-current/host.log:11-25,90-92`.

R09 remains incomplete. Reconcile the active implementation with the host-setup owner before deploying another updater. Privileged changes, reboot, restore, and package operations require a separately authorized execution. No installed configuration changed here.

## Earlier observation, 2026-11-15 at 17:16 UTC

The installed custom updater ran independently before this inspection. Its receipt reports `applied-rebooting`, rc 0, at 04:04:44 CST, or 10:04:44 UTC. The journal records successful maintenance completion and a new boot at 04:05 CST. This is an observed maintenance application and reboot, not an action requested by this execution. Sources: execution `logs/20261115-current/host.log:378-386`; `logs/20261115-current/boot.log:22-27,57-60`.

The running kernel is `7.3.4-1-cachyos`, matching the installed kernel and NVIDIA kernel-package version. The loaded NVIDIA driver and `nvidia-utils` both report `620.70.06`. These checks do not establish workload recovery or rollback safety. Source: execution `logs/20261115-current/boot.log:1-20`.

The previous boot's maintenance journal records 6min 29.916s CPU time, 4min 43.970s wall time, 5.9G peak memory, and 103M peak swap. Current service counters are unset after reboot. Transfer volume, disk IO, foreground impact, and recovery remain unmeasured. Sources: execution `logs/20261115-current/boot.log:57-60`; `logs/20261115-current/host.log:272-290`.

Both custom timers remain active and enabled. The next maintenance deadline is November 22 at 04:00 CST, or 10:00 UTC, in `America/Chicago`. The installed timer still calls its window a placeholder requiring Kevin's choice. Approval is not established by the supplied item and verdict. Sources: execution `logs/20261115-current/host.log:183-196,245-255,292-294,403-406`; `ITEM.json:4-6`; `VERDICT.json:12-15`.

Transaction binding and workload drain remain absent from the installed source. It classifies one check result before a separate live refresh and installation. It never reads the staged file for installation. The updater hash is unchanged. Source: execution `logs/20261115-current/host.log:317-376`.

Root and cache share XFS with 7,201,124 KiB available, below the native proposal's 15 GiB floor. The native updater and queried snapshot tools remain absent. The units' recovery-document target is missing. These checks do not prove that no backup exists. The capture exits 1 because the staged file is now absent, not because the maintenance transaction failed. Sources: execution `logs/20261115-current/host.log:296-315,384-409`; `scripts/setup-native-updates:45-53`.

Fleet tests did not start. The absolute-path invocation failed querying Kueue's `lanes` clusterqueue, exit 1. An earlier clean-shell invocation failed PATH lookup, exit 127. No groot fallback ran. Sources: execution `logs/20261115-current/fleet-absolute.log:1-12`; `logs/20261115-current/fleet.log:1-4`.

R09 remains incomplete. A successful maintenance observation does not prove safe non-reboot transactions, approved drain/defer handling, or consistent rollback. No package, service, or reboot change was invoked here.

## Earlier observation, 2026-11-15 at 04:18 UTC

The existing clean `ayo/R09` worktree was inspected without changing the dirty owner checkout. The read-only capture completed with exit 0. Its diagnostic `check` still masks missing packages and does not establish readiness. Sources: execution `20261115-revalidation.log:1-25,89-91,299-310`; `host-inspection.log` records owner HEAD and proposal hashes.

Both custom timers remain active and enabled. Maintenance next runs November 15 at 04:00 CST, `America/Chicago`, or 10:00 UTC. The installed unit still labels this window a placeholder requiring Kevin's choice. The item and verdict do not establish approval. No timer was changed. Sources: execution `20261115-revalidation.log:93-104,153-163,200-202`; `ITEM.json:4-6`; `VERDICT.json:12-15`.

The installed updater hash remains `2c6646cee8eb36e3a23b62ae13a8fa54a73734f9cb117dd266f98f28e401934e`. It classifies `checkupdates` output before a separate live refresh and application. It never reads the staged file for installation. No workload-drain gate precedes its possible reboot. These are source findings, not a reproduced transaction. Source: execution `20261115-revalidation.log:225-284`.

The latest receipt remains November 14 staging, with 433 output lines. The staged file has 437 lines. Neither count proves unique packages or safe installation. Current CPU and peak-memory counters are unset. IO and IP accounting remain off, so this capture adds no installation or foreground-impact measurement. Source: execution `20261115-revalidation.log:180-198,286-294`.

Root and cache share XFS with 8,764,972 KiB available, below the proposal's 15 GiB floor. The native updater, Snapper, and Timeshift are absent. The units' recovery-document target is absent too. These checks do not prove no backup exists. No restore drill ran. Sources: execution `20261115-revalidation.log:204-223`; `20261115-owner-extra.log:1-2`; `scripts/setup-native-updates:45-53`.

Fleet admission tests did not start. `fleet-build --node mbp --light --local-data --wait 1800` failed while querying Kueue's `lanes` clusterqueue, exit 1. No groot fallback ran. Source: execution `20261115-fleet-tests.log:1-3`.

R09 remains incomplete. Transaction binding, approved drain/defer handling, consistent rollback, and actual resource-impact evidence remain missing. Privileged maintenance, reboot, service changes, and recovery execution require separate owner authorization. No such action ran here. Sources: findings above; recovery gates below; `VERDICT.json:12-15`.

## Earlier observation, 2026-11-14 at 15:46 UTC

This capture is from the verdict's host, not the MBP. The MBP report previously in the execution folder is preserved in `logs/20261114-preserved-mbp/`. The existing clean `ayo/R09` worktree was reused. Sources: execution `logs/20261114-groot-revalidation.log:2-10`; `logs/20261114-preserved-mbp/REPORT.md:3-6`.

Both custom timers remain enabled and active. The maintenance deadline is **November 15 at 04:00 CST**, `America/Chicago`. The installed timer still calls this a placeholder requiring Kevin's choice. Approval is not established by the supplied item or verdict. No timer was changed here. Sources: execution `logs/20261114-groot-revalidation.log:93-178,201-203`; `ITEM.json:4-6`; `VERDICT.json:12-15`.

The installed updater still has SHA256 `2c6646cee8eb36e3a23b62ae13a8fa54a73734f9cb117dd266f98f28e401934e`. It classifies separate check output, then refreshes and applies a live transaction. It has no workload-drain check and can request a reboot. It never reads the staged list before installation. These are source findings, not a live transaction test. Source: execution `logs/20261114-groot-revalidation.log:226-285`.

Today's daily receipt reports staging with 433 output lines. The staged file has 437 lines. Neither count proves unique packages or a safe installation. The daily service retains a peak of 1,218,723,840 bytes and 42.789372 CPU-seconds. IO and IP accounting are off. These are staging counters, not installation or foreground-impact measurements. Source: execution `logs/20261114-groot-revalidation.log:181-198,287-295`.

Root and package cache share XFS root with 10,552,456 KiB available, below the proposal's 15 GiB admission floor. `pacman-offline`, Snapper, and Timeshift remain absent. The live units' documentation target, `/workspace/.files/docs/fleet/OS-UPDATE.md`, is also absent. None of this proves that no backup exists. No restore or recovery boot ran. Sources: execution `logs/20261114-groot-revalidation.log:205-224`; `logs/20261114-groot-owner-state.log:14-15`; `scripts/setup-native-updates:45-53`.

The existing syntax, diagnostic, and cadence probes completed. Diagnostic exit zero is not readiness. The four admission tests did not start: `fleet-build --node mbp --light --local-data --wait 1800` failed with exit 1 while querying Kueue's `lanes` clusterqueue. No tests ran on groot as a fallback. Sources: execution `logs/20261114-groot-revalidation.log:13-92`; `logs/20261114-groot-fleet-tests.log:1-3`.

R09 remains incomplete. The owner must reconcile updater ownership and bind classification to the actual transaction. Kevin must confirm or replace the active window and define drain/defer behavior. Privileged update, reboot, and restore execution requires separate authorization. Cancellation and cached package downgrades do not prove consistent OS rollback. Sources: the source and recovery findings above; this review's recovery gates below; `VERDICT.json:12-15`.

## Earlier observation, 2026-11-12 at 14:01 UTC

Both custom timers remain enabled and active. Maintenance is still due November 15 at 04:00 CST, `America/Chicago`, and the installed unit still labels that time a placeholder. The next daily deadline is November 13 at 03:39:41 CST. No window approval was established. Source: execution `logs/20261112-revalidation.log:93-178,200-202`.

The November 11 daily receipt reports `checkupdates-failed`, exit 1. November 12 reports `staged-for-maintenance`, exit 0, with 417 output lines; the staged file has 421 lines. These are output-line counts, not unique-package counts or proof of an installation. The installed updater hash is unchanged at `2c6646cee8eb36e3a23b62ae13a8fa54a73734f9cb117dd266f98f28e401934e`. It still classifies separate check output before a different live transaction and has no workload-drain gate. Sources: execution `logs/20261112-revalidation.log:225-294`.

Root and package cache share XFS root, with 10,738,812 KiB available, below the proposal's 15 GiB floor. The native updater, Snapper, and Timeshift remain absent. Current systemd peak-memory and CPU counters are unset for both custom services. Earlier measurements below are historical staging measurements, not current installation-impact evidence. Sources: execution `logs/20261112-revalidation.log:180-223`.

Native setup now rejects `enable` before privilege checks or mutations unless systemd reports both custom timers as `not-found`. Installed disabled timers, unknown states, and discovery failures also refuse. The actual host CLI refused with exit 1 while both custom timers remained active. This prevents duplicate setup, not unsafe transactions in the active custom updater. Sources: `scripts/setup-native-updates:17-29`; execution `logs/20261112-live-admission.log`.

Four subprocess admission tests cover both conflicting timers, unknown/masked/error states, discovery failure, and the absent-timer path. They use temporary command stubs and never operate real packages or services. Fleet logs record failing-before and passing-after evidence from the MBP. This is admission coverage only; successful installation, reboot, restoration, and foreground impact remain unverified. Sources: `tests/test_native_updates.py`; execution `logs/20261112-guard-red.log`, `logs/20261112-guard-green.log`.

## Earlier observation, 2026-11-11 at 06:58 UTC

Both custom timers remain enabled and active. Maintenance next runs November 15 at 04:00 CST, `America/Chicago`. The daily timer next runs today at 03:58:52 CST. The maintenance unit still calls its schedule a placeholder requiring Kevin's choice. No approval was established from the allowed evidence. Sources: execution `logs/20261111-revalidation.log:93-178,200-202`.

The November 8 maintenance receipt reports `upgrade-failed`, exit 1. November 9's daily receipt reports `applied`, exit 0, with an empty reboot class. November 10's receipt reports staging, exit 0, with 128 output lines. The staged file has 132 lines. Counts are not unique-package counts. These are existing receipts, not transactions run by this execution. Source: execution `logs/20261111-revalidation.log:286-294`.

The installed updater changed to SHA256 `2c6646cee8eb36e3a23b62ae13a8fa54a73734f9cb117dd266f98f28e401934e`. Its new comment describes a previous half-applied transaction and missing pacman binary. That comment is not independent proof of the incident's full extent. The code now runs `pacman -Syuw --noconfirm` followed by `pacman -Su --noconfirm`, after classifying separate `checkupdates -d` output. Download failure exits after refreshing the live databases. Classification is still not bound to the applied transaction, and maintenance still has no workload-drain gate before installation or reboot. Sources: `/etc/os-update/run:25-54`; execution `logs/20261111-revalidation.log:225-284`.

The running kernel is `7.3.3-1-cachyos`. Installed kernel and module packages are both `7.3.3-1`. Loaded NVIDIA version `620.70.06` matches the version component of installed `nvidia-utils 620.70.06-2`. Boot time is November 9 at 08:19:43 local time. These checks establish current version observations, not a tested rollback or proof that the failed maintenance recovered itself. The bounded maintenance journal query returned no entries. Source: execution `logs/20261111-incident-readonly.log:3-28`.

Root is XFS with 14,964,932 KiB available, below the proposal's 15 GiB floor of 15,728,640 KiB. The cache now resolves to `/var/cache/pacman/pkg` on root, not the previously observed separate mount. The native updater, Snapper, and Timeshift remain absent. Missing packages do not prove there is no backup. Sources: execution `logs/20261111-revalidation.log:204-223`; `scripts/setup-native-updates:31-39`.

The latest retained daily counters show `MemoryPeak=185802752` bytes, about 177 MiB, and `CPUUsageNSec=7475446000`, about 7.48 CPU-seconds. IO and IP accounting are disabled. No maintenance counters are retained. This is evidence from staging, not installation or foreground-latency measurement. Source: execution `logs/20261111-revalidation.log:180-198,289`.

`python3 revalidate-host.py` completed with exit 0. It preserved the expected missing-package exit 1. Bash syntax, native diagnostic, and cadence audit completed. The native diagnostic's exit 0 is still not readiness. No installation, service change, reboot, or recovery drill ran in this pass. Sources: execution `logs/20261111-revalidation.log:10-91,204-209,296-308`.

## Earlier observation, 2026-11-06 at 15:02 UTC

This observation supersedes the historical host facts below. Both custom timers remain enabled and active. Maintenance still next runs on November 8 at 04:00 CST, `America/Chicago`. The daily timer next runs on November 7 at 03:35:51 CST. The installed maintenance unit still labels its schedule a placeholder requiring Kevin's choice. Sources: execution `logs/revalidation-latest.log:93-178,200-202`.

The installed updater hash remains `0e085d4a8551137a35d0b325ef54dc6187168b414c79568c50887be210005f99`. Classification and application still use different transactions, without workload drain. Maintenance can reboot. These are source findings, not an executed installation test. Sources: execution `logs/revalidation-latest.log:225-278`; `/etc/os-update/run:25-46`.

A newer daily receipt records staging at 03:43:32 CST today, exit 0, and 1,143 pending output lines. The staged file has 1,147 lines. Neither count proves unique packages or installation. Retained service counters now show `MemoryPeak=1863843840` bytes, about 1.74 GiB, and `CPUUsageNSec=34868699000`, about 34.9 CPU-seconds. IO and IP accounting remain disabled. These are observations of an existing run, not a new update experiment. Sources: execution `logs/revalidation-latest.log:180-198,280-287`.

Root is XFS with 21,583,600 KiB available. The native updater, Snapper, and Timeshift packages remain absent. Missing packages do not prove that no backup exists. No successful restore drill or safe installation was established. Sources: execution `logs/revalidation-latest.log:204-223`.

Rerun `python3 revalidate-host.py` in the evidence directory. It completed with exit 0, retaining the expected missing-package query exit 1. Bash syntax and both read-only native commands completed. The native diagnostic still exits 0 despite the missing updater, so it is not a readiness check. No service change, installation, or recovery drill ran in this pass. Sources: execution `logs/revalidation-latest.log:10-91,204-209,289-300`.

## Earlier revalidation, 2026-11-06 at 02:46 UTC

At 02:46 UTC, both custom timers were enabled and active, root had 22,366,540 KiB available, and the earlier receipt and counters were unchanged. Source: execution `logs/revalidation-current.log`. The following observations predate the latest capture.

This section supersedes the historical host observations below. Both custom timers, `os-update.timer` and `os-update-maintenance.timer`, are now enabled and active. The native `pacman-offline` proposal remains absent. Sources: evidence `logs/20261106-readonly.log`, commands `pacman -Q` and `systemctl show`; `logs/20261106-active-updater.log`, timer properties.

The maintenance timer next elapses on **2026-11-08 at 04:00 CST**, timezone `America/Chicago`. Its installed unit still calls this a placeholder requiring Kevin's choice. This review cannot establish approval from the allowed item and verdict. The daily timer next elapses on 2026-11-06 at 03:42:59 CST. Sources: `/etc/systemd/system/os-update-maintenance.timer:2-6`; evidence `logs/20261106-active-updater.log`, `timedatectl show` and `systemctl show` outputs.

The installed `/etc/os-update/run` matches the previously reviewed implementation at `5e57eed4f9b6d7f5466f09c5790468dc2e62e230`. It checks one package set, then refreshes and applies another with `pacman -Syu --noconfirm`. It never reads the staged list before installation and has no workload-drain gate. Maintenance can call `systemctl --no-block reboot`. These are source findings, not a reproduced upgrade or reboot. Sources: `/etc/os-update/run:25-46`; evidence `logs/20261106-active-updater.log` and `logs/20261106-resource-source.log`.

A prior daily run completed on November 5 at 15:40:12 CST. Its receipt reports `staged-for-maintenance`, 1,715 pending output lines, and exit 0. This is not proof of 1,715 unique packages or an installation. The staged file currently has 1,719 lines. Sources: `/var/log/os-update.jsonl:1`; evidence `logs/20261106-active-updater.log`, service properties; `logs/20261106-resource-source.log`, `wc -l`.

Systemd retains `MemoryPeak=1335037952` bytes, about 1.24 GiB, and `CPUUsageNSec=76804919000`, about 76.8 CPU-seconds, for that daily service. IO and IP accounting are disabled, so transfer volume and disk IO are unavailable. Foreground impact and installation resources remain unmeasured. Source: evidence `logs/20261106-resource-source.log`, `systemctl show os-update.service`.

Root remains XFS with 22,418,848 KiB available at inspection. The cache resolves to a separate Btrfs mount. Missing `snapper` and `timeshift` packages do not prove that no backup exists, but no restore drill was established. Source: evidence `logs/20261106-readonly.log`, `df`, `findmnt`, `readlink`, and `pacman -Q`.

Read-only syntax, native diagnostic, cadence audit, and commit whitespace checks passed. Diagnostic exit 0 still does not mean readiness. No transaction, recovery drill, update activation, or service change ran during revalidation. Sources: evidence `logs/20261106-readonly.log`; `scripts/setup-native-updates:8-14`.

The host-setup owner must reconcile the active custom implementation with the native proposal before further deployment. Kevin must confirm or replace the live maintenance window and authorize any service changes and recovery procedure. Do not treat the older inactive-timer finding as current, or activate a second updater alongside the existing one.

## What is codified

The owner asked for OS-native, low-impact updates and reboot-dependent updates immediately before scheduled maintenance. Sources: `owner-message-audit-20261104/ASK-LEDGER.md:52-56` and `owner-message-audit-20261104/REPORT.md:92`, relative to the operations directory.

The three existing untracked files were copied from `/workspace/.files` into branch `ayo/R09`, based on `bbeebf753ad745868fe9d210aebd6f6ef3f72ba0`. The two scripts are unchanged. The policy now warns that activation and recovery are unverified. Sources: execution `logs/initial-state.log`, `logs/worktree.log`, and `logs/final-state.log`.

The native proposal uses packaged offline preparation, not a new resident updater. Its setup lowers preparation priority with `Nice=19`, idle IO, `CPUWeight=10`, and `IOWeight=10`. It declares the resolved cache mount as required for offline boot. Source: `scripts/setup-native-updates:42-54`.

## Acceptance gaps

| Requirement | Current evidence | Still missing |
|---|---|---|
| Safe non-reboot updates | Policy defers the complete Arch OS transaction. | No continuously installed safe subset is implemented or proven. |
| Reboot class only at scheduled maintenance | Proposal disables the automatic reboot timer. | Preparation can arm the next user reboot, not specifically an approved window. There is no workload drain gate. |
| Rollback | Disable calls the native abort command; cache cleanup retains packaged defaults. | No tested OS rollback, restored backup, or recovery boot. |
| Resource impact | November 15 maintenance journal records 6min 29.916s CPU, 4min 43.970s wall time, 5.9G peak memory, and 103M peak swap. Source: `logs/20261115-current/boot.log:57-60`. | No transfer volume, disk IO, foreground-latency measurement, or proven resource admission for future transactions. |

Sources: `docs/native-updates.md:5-12,28-32,45-60`, `scripts/setup-native-updates:22-28,48-56`, and execution `logs/native-readonly-rerun.log`. `check` exits zero despite missing dependencies because lines 9-11 suppress individual failures. Its success is diagnostic completion, not readiness.

## Current host observations

Read-only inspection on 2026-11-05 found `pacman-offline` absent. Native and custom updater units are not found and inactive. `paccache.timer` is disabled and inactive. Root has 17 GiB free, above the script's admission floor, so the previous 9.8 GiB observation is stale. This does not establish enough space for a transaction. Source: execution `logs/host-readonly.log`, from `systemctl show`, `pacman -Q`, `findmnt`, and `df`.

Root is XFS. The package cache resolves onto a separate Btrfs mount. `snapper` and `timeshift` are not installed; their usual configuration paths and `/system-update` were absent. This narrow probe does not prove that no backups exist. It does rule out assuming a configured root Btrfs snapshot from the cache filesystem type. Source: execution `logs/host-readonly.log`.

The local cadence script still reports nine CachyOS kernel upgrade days, last upgrade 2026-10-07, median local interval 24 days. This measures local installations, not upstream release cadence. No live database refresh or upstream request was made. Source: execution `logs/native-readonly-rerun.log` and `scripts/audit-update-cadence.py:24-48`.

## Competing owner implementation

A separate owner worktree already contains commit `5e57eed4f9b6d7f5466f09c5790468dc2e62e230`, branch `fix/r09-os-update-defer-reboot-20261105`, at `/mnt/zer0models/worktrees/files-ph8-self-healing`. It was inspected, not changed or applied. Source: execution `logs/competing-owner-source.log`.

Do not deploy that implementation unchanged:

- `config/host/etc/os-update/run:25-40` classifies `checkupdates -d` output, then runs a separate `pacman -Syu --noconfirm`. The second transaction is not bound to the classified set. A repository change between those steps can introduce an unclassified reboot-dependent update. This is a source-level finding, not a reproduced production incident.
- `run:40-46` does not apply a frozen staged transaction. It refreshes again and bases its reboot decision on the earlier list. Installed `/usr/bin/checkupdates:150-155,169-173` uses a temporary database and download-only operation. Its output does not bind a later live transaction. The installed source excerpt and hash are saved in `logs/competing-owner-source.log`.
- `run:25-46` has no workload-drain check. Its maintenance timer has a placeholder Sunday 04:00 window at `config/host/etc/systemd/system/os-update-maintenance.timer:5-7`. Kevin has not chosen that window in this run.
- `docs/fleet/OS-UPDATE.md:33-37` describes disabling timers and per-package cache downgrade. Neither is evidence of a tested, consistent OS restore. Its older-kernel bootability statement was not verified here.

These references refer to the paths at commit `5e57eed4f9b6d7f5466f09c5790468dc2e62e230`. The native proposal also remains blocked: disabling automatic reboot does not enforce a scheduled maintenance window.

## Recovery and resource gates

Before any privileged transaction, the host-setup owner must identify a restorable backup for the XFS root, the separate boot and package-cache dependencies, and a usable recovery boot route. Record a successful restore drill and its exact backup identifier. Stopping preparation or aborting a pending update is cancellation, not rollback. Cache retention alone is not a restore plan. Sources: host observations above and `scripts/setup-native-updates:22-28`.

During an approved drained window, record the complete proposed transaction, available root and cache space, and the recovery point before proceeding. Capture native service exit status and journal, CPU time, peak memory, disk growth, transfer volume, and observed foreground impact. Verify boot, kernel/module consistency, and workload recovery afterward. No such drill ran here; this is the remaining evidence requirement, not an execution receipt.

The read-only check took 0.076 s and the cadence audit took 0.087 s on this run. The wrapper's cumulative child peak RSS reached 18,932 KiB. These numbers measure probes only and are not updater resource measurements. Source: execution `logs/native-readonly-rerun.log`; rerun with `python3 verify-readonly.py` from the evidence directory. All executed checks were tiny local commands; no heavy build or test suite ran.

## Required owner decisions

Kevin must supply the maintenance day, time, timezone, maximum interruption, busy-work defer policy, privileged authorization, and recovery approval. The existing host-setup owner must reconcile the two proposals before deployment. Options remain an offline full-transaction policy with no continuous non-reboot subset, or an implementation that proves a safe full transaction and binds its reboot decision to exactly that transaction. No option is activated by this review.
