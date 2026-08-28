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
./scripts/onboard install --module core-links --module agent-skills --yes
```

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

## License

[MIT](LICENSE) © Kevin Rajan (kvnloo)

## Legacy / deep migration

- Day-to-day onboarding: `./install` or harness flow above
- One-shot CachyOS rebuild scripts: [`migration/`](migration/)
- Older `script.sh` now forwards to `./install`
