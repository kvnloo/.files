# Portable Hermes bootstrap

This directory is the public, privacy-filtered portion of Kevin's Hermes setup.
It is deliberately **not** a copy of a live Hermes profile.

## Install

From the dotfiles repository:

```bash
./scripts/onboard run hermes-portable --yes
```

The module:

1. symlinks this sanitized bundle to `~/.config/hermes-portable/kvnloo`;
2. imports `skills.snapshot.json` through Hermes's native `hermes skills snapshot import` command;
3. records completion in the dotfiles onboarding state.

Hermes itself must already be installed. Provider login and any credential entry remain separate, human-controlled steps.

## Included

- a native Hermes skill snapshot containing only reinstallable public sources;
- a conservative list of portable configuration domains;
- public tool, skill, and plugin provenance names;
- service-path placeholders rather than host paths;
- theme names.

## Never included or symlinked

- `.env`;
- `auth.json` or OAuth/API credentials;
- `state.db`, session transcripts, logs, cache, or memory;
- Telegram/Discord chat IDs;
- local profile directories;
- private/local-only skills or plugins;
- absolute paths identifying Kevin's machines.

The live Hermes profile must not be symlinked into this repository. Regenerate only through `scripts/export-hermes-portable`, whose writer validates every artifact before persisting any of them.

## Remaining portability layers

Hermes natively supports plugin packs (`hermes plugins pack export/install`). The current Chief-of-Staff profile has no publicly reinstallable enabled plugins, so this bundle intentionally does not publish an empty or misleading pack. Non-secret config values should be added one explicit `hermes config get/set` key at a time after privacy review; credentials are never part of this flow.
