# Burn-pace admission reference

`burn-pace admit <lane>` returns `allow` or `deny` with a reason. Exit codes are
0 for allow, 1 for deny, and 2 for invalid CLI arguments. `--json` emits
`{"lane": "...", "decision": "allow|deny", "reason": "..."}`.
`--state-dir PATH` selects a cache directory instead of
`~/.z0int/state/posture`.

The Python function is `admit(lane, rows=None, *, now=None, state=None)` in
`scripts/burn-pace`. Without `rows`, each call reads current caches. `rows`
accepts a snapshot with `at`, `lanes`, optional `probe_errors`, and optional
`z0_factory`. `now` accepts a timezone-aware datetime for deterministic checks.
The returned dictionary has the same shape as CLI JSON.

## Inputs and policy

Admission reads only these files. It never invokes the regular refresh command,
CodexBar, OAuth, inference, a phone, or a credential store. It writes nothing.
The existing `burn-pace --json` refresh behavior is unchanged.

- `burn-pace.jsonl`: latest complete row, including paid pacing and the factory
  avoid list. The reader examines at most the final 64 KiB, ignores an unfinished
  append, and denies if the latest complete row is corrupt.
- `codexbar-fresh.json`: cached paid usage, joined by exact provider name.
- `claude2-headers.json` and `claude3-headers.json`: cached extra-subscription
  usage when the corresponding pacing lane exists.
- Optional `admission-rows.json`: free-model and app observations, in the shape
  below. Duplicate lanes and attempts to replace the paid subscriptions deny.

A timestamp more than 900 seconds old, a future timestamp, missing quota,
invalid numbers, historical provenance, or a passed reset denies admission.
A passed reset requires a new observation, not an assumed replenishment.
Timestamps must include a timezone. Both paid usage and pacing must be fresh.
All reported paid primary, secondary, tertiary, and extra windows bind. An
exhausted window denies even when pacing calls it `unknown`. Missing optional
paid windows such as Codex's null primary are not fabricated.

`hard-throttle`, `hold`, `blocked`, unknown pacing, zero workflow agents, and a
factory avoid entry deny. `throttle` allows a single admission check while
retaining the existing worker cap. Explicit provider blocking also denies.
Free-model and app rows require positive remaining capacity in every supplied
window. Exact lane identifiers keep app, API, and individual subscriptions
separate. There are no aliases, fallback routes, or inferred unlimited lanes.

This is an advisory check, not a reservation or a dispatcher. It neither
consumes counters nor prevents concurrent callers from seeing the same balance.
A sender must update its existing accounting after use and reserve estimated
tokens separately when request size matters. An `allow` result proves only the
reported windows have capacity, not that unobserved dimensions are unlimited.

## Free-model and app row shape

This is a synthetic schema example, not a measured ChatGPT entitlement:

```json
{
  "at": "2026-11-05T06:00:00Z",
  "lanes": {
    "chatgpt-app": {
      "source": "account_observed",
      "windows": [
        {
          "name": "messages/hour",
          "limit": 10,
          "remaining": 2,
          "resets_at": "2026-11-05T07:00:00Z"
        }
      ]
    }
  }
}
```

Rows may specify their own `observed_at`; otherwise the file's `at` applies.
Accepted sources are `provider_header`, `account_observed`, and
`locally_reconstructed`, matching the local quota catalog's provenance names.
Each cap window supplies a name, numeric limit, remaining balance in the same
unit, and an absolute reset timestamp. Unknown numeric values deny. Minute,
daily, monthly, and app-send windows remain separate entries. Example exact
lane names are `opencode/deepseek-v4.1-flash-free`, `groq/<model>`,
`chatgpt-app`, and `deepseek-app`.

No live free-model or app-cap producer is installed by this change. Those lanes
deny until their owner supplies current observations. The offline catalog is
historical evidence, not live remaining capacity. Static limits alone do not
establish a current balance, especially for rotating OpenCode free models.

Local policy references inspected for this change:

- `/mnt/zer0models/workspace/zer0/data/operations/rate-limits/README.md:117-123`,
  historical remaining balances are not live admission authority.
- `/home/kvn/.hermes/profiles/clean/skills/research/offline-rate-limit-catalog/SKILL.md:31-33`,
  window provenance, unknown limits, and shared account budgets.
- The same skill's `references/free-tier-providers.md:34-53`, provider and
  harness-specific free-tier restrictions, including unknown stable Zen caps.

## Focused checks

```sh
python3 -B -m unittest discover -s tests -p 'test_burn_pace*.py' -v
python3 -B scripts/burn-pace admit claude2 --json
```

The tests use temporary directories, fake CodexBar output, and synthetic quota
rows. They never invoke a live provider or change the owner's caches. The second
command reads real caches and may allow or deny depending on their current age,
quota, and pace.
