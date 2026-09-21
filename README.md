# .files

Personal Linux/macOS dotfiles and fleet IaC for Hyprland, shells, audio DSP,
agent tooling, Hermes experiments, and related workstation helpers.

## Setup

Both setup paths call the same modules. Full details: **[docs/SETUP.md](docs/SETUP.md)**.

### LLM harness

Open this repo in Cursor, Claude Code, Codex, OpenCode, Hermes, or similar.
Agents read [`AGENTS.md`](AGENTS.md), run:

```sh
./scripts/onboard status --json
```

and ask before changing the machine.

### Terminal installer

```sh
git clone https://github.com/kvnloo/.files.git ~/workspace/.files
cd ~/workspace/.files
git switch dev
./install
```

The active machine configuration currently lives on `dev`; see issue #18 for
making the default GitHub branch match this disaster-recovery source of truth.

Useful commands:

```sh
./scripts/onboard status --json
./scripts/onboard doctor
./iac collect
./iac plan
```

## Fleet IaC

`.files` describes a fleet of hosts. One computer is a **host**; Kubernetes
clusters/workloads are a separate layer that can run on one or more hosts.

See **[docs/iac.md](docs/iac.md)** for ownership and design rules and
**[docs/iac-rollout.md](docs/iac-rollout.md)** before merging repository path
moves into a live symlinked checkout.

## What this repo configures

- **Desktop**: Hyprland, Noctalia, Waybar, Rofi, Sunshine helpers
- **Shell / editors**: zsh, fish, tmux, nvim
- **Audio**: PipeWire headphone DSP + optional Aural Evolution chain
- **Agents**: shared skills, Agent Reach, mcporter, Hermes helpers
- **Fleet**: package/service intent, host identity, restore/transition metadata
- **Optional**: Tailscale SSH, Nix Home Manager, local Kubernetes lab

## Safety notes

- Sunshine credentials/state/logs stay outside Git.
- Agent Reach state stays outside Git.
- Onboarding and IaC observed state live under `~/.local/state/dotfiles/`.
- Secret manifests contain references only, never credential values.
- Normal IaC convergence must never execute destructive transitions.

## Legacy / transitions

- Day-to-day onboarding: `./install` or the harness flow
- Canonical transition history: [`transitions/`](transitions/)
- The root `migration` path is a compatibility symlink during rollout.
- Older `script.sh` forwards to `./install`.

## License

MIT. See [LICENSE](LICENSE).

Third-party trees under `config/`, `.zsh/`, and similar keep their own licenses.
Upstream audio assets remain under their respective terms.
