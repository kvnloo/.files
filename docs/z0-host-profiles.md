# z0 host intent and read-only binding health

Owner: .files for host/harness/profile **desired intent**. z0#33 owns the
canonical component registry, native binding recipes and doctor/apply. AODL
owns native harness IDs; z0intelligence#22 owns memory/state resolution.
z0bridge owns scoped pairing/transport, kerdoios capacity/placement,
oss-factory coordination, and native harness plugins their own config seams.
A remembered or observed capability is evidence, never permission.

Tracking: [.files#40](https://github.com/kvnloo/.files/issues/40),
[.files#16](https://github.com/kvnloo/.files/issues/16),
[.files#12](https://github.com/kvnloo/.files/issues/12),
[z0#33](https://github.com/kvnloo/z0/issues/33). Registry Drafts:
[z0 PR30](https://github.com/kvnloo/z0/pull/30),
[z0 PR31](https://github.com/kvnloo/z0/pull/31),
[z0 PR32](https://github.com/kvnloo/z0/pull/32).
The TOML host-profile JSON contract is under development on z0 branch
feat/fleet-binding-health; do not treat those Drafts as merged or qualified.

## Selection contract

The existing fleet.toml hosts.<id>.z0_components TOML mapping is the z0
Intent input: an optional components array; harnesses.<id>.components;
and harnesses.hermes.profiles.<name>.components. Precedence is native
profile > harness > host. A missing selection means UNKNOWN (not a
request to bind or remove); components = [] is explicit none.
Native harness IDs are hermes, claude, codex, omp. Component IDs are
looked up by z0 from registry/components.yaml; .files does not mirror
recipes, executable commands, credentials, or service state.

Desktop host = groot or 0. Hermes clean now DESIRES
[tencentdb-memory, z0intelligence] **only in Git config**. The dated
observed clean state instead has ctx and noop with no TencentDB provider.
Those existing entries and every unrelated native setting MUST be
preserved. Hermes default and chiefstaff have the same two desired
components based on .files#12 and z0#15's observed topology; this is
not a statement about successful extraction or shared continuity.
Desktop Claude, Codex and OMP selections are explicitly empty pending
separate qualification, not an instruction to delete installed tools.

MBP and phone explicitly select no local z0 bindings: MBP's z0int timer
is not proof of qualified harness injection; the phone is an Arch PRoot
client without systemd or a local qualified memory service. Both need
independent native-harness and device identity receipts before opting in.
No automatic deployment, node reachability, or cross-device authority is
implied. The S22+ guest needs a separately verified identity, not a
second host silently inferred from a generic PRoot hostname.

**Blocked: GraphRAG.** Its installed batch tooling and incomplete
index do not supply an executable query/MCP service. Prerequisite:
finish and independently validate an index on an authorized corpus,
then expose and test a real query-capable backend/adapter (including
scope-aware retrieval) before requesting a registry binding and any
host/harness selection. No graphrag command, MCP endpoint, service, or
auto-enable is declared here. Supermemory remains credential-blocked;
the other observed/unmanaged tools remain unmanaged, not implicitly
desired. Never commit mutable memory, state.db, keys, OAuth tokens,
secrets or any private doctor receipt to Git.

## Read-only health adapter

Current dev has ./iac plan, not scripts/fleet. The latter, including
the health record under ~/.local/state/fleet/health/<node>.json, lives
on the **separate and still-Draft .files PR30** feat/k3s-cluster.
Do not copy its registry, probe, state store or cordon logic into dev.

Run ./iac plan --z0-bindings --json on the same physical/logical host
as the observed state. This adds an advisory z0_bindings dimension while
preserving existing package, systemd and timer checks unchanged.
It invokes only:

~~~sh
z0 doctor --bindings --json --host-profile <absolute-path-to-this-checkout/fleet.toml>
~~~

through a bounded (20-second) shell-free subprocess. Optional Z0_BIN
selects the installed z0 executable. A missing executable, bad JSON,
unknown/missing status, missing/unknown per-profile intent, mismatched
host identity, timeout, invalid schema or failed doctor is **unavailable**,
never healthy. Only MATCH after actual local inspection is healthy.
DRIFT means a checked config mismatch, not evidence of a running or
verified memory capability. No apply, service control, fleet cordon,
secret-bearing raw stdout/stderr, external network call, or new store.
Doctor may save its own private read-only observation receipt outside
Git; this adapter does not create a persistent record.

The status field reports MATCH, DRIFT, UNKNOWN or ERROR, with
available/healthy booleans and bounded, identifier-only configs/findings.
Unavailable/unknown overrides success; unexpected field text, native
paths and command values are not reprinted. Exit: 0 for overall MATCH,
1 for package/unit or z0 DRIFT, 2 for z0 UNKNOWN/ERROR. The underlying
IaC status remains separate in JSON; z0 cannot suppress existing
fleet/package failures.

When PR30's fleet command is integrated with dev, its owner should
consume this .files-owned projection into its **existing** node health
record, keyed via desktop→groot, mbp→mbp, phone→omarchy-phone.
Component status must remain advisory, never participate in strikes,
cordon/uncordon, pause/resume, device revival or authority decisions.
Until that integration, do not claim that scripts/fleet health displays
z0 binding drift.

## Exact OMP verification (MBP only; do not run here)

From this branch checkout, off groot:

~~~sh
git switch feat/z0-component-profiles
python3 -m pytest -q tests/test_iac_plan.py tests/test_iac_z0_health.py tests/test_iac_collect.py
python3 -m compileall -q scripts/iac/plan.py
python3 -c 'import tomllib; from pathlib import Path; tomllib.loads(Path("fleet.toml").read_text())'
./iac collect
./iac plan --z0-bindings --json
z0 doctor --bindings --json --host-profile "$PWD/fleet.toml"
~~~

The last two commands require the z0 feat/fleet-binding-health contract
on MBP. If not installed, UNKNOWN/unavailable is an expected failure
receipt, not a green gate. Do not treat unit tests or dry-run as proof
of loaded bindings, successful retrieval, or verified model use.
If OMP uses the existing **Draft PR30** fleet-build wrapper to execute
these on MBP, it must run from this branch checkout and set --src to
this branch checkout explicitly. That wrapper lives on a different
Draft branch and is NOT included here; never accidentally ship PR30's
source as this profile branch or run tests on groot.

## Owner-reviewed clean plan / apply (only on groot, later)

From the reviewed .files checkout on groot, using z0 with TOML host
profile support, capture **read-only before** first:

~~~sh
z0 doctor --bindings --json --harness hermes --harness-profile clean --host-profile "$PWD/fleet.toml"
z0 apply --dry-run --harness hermes --harness-profile clean --host-profile "$PWD/fleet.toml"
~~~

Review the masked native diff and confirm ctx/noop, unrelated server
definitions, secret reference handling, backing up and profile routing
are intact. After explicit owner approval only, the exact opt-in is:

~~~sh
z0 apply --apply --yes --harness hermes --harness-profile clean --host-profile "$PWD/fleet.toml"
z0 doctor --bindings --json --harness hermes --harness-profile clean --host-profile "$PWD/fleet.toml"
~~~

No part of this PR runs apply or touches the live clean profile.
A JSON doctor report is local evidence of configuration, not of
service state, actual injected memory or independently checked use.
OMP should put sanitized before/after outcomes, command exit codes and
exact z0/.files head SHAs into z0-01/reports/registry.md. Never
publish credentials, personal memory or full unredacted host packets.

## Next slices and file ownership

1. z0 / feat/fleet-binding-health owns TOML host-profile parsing,
   registry-ID validation and authoritative doctor --json status/config
   output; .files must not duplicate any of those registries.
2. .files fleet PR30 owner owns scripts/fleet integration of the advisory
   z0_bindings projection into existing per-node health records without
   strike/cordon changes. Explicit alias mapping only after identity check.
3. Native Hermes owner owns reviewed clean dry-run/apply and independent
   readback, preserving ctx/noop; later harness adapters own qualified
   Claude/Codex/OMP/MBP/phone bindings. z0intelligence/z0evals own
   any retrieval/use/continuity acceptance, not this host intent file.
