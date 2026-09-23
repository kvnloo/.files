# Dotfiles migration, 2026-09-22

Applied from live `dev` at `0e41356`, which contains `761a9c9`. The working tree before this change was that commit plus untracked `.artifacts/`. No history was rewritten.

## Link receipt

A home scan with `./iac links scan` matched the 2026-09-21 receipt: 67 links, the same raw targets, 0 dangling, 0 missing, 0 type changes. Scanning `/etc` added permission errors on root-owned directories and no additional `.files` links. The home-only rescan after the moves was again 67 links and 0 scan errors.

`stage.py` was dry-run and not applied. It fails closed on the pre-existing `.gitconfig` → `gitconfig` mapping (`Path.lstrip("./")` strips the leading dot). Three other raw targets differ from the absolute stage path only by spelling (`/home/kvn/workspace/.files` is `/workspace/.files`; `nvibrant.service` in `default.target.wants` points at the unit symlink). Applying that plan would retarget live links, including a systemd wants link, so cutover was not run.

## Path moves

| Path | Result | Evidence |
| --- | --- | --- |
| `migration/` | Kept as a real directory | `02-deploy-dotfiles.sh` content commit `85ae09a` on 2026-09-17; newest mtime age 4.3 days. Still inside the 7-day hot window. |
| `claudedocs` | Moved to `docs/archive/claude`; old path is a relative symlink | Last content 2026-07-03 (81 days). No unit, fd, or symlink references. User systemd cwd is `/` and none of its fds point here. Byte fingerprint unchanged. |
| `POLYBAR_PYWAL_USAGE.md` | Moved to `docs/legacy/POLYBAR_PYWAL_USAGE.md`; old path is a relative symlink | mtime age 60.6 days, outside the 60-day warm window. No references. Byte fingerprint unchanged. |
| `proposal_codexbar_aggregate.md` | Not created | Still absent on this tree. |

## Cleanup

Removed regenerable or obsolete untracked state: `website/node_modules`, `website/.next`, `website/out`, `dsp-app` SvelteKit build output, `.artifacts/`, pytest/ruff/`__pycache__` caches, tmux client logs, and the February 2026 migration run logs. About 654 MiB came back on `/workspace`. UEFI captures in `logs/` stayed. `secrets/.env` and `secrets/.env.keys` stayed. `.cast-tools/` stayed because those stripped binaries have no source copy in the repo.

Nothing was restarted. `browser-bypass-dsp.service` stayed active on its existing PID. PipeWire, WirePlumber, Docker, and tailscaled stayed active. Hyprland stayed running.

`./iac plan` against a fresh collect is still `DRIFT`: 29 package names reported missing, `hermes-gateway.service` not enabled, and `bws-secrets-sync.timer` not enabled. That remains desired-state review. Nothing was installed or enabled.

## Retained top-level paths

| Path | Owner / purpose |
| --- | --- |
| `config/`, `scripts/`, `.zsh/`, `packages/`, `fleet.toml`, `iac`, `install`, `script.sh`, `restore/`, `transitions/` | Machine desired state and onboard tooling |
| `background/`, `icons/` | Desktop wallpaper and icon source |
| `docs/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `UX-README.md`, `LICENSE` | Repo documentation. `docs/archive/claude` and `docs/legacy/` hold the moved notes |
| `tests/` | IaC and desktop contract tests |
| `website/` | Showcase site source. Generated `node_modules`, `.next`, and `out` are not kept |
| `dsp-app/` | Audio helper source. Generated SvelteKit output is not kept |
| `network/` | Network helper source |
| `migration/` | One-shot CachyOS migration source. Held in place while its newest script is hot |
| `claudedocs`, `POLYBAR_PYWAL_USAGE.md` | Compatibility symlinks to the moved docs |
| `secrets/` | Local dotenvx material. Tracked `.gitkeep` only; `.env` and `.env.keys` stay gitignored |
| `logs/` | UEFI variable captures used by `scripts/uefi-hidden-settings-inspector.py` |
| `.cast-tools/` | Gitignored `doubletake` binaries with no in-repo source. Not referenced. Kept |
| `.github/`, `.gitignore`, `.gitmodules`, `.gitconfig`, `_config.yml` | Git and Pages metadata |
| `.claude/`, `.cursor/`, `.omp/`, `.superdesign/` | Tracked harness project settings |
| `worktrees/` | Empty tracked placeholder |
| `.git/` | This clone's history |
