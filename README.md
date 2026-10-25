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

`scripts/apply-agent-oom --apply` installs the content-stamped `~/.local/bin/omp`
wrapper alongside `agent-launch`. The wrapper runs Tern's managed
`~/.local/share/tern/omp/bin/omp` through `agent-launch omp`; no global Bun OMP
package is required. Point launchers at `~/.local/bin/omp`, not `~/.bun/bin/omp`.

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
