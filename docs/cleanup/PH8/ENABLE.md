# Enable the PH8 disk detector after review

Nothing was installed, linked, enabled, or restarted by PH8. The candidate is on local branch `ayo/PH8` in `/mnt/zer0models/worktrees/files-ayo-PH8`, based on owner HEAD `bbeebf753ad745868fe9d210aebd6f6ef3f72ba0`. The owner checkout remains dirty and untouched.

Do not enable this timer until the focused fleet tests have run successfully. Both attempted phone guest routes currently reject admission because the Omalauncher Linux service is missing. Native ADB probes work, but that is a different route.

## Review the exact files

- `scripts/host-cleanup-pressure.py`
- `tests/test_host_cleanup_pressure.py`
- `config/systemd/user/host-cleanup-pressure.service`
- `config/systemd/user/host-cleanup-pressure.timer`

The service is groot-only. Its optional repair is one offline uv-cache prune with a 20-second limit, only on a pressured measured device. It will not prune anything resolved under `/mnt/zer0models`. It never cleans phone data, touches MBP fleet state, restarts services, reconfigures ADB, launches apps, or sends phone input.

## Unblock verification without device side effects

Do not rerun the current phone `fleet-build` commands unchanged. The deployed `fleet-adb.probe()` calls `restore_guest()` when the Linux service is absent. PH8 stopped both waiting attempts with signal 15 after finding that behavior. The pre-action retry markers were absent in `logs/fleet-safety-audit.log`, but this is not an input-free admission route by contract.

Have the existing fleet owner provide an admission path with no automatic app recovery, or another authorized compute destination. Do not restart a phone service, use phone UI input, route tests to groot, or touch excluded MBP fleet state. Once a safe route exists, run through `fleet-build`, with `--wait 1800` on admission hold. The exact payload is:

```sh
python3 -m unittest discover -s tests -p test_host_cleanup_pressure.py -v
```

Select only `scripts/host-cleanup-pressure.py` and `tests/test_host_cleanup_pressure.py` for the source payload. This uses the standard library and needs no package installation or credentials. Then check unit syntax locally:

```sh
systemd-analyze --user verify --man=no \
  config/systemd/user/host-cleanup-pressure.service \
  config/systemd/user/host-cleanup-pressure.timer
```

## Install through the existing release owner

Have the owner of the current content-stamped `.files` release install the reviewed script as `~/.local/lib/host-cleanup-pressure/host-cleanup-pressure.py` and the two units in `~/.config/systemd/user`. Do not repoint current release links at this old-HEAD worktree. Preserve existing unit files and use the existing deployment lock and link verification workflow from `root-pressure-safe-cleanup/SKILL.md:16`.

For report-only operation, remove `--repair-uv` from the staged service before installation. Keeping the flag enables only the bounded uv policy described above. Both choices retain phone measurements and receipts.

Only after an authorized install and test pass, run:

```sh
systemctl --user daemon-reload
systemctl --user enable --now host-cleanup-pressure.timer
systemctl --user show host-cleanup-pressure.timer -p LoadState -p ActiveState -p UnitFileState
journalctl --user -u host-cleanup-pressure.service --no-pager -n 30
```

These are future operator commands, not PH8 execution evidence. Starting the timer does not restart shared services. The service writes private per-run JSONL receipts under `~/.local/state/host-cleanup-pressure/`. Exit 0 means all measured reserves passed. Exit 1 means pressure, unknown measurements, or a failed/unknown repair remains. Exit 75 means another invocation owns the lock. No automatic retry occurs inside a tick. Timeout does not prove that uv made no changes.

## Undo the added timer only

After deployment, the release owner can disable this new timer with `systemctl --user disable --now host-cleanup-pressure.timer`. Do not disable any existing fleet, memory, retention, or ADB timer. Preserve receipts. Do not delete a live script or unit file outside the release workflow.

Sources: `FAILURE-CLASSES.md`, `logs/verification.log`, `logs/tests-fleet.log`, `logs/tests-fleet-s22.log`, and `logs/candidate-sizes-policy.log` in the PH8 operation folder. The unit check passed with an unrelated pre-existing `CPUAccounting=` warning. A unit-file check does not prove a deployed service works.
