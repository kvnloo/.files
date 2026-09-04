# .files

Personal Linux/macOS dotfiles for Hyprland, tmux, shells, audio DSP, agent tooling, and related desktop helpers.

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

- Sunshine **credentials / state / logs** stay in `~/.config/sunshine` and are not tracked.
- Agent Reach state lives in `~/.agent-reach` (not tracked).
- Onboarding state lives in `~/.local/state/dotfiles/onboard.json` (not tracked).

## Legacy / deep migration

- Day-to-day onboarding: `./install` or harness flow above
- One-shot CachyOS rebuild scripts: [`migration/`](migration/)
- Older `script.sh` now forwards to `./install`

## License

MIT. See [LICENSE](LICENSE).

Third-party trees under `config/`, `.zsh/`, and similar keep their own licenses.
Upstream audio assets (AutoEQ measurements, BRIRs, LV2/LADSPA plugins) remain
under their respective terms; this grant covers this repository's code and
configuration only.
