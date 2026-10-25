# .files

[![Website](https://img.shields.io/badge/site-kvnloo.github.io%2F.files-0f172a?style=flat-square)](https://kvnloo.github.io/.files/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

Personal Linux/macOS **agent-native** dotfiles for Hyprland, tmux, shells, audio DSP, agent tooling, and related desktop helpers.

**Author:** Kevin Rajan ([kvnloo](https://github.com/kvnloo)) · Contact: [dev@ek.vin](mailto:dev@ek.vin)

Showcase site: **[https://kvnloo.github.io/.files/](https://kvnloo.github.io/.files/)**

## Setup (two methods)

Both paths use the same modules. Full details: **[docs/SETUP.md](docs/SETUP.md)**.

### 1. LLM harness (interactive through chat)

Open this repo in Cursor, Claude Code, Codex, OpenCode, or similar. Agents read
[`AGENTS.md`](AGENTS.md) / [`CLAUDE.md`](CLAUDE.md), run
`./scripts/onboard status --json`, and ask:

> Want to run onboarding setup?

Say yes and walk the modules in chat, or ask the agent to launch the TTY installer.

### 2. Interactive installer (terminal)

```sh
git clone https://github.com/kvnloo/.files.git ~/workspace/.files
cd ~/workspace/.files
./install
```

Useful commands:

```sh
./scripts/onboard status --json
./scripts/onboard doctor
./scripts/onboard list-modules
./scripts/onboard install --module core-links --module fonts --module agent-skills --yes
```

## OMP executable ownership

`scripts/apply-agent-oom --apply` installs one content-stamped wrapper at both
`~/.local/bin/omp` and Tern's legacy absolute
`~/.local/share/tern/omp/bin/omp`. Thus previously recorded Tern `--restore`
commands also enter `agent-launch omp`, not just new shell starts. The payload is
checksum-verified against Tern's installed state and copied into an immutable
SHA-256 release; `~/.local/lib/files-tern-omp/current` selects it atomically.
On groot the payload bytes live under `/mnt/zer0models/releases/files-tern-omp`.
No running executable inode, daemon, pane or desktop is changed or restarted.

**Update ownership changes explicitly:** .files owns the live OMP entry points.
The installer sets the supported Tern `agent_command` to `~/.local/bin/omp` and
the live OMP manager state to `managed=false`. Tern's own application updates are
unchanged. Do not let its OMP updater replace the live legacy entry.

To upgrade OMP, use Tern's supported OMP download/update UI in a **separate**
`TERN_CONFIG_DIR` staging profile, then import that profile:

```sh
# Open a separate Tern profile, never restart the live session daemon.
# Exclude live OMP wrappers from manager discovery in this staging process.
PATH=/usr/bin:/bin TERN_CONFIG_DIR="$HOME/.local/state/tern-omp-staging" \
  TERN_DAEMON_SOCKET="$HOME/.local/state/tern-omp-staging.sock" \
  "$HOME/.local/bin/tern"
# In that profile use the default omp agent command and accept its OMP update.
# Publish only its verified immutable version; never copy staging bin/omp live.
install-tern-omp --apply --from-tern "$HOME/.local/state/tern-omp-staging"
```

The import takes an installer lock and Tern's manager check lock, verifies the
advertised SHA-256, stages the payload, and atomically switches the payload
pointer while both live entries remain wrappers. Re-run this import after each
staging-profile update. Checksum failure leaves live entries unchanged.
`install-tern-omp --rollback` restores the exact entry points, settings, manager
state and payload pointer saved by the last successful import. Rollback never
writes through an executable symlink. The host-drift manifest checks both entry
points and the installer against their content-stamped .files sources.

## Scoped Bitwarden credentials

`scripts/install-bws-secrets --apply --migrate-env` installs content-stamped
launchers and service drop-ins from `config/bws-consumers.json`. The manifest
contains names only. `bws-env-exec` reuses the Hermes GNOME Keyring bootstrap,
fetches BWS values through captured pipes (never process arguments), and injects
only the selected consumer's allowlist. Direct Hermes entrypoints and pane
launches share the same per-profile scope. Native OMP keeps its own private
login store; it does not need the redundant TypeSafe environment variable.

`bws-secrets-sync.service` now writes only mode-0600 consumer environment files
under the mode-0700 `$XDG_RUNTIME_DIR/bws-secrets/`, not persistent config or
dotenv files. A consumer service requires a successful refresh before startup.
The installer verifies exact vault equality before removing mapped dotenv
entries, preserves other lines, and keeps mode-0600 **secret-containing** backups
under `~/.local/state/secret-migration/`. Only the owner may authorize deleting
those backups. Existing agents and desktop processes are not restarted.

CodexBar loads its runtime scope before native subscription-login fallbacks.
The old dotenv/config-writing synchronizer and plaintext template are removed;
verified legacy OMP-agent and CodexBar dotenv copies are retired during cutover.

Profiles migrated to the explicit allowlist stop using Hermes' bulk-project
source, so unrelated vault credentials are not injected. Bootstrap access
tokens belong in the existing keyring, not dotenv files. Missing vault access
fails closed; run `~/.hermes/bin/hermes-store-bws-token.sh` to restore the
machine-account token. Do not paste credentials into a command or a ticket.

`scripts/install-bws-secrets --render UNIT` prints the exact generated drop-in
using only the tracked consumer map. It performs no vault or network access
and emits no credential values. The host manifest records these drop-ins as
`install = "generated"` with that command as their reproducible generator.

## Agent state packet freshness

`scripts/install-state-packet-timer.sh --activate` installs content-stamped user
units and enables `z0-state-packet.timer` on a persistent 15-minute calendar.
The oneshot service calls `~/.local/lib/z0-state-packet/current/bin/generate-packet`,
which must first be installed from the z0intelligence startup-packet feature.
It publishes `~/.local/state/z0int/STATE-PACKET.md` atomically.
OMP, Hermes and Claude Code replace packets older than two hours with a
one-line stale warning. Unit replacements have backups under
`~/.local/state/z0int/startup-packet-unit-backups/`.

Socket-activated memory MCP instances use a pinned source release and
`CollectMode=inactive-or-failed`; client disconnects are handled by the server,
not hidden with a successful-exit-status override. Telemetry snapshot scratch
is `/mnt/zer0models/tmp/agent-telemetry-refresh`, on the same Btrfs filesystem as
the large OpenCode database so reflink snapshots do not become full cross-volume
copies. New artifact controller releases live under
`/mnt/zer0models/releases/artifact-leases/<commit>` with home-directory aliases;
existing running releases are not moved.

## What this repo configures

- **Desktop**: Hyprland, Noctalia, Waybar, Rofi, phone display via Sunshine
- **Shell / editors**: zsh, fish, tmux, nvim
- **Audio**: PipeWire headphone DSP + optional Aural Evolution chain
- **Agents**: shared skills, Agent Reach, mcporter MCP config, workspace-copilot
- **Optional**: Tailscale SSH, Nix Home Manager on CachyOS (`config/nix/`)

## Safety notes (public repo)

This tree is public. Treat anything that can authenticate as **out of band**:

| Keep local (not tracked) | Where it lives |
|--------------------------|----------------|
| Sunshine credentials / state / logs | `~/.config/sunshine/` |
| Agent Reach state | `~/.agent-reach` |
| Onboarding state | `~/.local/state/dotfiles/onboard.json` |
| dotenvx private keys / secrets | `secrets/.env.keys` (gitignored) |

- Tracked Sunshine files are **config only** (`sunshine.conf`, `apps.json`) — no credentials.
- Do not commit Tailscale auth keys, provider API tokens, SSH private keys, or shell history.
- `scripts/with-secrets` loads local dotenvx material; keys never ship in git.
- See [AGENTS.md](AGENTS.md) safety rules for agent harnesses cloning this repo.

## Python tests

Use a fresh virtual environment and install `requirements-test.txt`.
Run `python -m pytest tests -q` for the clean-runner suite.
The dependency list includes NumPy for the next-action reranker.
The runner also needs Bash, Git, and the Lua compiler (`luac`) on `PATH`.

Tests with the `live_system` marker check a deployed desktop, installed tools,
or real provider accounts. The default suite deselects these checks.
Run `python -m pytest tests -q --run-live-system -m live_system` on the
configured operator machine to run those checks explicitly.
Do not copy account credentials or desktop state into a CI runner.

## License

[MIT](LICENSE) © Kevin Rajan (kvnloo)
