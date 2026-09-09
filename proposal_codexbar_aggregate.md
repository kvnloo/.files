# CodexBar provider expansion

## Root cause (corrected)

The installed binary **is** upstream CodexBar (`~/.local/lib/codexbar-cli/codexbar`), wrapped by `scripts/codexbar`.

`No available fetch strategy` for OpenRouter/Groq means **missing API keys**, not a broken binary:
- OpenRouter needs `OPENROUTER_API_KEY`
- Groq on Linux needs `GROQ_API_KEY` (browser/console auth is macOS-only)
- Grok/Codex/Claude work via OAuth/browser sessions (already working)

Crush `providers.json` stores `$OPENROUTER_API_KEY` style references, not literal keys.

## Dotfiles fix

1. `scripts/codexbar-env.sh` — loads `~/.config/codexbar/secrets.env` and resolves Crush refs
2. `scripts/codexbar` wrapper — sources env before exec
3. `scripts/codexbar-extra-providers.py` — Cerebras, Vercel AI Gateway, Nous Portal (not in upstream enum)
4. `config/waybar/scripts/codexbar.sh` — merges extra providers; writes `full.json` for Noctalia
5. `config/codexbar/secrets.env.example` — copy to `~/.config/codexbar/secrets.env`

## Fork (`packages/codexbar/`)

Upstream clone for future PR. Rebuild requires Swift (`swift-bin` AUR). Not required for runtime once secrets are set.

## Noctalia integration

`salemsayed/codexbar-meter` calls `codexbar usage --format json --json-only` directly,
which skips Linux-only provider routing. Use the aggregate shim instead:

- `scripts/codexbar-noctalia` — refreshes Waybar cache, emits `full.json`
- `[plugins.settings."salemsayed/codexbar-meter"].codexbarPath` → `~/.local/bin/codexbar-noctalia`

## User action

```bash
~/workspace/.files/scripts/codexbar-sync-credentials.sh   # creates secrets.env
# fill in API keys in ~/.config/codexbar/secrets.env, then:
~/.local/bin/codexbar-noctalia usage --format json --json-only | jq '.[].provider'
# sign into Cursor IDE for cursor usage; run `claude` for Claude OAuth
```
