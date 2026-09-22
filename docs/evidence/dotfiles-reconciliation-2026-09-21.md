# Dotfiles reconciliation, 2026-09-21

Sanitized record of how the live workstation and GitHub `dev` were brought back together. Full symlink dumps, process tables, and generated rollout scripts stayed in local `/tmp` reports and were not committed.

## Divergence

Live `dev` and GitHub `dev` diverged after `2116685b5083a3ab4466a70ae1830f752beef40a`.

- Live side at reconciliation start: `1346c94a512046f897d973d9d239b0148fd054cd` (32 commits).
- Remote side: `9f9aa24f053d235da4c3c4fd9894184a898a3a78` (18 commits).
- `git cherry` treated every commit on both sides as patch-unique. Final-file comparison showed the CodexBar implementation was already present on the live tree.

## Link baseline

67 `$HOME` symlinks resolved into `/workspace/.files`. 49 more symlinks lived inside the repo. 0 were dangling.

One process held a live script open: `browser-bypass-dsp.service` runs `/workspace/.files/config/pipewire/browser-bypass-dsp.sh`. `~/.config/hypr/hyprland.conf` points at `config/hyprland/hyprland.legacy.conf`, which existed on live `dev` and was missing from the older PR branch because that file was added after the branches split.

## Scanner bug

The first IaC scanner resolved a symlink before applying the repo exclude, so every external link into `.files` looked internal and was dropped. It reported zero links. The fix compares the symlink's own path and does not follow it. After the fix, a home scan matched the independent count: 67 external, 0 dangling.

## Contract result on the reconciled tree

Against the live worktree:

```text
67 contracts
62 SAFE
5 mode-only CHANGED
0 MISSING
0 TYPE_CHANGED
0 content-level CHANGED
```

The five mode-only files (`hypridle.conf`, `hyprlock.conf`, `pipewire.conf`, `51-topping-dx5.conf`, `headphone-switch.sh`) have identical bytes. The live worktree has group-write bits that a fresh checkout does not.

IaC safety suite: 20 passed. Four CodexBar tests that invoke the installed `codexbar` wrapper fail on this Linux host because that wrapper cannot serve those providers here. They do not change configuration.

## What was merged

PR #21, `iac: reconcile live dev and add symlink-safe fleet state`, merged with a normal merge commit.

- Recovery anchor, still on the remote: `archive/live-dev-2026-09-21` → `1346c94a512046f897d973d9d239b0148fd054cd`.
- Ancestry-only reconciliation commit: `53ad68f435eb15a97f684b3d762cd38394c378e1`, parents `abec26d7b173c230fb42cf4252e110386edc51a6` and `9f9aa24f053d235da4c3c4fd9894184a898a3a78`, tree `d01bb7f2c0b5b5365c5280233ea7ae1264879569`.
- GitHub merge commit / current `dev`: `761a9c9da275eb5dea1291464110e3e55e36f922`, same tree.
- PR #20 was closed as superseded. Its branch `iac/fleet-future-state` remains at `89ae0036d3125ae027042af829cf1ea11ad5a6f3`.
- The local hardening commit `6b594f1760c3a02bea7f3191b5bc4f9021a46e3e` is kept by the local branch `iac/fleet-future-state-hardened`. It is not an ancestor of `dev` and has no remote ref. Its useful changes were transplanted onto `dev` as `2e6d7886e2bc90e01c43d225c5a673b472c84b40`.

## Migrations intentionally not applied

```text
migration                    BLOCKED
POLYBAR_PYWAL_USAGE.md       DEFER
claudedocs                   DEFER
proposal_codexbar_aggregate  NOT_PRESENT
```

Those three existing paths are still real directories or files, not compatibility symlinks. The proposal file was not added.

## Desired-state review, not done here

`iac plan` without a collected snapshot fails because `~/.local/state/dotfiles/iac/groot/observed.json` does not exist. Planning from a one-off collect reported 29 desired packages missing, `hermes-gateway.service` not enabled, and `bws-secrets-sync.timer` not enabled. That is `DESIRED_STATE_REVIEW_REQUIRED`. Nothing was installed or enabled.

`nvibrant.service` was already `failed` before this cleanup and was not restarted.

Untracked `/workspace/.files/.artifacts/` was left in place.
