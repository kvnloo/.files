# Agent onboarding for .files

This repository supports **two setup methods**. Prefer whichever the user is already in:

1. **LLM harness (you)** — interactive setup through chat
2. **Terminal installer** — `./install` (menu-driven)

## First contact (required)

When this repo is opened or the user asks about setup/install/onboarding, run:

```sh
./scripts/onboard status --json
```

If `offer_onboarding` is `true` (or `recommended_complete` is `false`):

1. Tell the user you detected this machine still needs .files onboarding.
2. Ask clearly: **Want to run onboarding setup now?**
3. Only proceed after an explicit yes.
4. Walk modules one at a time with short confirmations. Prefer:

```sh
./scripts/onboard run core-links
./scripts/onboard run agent-skills
./scripts/onboard run agent-tools      # optional research tools
./scripts/onboard run tailnet-ssh      # optional Linux remote access
./scripts/onboard run nix-home         # optional CachyOS/Arch Home Manager
./scripts/onboard run audio-evolution  # optional PipeWire DSP
```

Or hand off to the TTY installer if the user prefers a classic menu:

```sh
./install
```

If onboarding is already complete (`offer_onboarding: false`), do not re-offer unless the user asks. Module statuses may show `done-inferred` when symlinks already point at this repo from a prior install. Point them to `./scripts/onboard doctor` or optional modules instead.

## Harness detection

```sh
./scripts/onboard detect-harness
```

Supported labels include `cursor`, `claude`, `codex`, `opencode`, `gemini`, `omp`, `hermes`, `kimi`, `grok`, or `unknown`. Behavior is the same for every harness: status → ask → guided module runs.

## Safety rules for public clones

- Never commit Sunshine credentials, Tailscale auth keys, API tokens, or `~/.agent-reach` state.
- Prefer the tracked helpers under `scripts/` and `config/`; do not invent new absolute secrets paths.
- Sunshine runtime secrets live only in `~/.config/sunshine/` (not in this git tree).
- When unsure, run `./scripts/onboard doctor` and report findings before changing system files.

## Canonical docs

- [docs/SETUP.md](docs/SETUP.md) — full setup guide (both methods)
- [README.md](README.md) — short entry point
- [config/nix/README.md](config/nix/README.md) — Home Manager on CachyOS

## What “recommended setup” means

Minimum useful desktop/agent baseline:

| Module | Purpose |
|--------|---------|
| `core-links` | Symlink shell, tmux, git, Hyprland, nvim, noctalia, Waybar, PipeWire fragments, Sunshine config (no credentials), helpers |
| `agent-skills` | Install `workspace-copilot` into Claude/Codex/OpenCode/Gemini/Cursor skill dirs |

Everything else is optional and should be confirmed with the user.
