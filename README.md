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

## Agent state packet freshness

`scripts/install-state-packet-timer.sh --activate` installs content-stamped user
units and enables `z0-state-packet.timer` on a persistent 15-minute calendar.
The oneshot service calls `~/.local/lib/z0-state-packet/current/bin/generate-packet`,
which must first be installed from the z0intelligence startup-packet feature.
It publishes `~/.local/state/z0int/STATE-PACKET.md` atomically.
OMP, Hermes and Claude Code replace packets older than two hours with a
one-line stale warning. Unit replacements have backups under
`~/.local/state/z0int/startup-packet-unit-backups/`.

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
