# R09 activation blockers

This review preserves the existing native-updater proposal without activating it. R09 is not complete. No package refresh, installation, timer activation, service restart, or reboot ran in this execution. Evidence directory: `/mnt/zer0models/workspace/zer0/data/operations/intent-analyzer-20261104/ayo-runs/exec-R09`.

## Latest observation, 2026-11-06 at 15:02 UTC

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
| Resource impact | Latest daily-service counters show about 1.74 GiB peak RAM and 34.9 CPU-seconds, from `logs/revalidation-latest.log:180-188`. | No installation resource measurement, transfer volume, disk IO, or foreground-latency measurement. |

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
