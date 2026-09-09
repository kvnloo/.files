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

## User action

```bash
cp ~/workspace/.files/config/codexbar/secrets.env.example ~/.config/codexbar/secrets.env
# fill in keys, then:
~/.config/waybar/scripts/codexbar.sh >/dev/null
```
