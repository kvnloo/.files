# Low-impact CachyOS updates

Status, rechecked 2026-11-06 at 15:02 UTC: this native proposal is not enabled or acceptance-complete. A separate custom updater already has active daily and maintenance timers. Do not enable a second updater. Its next maintenance deadline is November 8 at 04:00 CST, `America/Chicago`, with no workload-drain gate in the installed script. Read [R09 activation blockers](native-updates-review.md) before any activation. Sources: execution `logs/revalidation-latest.log:93-178,225-278` and `/etc/os-update/run:25-46`. The historical observations below are not fresh repository or upstream checks.

Use the distribution's `pacman-offline-prepare.timer` and `paccache.timer`. Do not add a resident updater, cron job, LLM call, AUR build loop, or all-package-manager background updater.

- Offline preparation downloads official repository updates daily using the packaged timer. Installation happens at the next user-initiated reboot/shutdown; do not enable `pacman-offline-reboot.timer`.
- Reboot-requiring updates must not be installed into the running system and left waiting for a reboot. Downloading ahead is fine; apply the complete OS transaction in the offline maintenance boot, immediately before returning to normal boot. Do not cherry-pick supposedly reboot-free packages from an Arch full upgrade.
- Scheduled maintenance may initiate this reboot, but only once an owner-approved maintenance window and active-work handling are defined. No recurring reboot schedule is enabled by this setup.
- A machine that never reboots will have downloaded updates, not necessarily installed ones. This policy intentionally prioritizes uninterrupted work over immediate installation.
- `paccache.timer` runs weekly and retains the packaged default of three versions. It is cache retention, not worktree cleanup.
- T3 has a separate existing daily `t3-auto-update.timer`. Do not duplicate it. Its current command (`t3 update --yes`) can restart T3; this policy does not change that.
- Provider native auto-update settings remain separate. Do not blanket-update global npm packages, editable forks, or source checkouts without checking their ownership and update mechanism.

## Cadence and maintenance policy

Checked 2026-11-04 against this host's installed packages, `/var/log/pacman.log`, sync database timestamps and https://www.kernel.org/releases.json. Repeat locally with:

    python3 /workspace/.files/scripts/audit-update-cadence.py

Findings:

- Installed CachyOS kernel: 7.2.9; fallback LTS: 6.18.55. Kernel.org currently lists 7.2.15 (2026-11-01) and 6.18.60 (2026-10-30). These are upstream releases, **not proof of current CachyOS repository availability**.
- Both kernels last upgraded locally on October 7. The median gap between nine local upgrade days is 24 days. That measures how often this host installed updates, not how often maintainers published them.
- NVIDIA userspace 615.71.09, Intel microcode 20260925, firmware 20260916, systemd 262 and glibc 2.44 are installed. Their observed local upgrade medians range from 28.5 to 71 days, also not release schedules.
- Local repository databases date to October 6–7. Do not use `pacman -Qu` against them to claim there are no updates. Do not run a bare live `pacman -Sy` to research freshness; use an isolated check database or native offline preparation.

**Selected policy: one weekly maintenance opportunity, not a mandatory weekly reboot.** This is an engineering recommendation based on kernel updates already outpacing this host's installation cadence, not a claimed exact upstream release interval. Daily low-priority native preparation provides fresher downloads; weekly maintenance bounds routine delay without daily disruption. Security advisories requiring urgent action take precedence over the routine window.

At maintenance: verify enough space and backups/recovery, review interventions and the complete proposed transaction, ensure active agent sessions, GPU jobs and cluster workloads have drained, then let the native offline update install before normal boot. If workload state cannot be verified, defer instead of terminating it. Kernel/modules, NVIDIA userspace, CPU microcode and firmware stay together with the full Arch transaction; systemd/glibc are maintenance-sensitive but do not universally mandate a hardware reboot. Never infer reboot need solely from a package name.

No automatic clock time or idle-detection service is installed: release cadence cannot tell us when Kevin's workloads are safe to interrupt. The stock reboot timer must stay disabled; a future approved maintenance trigger must enforce the drain/defer rule. This document and audit codify the policy, not a live scheduled reboot.

## Enable

Do not enable this proposal until Kevin approves a maintenance window, workload drain/defer handling, and privileged execution. Verify backup restoration and the recovery boot path first. The setup script does not enforce those approvals or test recovery.

The setup command refuses below 15 GiB available; this is a conservative admission floor, not a guarantee that any particular upgrade fits. Review root and cache space, pacman's proposed size, and Arch/CachyOS news before the initial full upgrade. These commands are for the approved drained window, not a background setup step:

    sudo pacman -Syu --needed pacman-offline
    sudo bash /workspace/.files/scripts/setup-native-updates enable

The setup starts weekly cache cleanup but only enables the native preparation timer for the next boot, avoiding an immediate overdue download. It creates small systemd drop-ins to lower download priority and mount the resolved package-cache location during offline boot (groot's cache is on a separate disk). It does not change pacman ignore lists, force dependency resolution, reboot, or start additional resident services. Offline updates still run package hooks and can fail; they are not a substitute for backups or reviewing intervention notices.

## Inspect / disable

    bash /workspace/.files/scripts/setup-native-updates check
    systemctl list-timers pacman-offline-prepare.timer paccache.timer
    journalctl -u pacman-offline-prepare.service -n 40
    sudo bash /workspace/.files/scripts/setup-native-updates disable

Disable stops preparation and cancels a prepared offline update using the upstream abort command. It leaves ordinary package cache retention enabled and the harmless mount/priority drop-ins installed.

References:
- https://wiki.cachyos.org/configuration/post_install_setup/
- https://github.com/eworm-de/pacman-offline

## Initial verification

At preparation time, `pacman-offline` was not installed, `paccache.timer` was disabled, root had 9.6 GiB free, and this ACP session could not authenticate sudo. Therefore **this setup is prepared but not activated**. The existing T3 update timer was active and its most recent service result was success.
