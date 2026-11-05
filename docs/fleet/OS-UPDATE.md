# R09 groot OS updates (Kevin, 2026-11-04: G0449, G0480, G0483)

What was asked: keep the system updated around the clock using OS features or a dotfiles config script, not a cron job or an LLM call. Keep processes minimal. Hold any update that needs a reboot until right before a scheduled reboot. Base the reboot list on how often those packages update. Codify all of it in .files.

## How it works
- `os-update.timer` (system) runs daily at 03:30 with a random delay of up to 30 min; Persistent. It starts the oneshot `os-update.service`, which runs at Nice 19 with idle IO. There is no resident process.
- `/etc/os-update/run daily`:
  1. Runs `checkupdates -d`. This downloads packages into the cache through a temporary db, so the live sync db is never partly updated.
  2. If no pending package needs a reboot, it runs `pacman -Syu`.
  3. Otherwise it applies nothing and stages the whole set in `/var/lib/os-update/staged`. Arch does not support partial upgrades, so this script never holds back single packages.
- `os-update-maintenance.timer` runs `run maintenance`. It applies the staged set from the cache (already downloaded, so the window stays short) and reboots only if a package that needs one changed.
- Receipts: one JSON line per run in `/var/log/os-update.jsonl`.

## Which packages count as needing a reboot (from groot's pacman.log)
`/var/log/pacman.log` from 2026-02-15 to 2026-11-03 shows 10 upgrade days. Only one of them (10-07, 534 packages) included packages that need a reboot: linux-cachyos, intel-ucode and glibc. So in practice, each weekly maintenance run either finds nothing to do or applies one batch.

The list (`reboot_re`): `linux*`, `nvidia*`, `*-ucode`, `systemd`/`systemd-libs`, `glibc`, `mkinitcpio`, `mesa`.

On 2026-11-05 groot had 554 pending updates. Install this only after Kevin approves that first catch-up run.

## Resource impact
One oneshot run per day. The download is IO-bound at idle priority. Nothing runs between runs.

## Install (root, Kevin)
```
sudo scripts/apply-host-system --apply
sudo systemctl daemon-reload
sudo systemctl enable --now os-update.timer
# Only after choosing the window (edit OnCalendar first):
sudo systemctl enable --now os-update-maintenance.timer
```

## Rollback
```
sudo systemctl disable --now os-update.timer os-update-maintenance.timer
```
Package rollback: run `pacman -U /var/cache/pacman/pkg/<pkg>-<oldver>*.pkg.tar.zst` for each package. The cache keeps previous versions; the older kernel stays bootable through limine/mkinitcpio.
