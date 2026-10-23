# z0 host intent and read-only fleet binding health

Tracking: [.files #40](https://github.com/kvnloo/.files/issues/40),
[.files #12](https://github.com/kvnloo/.files/issues/12),
[z0 #33](https://github.com/kvnloo/z0/issues/33), and
[z0 Draft #34](https://github.com/kvnloo/z0/pull/34).
This integration stacks on [.files Draft #46](https://github.com/kvnloo/.files/pull/46),
which preserves [.files Draft #41](https://github.com/kvnloo/.files/pull/41).
It carries the profile work from Draft #42 onto the actual fleet source, rather
than importing dev's unrelated IaC implementation or creating a second fleet CLI.

## Ownership and selection

z0 owns the canonical registry and native recipes; .files owns host intent.
AODL owns harness IDs; native harness adapters own execution and permissions.
z0intelligence #22 owns scoped memory evidence, not this host configuration.
Configured, running, injected and independently verified are different states.

`fleet.toml` declares `hosts.<id>.z0_components`: optional `components`,
`harnesses.<hermes|claude|codex|omp>.components`, and
`harnesses.hermes.profiles.<name>.components`. Native profile overrides harness,
which overrides host. Missing means UNKNOWN; `[]` means no requested components,
not permission to delete existing entries. z0 resolves component IDs and recipes.

Desktop aliases are groot/0. Hermes clean, default and chiefstaff explicitly
desire `tencentdb-memory` and `z0intelligence`. This is **Git-only desired
configuration**: clean currently has ctx/noop; those and unrelated native keys
must remain unchanged. Other Hermes profiles remain unknown. Desktop Claude,
Codex and OMP, and MBP/phone, conservatively select none pending qualification.
No cross-device activation or memory-quality claim follows from these selections.

**GraphRAG is disabled/blocked.** Its incomplete index has no finished graph or
qualified query service. `kvnloo/graphrag` owns the missing prerequisite: complete
and independently validate an authorized index, then provide a real scoped,
query-capable backend/adapter. z0intelligence #22 retains the memory evidence
contract. Neither z0 nor .files may invent `graphrag-mcp` or claim it bound.

## Read-only health interface

```sh
Z0_BIN=/path/to/reviewed/z0 ./scripts/fleet-z0-health --json --host-profile "$PWD/fleet.toml"
```

The executable shares `scripts/iac/z0_health.py` with tests. It invokes only
`z0 doctor --bindings --json --host-profile <absolute fleet.toml>` using a
shell-free, 20-second bounded subprocess. `Z0_BIN` selects the reviewed executable.
The result contains status, host_id, healthy/available, and identifier-only
configs/findings; paths, arguments, environment values and raw errors are removed.
Missing executable, invalid JSON, timeout, mismatched host and unknown desired
state are unavailable, never healthy. Exit 0 means MATCH, 1 DRIFT, 2 UNKNOWN/ERROR.
Informational unselected recipe mismatches do not become desired drift.

The existing `scripts/fleet health` consumes this advisory projection for the
local server only. It must never attribute groot's configs to remote MBP/phones,
or feed binding drift into CPU admission, strikes, cordon/uncordon, pause/resume
or device revival. Its existing health receipts carry the projection; there is
no second state store or new timer. Use `fleet health --dry-run` to inspect
without compute-health actions. Doctor may write its own private observation
receipt outside Git; no live native configuration or service is changed.

## Verification

Run checks only on MBP, from the exact branch intended for review:

```sh
flock -s /tmp/mbp-quiet.lock /home/kvn/.local/bin/fleet-build \
  --node mbp --mem 512M --cpus 1 --wait 1800 --src "$PWD" -- \
  bash -lc 'python3 -m venv /tmp/z0-profiles-check && /tmp/z0-profiles-check/bin/pip install pytest PyYAML && /tmp/z0-profiles-check/bin/python -m pytest -q tests/'
```

A missing installed z0 is a useful unavailable-path receipt, not an integration
PASS. Unit tests and dry-run do not establish retrieval quality or model use.

## Exact owner-reviewed clean apply (groot only, later)

Use the reviewed z0 #34 checkout and this .files checkout. `Z0INT_PYTHON` must
name an interpreter that can import `z0int.intelligence_mcp`; its package/runtime
and MCP handshake are a separate native-adapter prerequisite. Review the masked
plan and selected profile before explicitly opting in. No command below has
been applied by this PR.

```sh
export Z0INT_PYTHON=/path/to/verified/z0int-python
Z0=/path/to/reviewed/z0
FLEET=/path/to/reviewed/.files/fleet.toml
"$Z0" doctor --bindings --json --harness hermes --harness-profile clean --host-profile "$FLEET"
"$Z0" apply --dry-run --harness hermes --harness-profile clean --host-profile "$FLEET"
# Kevin only, after reviewing that exact diff:
"$Z0" apply --apply --yes --harness hermes --harness-profile clean --host-profile "$FLEET"
"$Z0" doctor --bindings --json --harness hermes --harness-profile clean --host-profile "$FLEET"
```

Apply owns only selected component entries and memory.provider, preserves
ctx/noop/unmanaged keys, and backs up existing files. Keep credentials, mutable
memory and raw host receipts out of Git. Sanitized exact-head MBP checks and
groot before/after observations belong in `z0-01/reports/registry.md`. The
post-code doctor may still report live drift: no live clean mutation is allowed.
