# Auto-capture: keep .files in step with the live host

Status: proposal, 2026-11-01. Nothing here is installed yet.

Goal: when the owner installs or removes anything on a host, `.files` records it
without manual edits and without a cron job or polling timer.

## Measured gaps on groot (2026-11-01)

| Area | Live | In .files | Gap |
|---|---|---|---|
| pacman explicit packages | 376 (34 AUR) | `packages/packages.toml`: 165 Arch names | **240** explicit packages untracked, 23 of them AUR; 8 manifest entries not installed |
| Other package managers | flatpak 3, cargo 21 bins, uv tools 8, npm -g 7, bun 5, go 2, pipx | none | all untracked |
| Nix / Home Manager | `nix` not installed on groot | `config/nix` flake (8 packages in `home.nix`) | flake unused on this host |
| `~/.config` | 167 top-level entries | 10 linked as whole dirs, plus file links inside some dirs | 127 small (<2 MB) dirs with no link, e.g. `git` (1 of 20 files linked), `fish` (repo has `config.fish`, live file is a separate copy), `quickshell` (87 files), `atuin`, `btop`, `gtk-3.0`, `mimeapps.list`, `qt6ct`, `Kvantum`, `user-dirs.dirs` |
| `/etc` | many files | 34 `[[system]]` entries in `config/host/groot.toml` | no record of other `/etc` edits |
| Deployed checkout | links point at `/workspace/.files` | that checkout is 372 commits behind `origin/dev`, with an uncommitted Noctalia edit | the live desktop runs old config |

`scripts/host-drift` checks only what the manifest declares: 88 drift findings,
10 unknown. It cannot see a new package or a new config directory.

## Tools considered

| Tool | What it does | Fit |
|---|---|---|
| **metapac** (ripytide/metapac, GPL-3, v0.10.3 2026-10-26, 320 stars; AUR `metapac`) | Declarative group files across backends: arch (paru), flatpak, cargo, uv, npm, bun, pipx, nix, brew, mise and others. `metapac unmanaged` prints everything installed but undeclared, as a valid group file. `sync` installs; `clean` removes. | **Use it as the format and for capture.** It covers every package manager groot uses, and brew for the MBP. It has no capture-on-install mode, so we add the trigger (below). |
| pacman hooks (alpm-hooks) | Run a command after every transaction | Works, but runs as root. A user `.path` unit on the pacman database does the same job without root. |
| etckeeper (extra repo) | Git-tracks `/etc`; auto-commits from its own pacman hook | Optional local history of `/etc`. Never push it: the repo contains secrets. The curated `config/host/etc` stays the source for deliberate system files. |
| aconfmgr | Saves an Arch system diff to bash config | Overlaps with metapac and etckeeper, and saving is manual. Skip. |
| Nix + Home Manager / system-manager | Declarative; you edit the file, then switch | **Does not meet the goal.** Installing is still an edit-then-switch step. On CachyOS it also loses the v3/v4-optimised builds, needs nixGL or a system-manager shim for NVIDIA OpenGL/Vulkan, and does not own the kernel, drivers, portals or services. |
| flox / devbox global | `flox install x` edits `manifest.toml` itself | Records only what you install through flox. Possible later for portable CLI tools shared with the MBP. |

## Recommendation

1. **Keep pacman/paru as groot's package manager.** Do not move system or GUI
   packages to Nix. Nix stays optional for portable CLI tools that must match
   on the MBP.
2. **metapac group files become the per-host package record**, under
   `packages/metapac/` with `hostname_groups`:
   - `groot.captured.toml`: generated, never hand-edited.
   - Curated shared groups (`core.toml`, `desktop.toml`, ...) are split out of
     the capture by hand when useful. `packages.toml` remains the
     cross-distro install list until it is ported over.
3. **Event-driven capture with no cron and no polling.** Use systemd **user**
   `.path` units (inotify) that start `files-capture.service` when one of
   these changes:
   - `/var/lib/pacman/local` (pacman, paru, yay)
   - `/var/lib/flatpak/app`, `~/.local/share/flatpak/app`
   - `~/.cargo/.crates2.json`
   - `~/.local/share/uv/tools`
   - `~/.local/share/pipx/venvs`
   - npm global prefix `lib/node_modules`
   - `~/.bun/install/global`
   - the nix profile manifest, if Nix is used

   The service waits about 5 s so a transaction finishes, then runs
   `metapac unmanaged`, minus the curated groups, into
   `groot.captured.toml`. If that changed, it commits only that file under
   `flock .git/claude-commit.lock` with the message `capture(groot): +a -b`.
   Removals drop out because the file is regenerated, not appended. No root
   is needed.
4. **Config: report new directories, never auto-add them.** Directories such
   as `bws`, `sops`, `gh`, `openrouter`, `tailscale` and `gcloud` hold
   secrets, so copying config automatically is unsafe. A `.path` unit on
   `~/.config` adds new unclaimed entries to a `config-unclaimed` section of
   `host-drift`, so each one is triaged once. Allowlisted entries are then
   adopted as links.
5. **One deployed checkout.** Deployed links should point at one checkout
   that follows `dev`; `files-live` already exists for root apply. The
   capture service commits there. Pushing is a separate owner decision.

## Order of work (highest user-experience value first)

1. Fix the stale deployment: bring `/workspace/.files` (or `files-live`) up
   to `origin/dev`, keeping the Noctalia edit. This affects every config the
   desktop reads today.
2. Package capture: metapac, the user `.path` units, and the first
   `groot.captured.toml` commit, with the 240 pacman packages plus
   flatpak, cargo, uv, npm and bun.
3. Adopt hand-edited configs: `fish` (merge the live `config.fish`), `git`,
   `quickshell`, `atuin`, `btop`, `gtk-3.0`, `mimeapps.list`,
   `user-dirs.dirs`, `qt6ct`/`Kvantum`/`kdeglobals`, `mpv`. Link each one
   through `core-links` and add it to `groot.toml`.
4. Add `config-unclaimed` to `host-drift`.
5. Optional: etckeeper for local `/etc` history, kept unpushed.
6. Optional: the same capture on the MBP with metapac's brew backend.
