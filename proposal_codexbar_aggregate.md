# CodexBar provider expansion — upstream proposal

## Problem
`codexbar usage` reports `No available fetch strategy` for providers present in config (openrouter, groq) because the shipped binary does not load the upstream provider plugins.

## Fix
Forked upstream `steipete/CodexBar` into `packages/codexbar/` and added:
- `groq`
- `cerebras`
- `nous` (Nous Portal)
- `vercelai` (Vercel AI Gateway)

OpenRouter already exists upstream; rebuild with plugin loading enabled.

## Upstream next step
Open issue + PR against `steipete/CodexBar` with these plugins and the fetch-strategy loading fix.
