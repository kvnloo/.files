# Worktree Runtime Architecture — Environment Subsystem Plan

Status: Draft revision 4 — adversarially validated working architecture

Owner: `.files`

Proposed skill: `worktree-env-manager`

Validation verdict: the native-first, content-addressed direction survives, but
the first implementation must be narrower than the surrounding runtime vision.
V1 is an environment resolver and launcher, not a worktree scheduler, service
orchestrator, remote executor, or universal cache. The custom realization path is
an experiment that must beat native uv/pnpm baselines without a correctness loss.

## 0. Validation Outcome

| Area | Result | Required condition |
|---|---|---|
| Objective | Pass | Optimize trustworthy feedback, not venv count |
| V1 scope | Corrected | Environment subsystem only; runtime orchestration stays separate |
| Reuse identity | Corrected | Descriptor, resolved closure, and realization remain distinct |
| Native-first strategy | Pass | uv/pnpm are measured controls, not implementation details to replace |
| Custom Python realization | Conditional | Must beat native baseline and pass source-binding fixtures |
| Node global virtual store | Conditional | Per-project compatibility and trust tests must pass |
| Unreviewed execution | Corrected | Require a real UID/container/VM boundary, not a logical namespace |
| Garbage collection | Conditional | Usage leases work; native and controller GC stay separate |
| Peer artifact sharing | Conditional | Stable digest API, least-privilege policy, and offline fallback |
| Future skill | Pass with boundary | Concise intent router over a deterministic, tested CLI |

This is architecture approval for measurement, not production-readiness approval.
No environment migration, cache pruning, global tool upgrade, or remote publication
is authorized until its rollout gate passes.

## 1. Objective

Minimize the time from assigning a task to obtaining a trustworthy result across
many products, Git worktrees, agents, and machines. Do this while bounding disk,
network, recovery, and cognitive costs and while preserving source isolation,
dependency correctness, reproducibility, and supply-chain boundaries.

Reducing the number of venv directories is a means, not the objective. The system
should make ordinary worktrees cheap, give genuine dependency experiments their
own immutable realization, reuse dependency and build artifacts by content, and
remove abandoned state safely. It must support hundreds of registered worktrees
without pretending that hundreds of expensive workloads should run at once.

V1 owns project discovery, normalized environment identities, backend selection,
dependency provisioning or native projection, first-party source binding,
verification, and process-scoped use leases. It exposes integration points to the
harness that already owns worktrees and task sessions.

V1 explicitly does **not** own Git worktree creation/removal, branch promotion,
ports, databases, process supervision, service scheduling, remote execution, or
build/test result caching. Those belong to a later `workspace-runtime` RFC and may
consume the environment subsystem's stable JSON contract.

### Optimization target

Measure the complete critical path:

```text
T_ready = source allocation
        + environment identification
        + artifact retrieval or build
        + source binding
        + required service readiness

T_feedback = T_ready + build/lint/test execution - valid result-cache hits
```

Choose an architecture by a weighted score over p50 and p95 `T_ready`, p50 and
p95 `T_feedback`, allocated disk blocks, inode count, network bytes, peak memory,
contention, recovery time, correctness failures, and operator effort. Treat a
wrong cache hit, cross-worktree source import, shared-state corruption, secret
leak, or lost work as a hard failure rather than a latency tradeoff.

## 2. Core Model

Use nine separate planes as architecture context. They may share an implementation
eventually, but their identities and lifecycles must not be conflated:

1. **Control plane** — policy, adapters, trust, leases, explanation, and GC roots.
2. **Source plane** — Git objects plus an isolated working tree and index per task.
3. **Toolchain plane** — pinned Python, Node, compilers, system libraries, and CLIs.
4. **Artifact plane** — append-only package, wheel, model, and build content stores.
5. **Environment plane** — immutable dependency closures or cheap projections.
6. **Binding plane** — the current worktree's first-party source and entry points.
7. **State plane** — task-local temp, databases, sockets, ports, logs, and secrets.
8. **Service plane** — heavy, capability-scoped runtimes shared behind narrow APIs.
9. **Result plane** — content-keyed build, lint, and test outputs and logs.

Share immutable content within a platform and trust domain. Share mutable caches
only when their concurrency and cancellation semantics are documented. Never
share task-owned mutable state.

The proposed skill is an intent and policy interface, not the stateful manager.
Deterministic identity, locking, provisioning, and cleanup belong in a CLI with
machine-readable output. Harnesses call that CLI instead of each implementing
the policy differently.

The environment subsystem directly owns only the relevant slices of the control,
toolchain, artifact, environment, and binding planes. It observes source identity
and may consume a harness task ID, but does not allocate or delete worktrees. It
does not implement the state, service, or result planes in v1.

## 3. Invariants

- Never let concurrent agents mutate the same environment.
- Never copy or merge `site-packages` between environments.
- Compose environment declarations before solving; do not implement inheritance
  by stacking arbitrary mutable `site-packages` directories at runtime.
- Never synchronize venv directories between macOS and Linux.
- Resolve environments from declared manifests and lockfiles.
- Do not let ambient package-manager environment variables alter resolution or
  installation outside the recorded descriptor/build recipe.
- Treat policy descriptors, resolved closures, and realized installations as
  separate content identities.
- Keep environment creation idempotent and protected by a build lock.
- Keep global tools out of project dependency resolution.
- Keep secrets and credentials outside Git and outside shared environments.
- Never install a worktree itself as an editable package into a shared environment.
- Never run an implicit package sync when executing from a shared environment.
- Do not delete a worktree, branch, environment, or runtime with an active lease.
- Refuse destructive cleanup when uncommitted, untracked, or unpushed work exists.
- Never treat a remote or local cache hit as valid unless all declared inputs,
  toolchain identity, platform properties, and trust namespace match.
- Never treat a same-user cache namespace or read-only mode bit as a sandbox.
- Never mutate a native package manager's internal store or index directly; use
  its supported commands and keep controller-owned GC separate.
- Quarantine a realization when an identical descriptor and closure unexpectedly
  produce different verified output in the same declared realizer context; never
  silently replace the old mapping.
- A disposable cache may be deleted at any time; anything whose deletion loses
  unique declarations, source, credentials, or user data is not a cache.

## 4. Proposed Repository Layout

```text
.files/
├── config/
│   ├── agent-skills/
│   │   └── worktree-env-manager/
│   │       ├── SKILL.md
│   │       ├── agents/openai.yaml
│   │       └── references/
│   │           ├── policy.md
│   │           ├── backends.md
│   │           └── security.md
│   └── project-env/
│       └── policy.toml
├── scripts/
│   ├── project-env
│   └── project-env-bench
├── tests/
│   └── project-env/
│       └── fixtures/
└── docs/
    └── worktree-env-manager-plan.md
```

Do not place design history, a README, or changelog inside the skill. Keep the
skill concise and load detailed policy references only when required. Keep the
CLI harness-neutral and independently testable. A skill may explain when to call
it, but must not be the only specification of its behavior.

## 5. Machine-Local Layout

Default each native artifact store and the environments projected from it to the
same filesystem so clone/reflink or hardlink mechanisms remain available. Probe
the filesystem and package manager rather than forcing one link mode globally.
Namespace data by platform, toolchain, trust, and schema before optimizing sharing.

```text
/workspace/
├── cache/
│   ├── uv/                         # native-owned
│   ├── pnpm/                       # native-owned
│   ├── wheels/
│   ├── results/
│   └── models/
├── environments/
│   ├── python/
│   │   └── <trust>/<platform>/<toolchain>/<closure-hash>/
│   ├── node/
│   │   └── <trust>/<platform>/<graph-hash>/
│   └── capsules/
│       └── <project>/<profile>/<capsule-hash>.json
├── projections/
│   └── <task-id>/
│       ├── bin/
│       ├── editor.json
│       └── binding.json
├── profiles/
│   ├── projects/
│   └── aliases/
│       └── <project>/current -> ../<generation>
├── project-env/
│   ├── metadata/
│   ├── locks/
│   └── leases/
│       └── <task-or-process-id>.json
└── runtime/                        # future harness/runtime-owned, not v1
    └── <task-id>/
```

Paths must be configurable for macOS and machines without `/workspace`.

Treat uv, pnpm, Pixi, Nix, and build-engine stores as native data planes. The
controller records their identities and ownership; it should not reimplement
their file layouts or mutate their internal indexes.

Controller-owned realizations, projections, metadata, and leases use the layout
above. Native stores remain at their own configured roots and are pruned only
through supported native interfaces.

Before a custom environment farm is accepted, benchmark these native baselines:

1. uv's current per-worktree `.venv` with its global package cache.
2. uv's preview centralized project environments after upgrading in an isolated
   experiment. The current machine has uv `0.11.7`, which does not recognize the
   feature; current uv documentation does.
3. pnpm `11.3.0` with its default virtual store and with the experimental global
   virtual store; it is currently unset on this machine.
4. Pixi features/solve-groups for projects with Python plus native dependencies.
5. A dependencies-only content-keyed Python environment selected by the proposed
   controller.

## 6. Environment Identity

Use three identities. A single recipe hash either blocks valid cross-project reuse
or hides policy and build differences inside one opaque key.

1. The **descriptor identity** is project-scoped policy and intent calculated
   before resolution. It includes the project adapter and schema, manifest and
   lock inputs, selected groups/extras, requested capability profile, index policy,
   trust domain, source-binding mode, and relevant backend/provisioner semantics.
   It also declares an environment schema and realizer compatibility ABI; a raw
   backend patch version remains provenance unless its adapter marks it incompatible.
2. The **resolved closure identity** describes the concrete third-party graph for
   one target capability set: distribution names and versions, artifact hashes and
   source origins, runtime implementation and ABI, OS/architecture/libc, and only
   the declared native/GPU capabilities that can change dependency selection. It
   also includes a build-recipe digest for source distributions: pinned build
   frontend/backend, compiler/SDK, declared flags and environment inputs, and
   network policy. Undeclared build inputs make a closure non-shareable. The closure
   excludes project ID, branch, and path when no local or path-bound input remains,
   allowing two projects with the exact same closure and trust policy to share.
3. The **realization identity** is calculated after provisioning from the exact
   interpreter, installed distribution metadata, artifact hashes, native-library
   references, entry points, bytecode policy, provisioner output manifest, and—for
   non-relocatable formats such as venvs—the final installation root.

The mapping is `descriptor -> resolved closure -> verified realization`. Reuse
requires the same closure and trust policy plus a compatible declared realizer
context. Record all three hashes and their component graph. If an unchanged closure
unexpectedly produces a different realization under the same realizer ABI,
toolchain, final root, and policy, fail closed and quarantine both for explanation;
do not silently make the new output canonical.

A venv realization identity is local verification evidence, not a portable artifact
key. Different installation roots can legitimately produce different script bytes;
cross-machine reuse stops at the closure's wheels/blobs and rebuilds the realization
at its local final path.

Represent identity as a Merkle-style descriptor graph so unchanged toolchain,
profile, and dependency subgraphs can be explained and reused. The resolved-closure
digest is the v1 directory key because it is known before installation; record the
realization digest inside its publication manifest. A backend with genuinely
relocatable outputs may instead publish by realization digest. Retain component
digests and canonical serialized descriptors in metadata.

Do not include branch name. Exclude the worktree path only when the dependency
layer contains no path-bound editable, local, or dynamically versioned input. Two
branches or projects with identical concrete third-party inputs may then select
the same immutable realization.

Do not hash all host state. Declare capability inputs that can affect resolution or
native execution, such as Python ABI, libc, CPU architecture, CUDA runtime, or GPU
driver floor. This avoids both unsafe hits and gratuitous misses.

Construct resolver and build environments from an allowlist. Capture effective uv,
pip, pnpm, compiler, and index settings from files, environment, and CLI as
non-secret descriptor inputs; reject or explain influential ambient settings that
the adapter does not model. Record credential-provider identity and index origin,
never credential values.

uv's project lockfile is universal across supported platforms. Hashing the complete
`uv.lock` bytes is a conservative v1 key: safe, but it can miss reuse when only an
irrelevant platform branch of the lock changes. A later adapter may derive a
normalized platform/profile closure from an ephemeral `uv export` or install plan,
but only after fixtures prove marker, extra, source, hash, and local-package
handling. Never commit that generated export as a second dependency authority.

For the v1 descriptor, hash exact authoritative file bytes and an ordered list of
their repository-relative paths; this is conservative and explainable. For the
closure lookup key, hash the backend/schema, selected target/profile/index/trust
inputs, and exact lock bytes—but not repository, project, branch, or file path. This
permits sharing only across byte-identical locks initially and knowingly causes
false misses for semantically identical locks. Store parsed component data for
diagnostics, but introduce semantic normalization only behind a versioned adapter
after equivalence fixtures prove it cannot create false hits. Never hash mtimes.
Record the descriptor, concrete closure, realization manifest, build provenance,
component digests, and a human-readable `why-different` explanation beside the
environment.

Proposed path example:

```text
/workspace/environments/python/trusted/linux-x86_64/cpython-3.12/a12f82c...
```

## 7. Environment Selection

Use the following decision order:

1. Respect an explicit user override only within non-overridable security policy;
   otherwise require the audited break-glass path or refuse.
2. Resolve the canonical repository, project-owned adapter, and effective policy.
3. Select the project adapter and native backend.
4. Calculate the descriptor and resolved closure identities for the current
   worktree and target platform.
5. Reuse an existing verified realization for that closure, trust policy, and
   compatible realizer context.
6. Otherwise create and verify a new immutable realization using the native
   package manager and record the mapping.
7. Mark the environment experimental when dependency inputs differ from the
   canonical branch, even though storage remains content-addressed.

Branch names such as `experiment/*`, `spike/*`, `prototype/*`, or `research/*`
should influence lifecycle and reporting, but dependency identity remains based
on actual inputs.

Do not infer compatibility merely because a branch did not edit `uv.lock`.
Recalculate the identity from the current worktree and validate that declared
manifests and lockfiles agree.

Prefer native behavior when it meets the contract. For example, pnpm's global
virtual store is explicitly designed to make repeated worktree projections cheap,
whereas uv's current centralized-project-envs preview keys environments by project
path and interpreter rather than dependency closure. The controller should enable,
observe, and explain native reuse before replacing it.

## 8. Shared Dependencies and Worktree Source

A shared environment must contain resolved third-party dependencies, not an
editable installation of project source. Editable packages and local workspace
members can embed absolute paths to one worktree and would therefore route other
agents to the wrong source tree.

“Inheritance” should mean composition of declarative profiles before resolution:

```text
project base + dev/test + voice + gpu + feature delta
             -> one solved and locked closure
             -> one immutable realization
```

This is the pattern used by Pixi features/solve-groups and Flox environment
composition. Do not treat `--system-site-packages`, arbitrary `.pth` chains, or
multiple mutable venvs on `PYTHONPATH` as a general dependency solver. Composition
must detect version conflicts before execution.

Provision Python dependencies using a project-selected strategy such as:

```bash
uv sync --locked --no-install-project
uv sync --locked --no-install-workspace
uv sync --locked --no-install-local
```

Select the least restrictive safe option for the repository. Record it as a
project adapter; do not guess when local path dependencies are present.

The custom Python experiment should also test a generated, ephemeral install
manifest rather than treating a second requirements file as authoritative:

```text
uv export --locked --format requirements.txt \
  --no-header --no-annotate <adapter-specific --no-emit-* flags>
uv venv --python <pinned-interpreter> <temporary-target>
uv pip sync --require-hashes --strict \
  --python <temporary-target-python> <generated-file>
```

Generate the file in controller-owned temporary state, retain its digest and uv
version as provenance, and delete or recreate it freely. The exact `--no-emit-*`
flags are adapter policy: `--no-emit-project`, `--no-emit-workspace`, and
`--no-emit-local` have different consequences for local package graphs and must
not be applied blindly. Keep native `uv sync --no-install-*` as the control.

Bind current worktree source at execution time through one of these modes:

1. **Module/source mode** — run from the worktree and add declared source roots
   to `PYTHONPATH`.
2. **Script mode** — invoke scripts by absolute worktree path using the shared
   dependency interpreter.
3. **Generated shim mode** — generate worktree-local entry-point wrappers that
   call the shared interpreter with the invoking worktree's source roots.
4. **Thin editable overlay mode** — generate only PEP 660 metadata and entry
   points in task-local state, with an explicit and verified reference to the
   immutable third-party layer. Treat this as experimental until import-order,
   subprocess, plugin, and console-script tests pass.
5. **Isolated fallback** — use a complete worktree environment when the project
   cannot safely separate local packages from third-party dependencies.

Module and shim modes require more than a simple import smoke test. Fixtures must
cover `importlib.metadata`, console entry points, package data, namespace packages,
pytest import modes and plugins, multiprocessing/spawn, subprocesses, and dynamic
versioning. Generated shims must be derived from canonical entry-point metadata.
Thin editable overlays remain experimental rather than a promised v1 feature.

Do not create `.venv` symlinks by default. Editors or agents may treat them as
mutable and run an implicit install. Generate explicit editor configuration or
use `project-env run`, which resolves the environment and source binding without
changing the worktree.

`project-env run` must execute the selected interpreter directly or use a
verified no-sync mode. It must never allow `uv run` to silently reconcile the
shared environment against whichever worktree invoked it.

Direct interpreter execution is the least ambiguous default. A project adapter may
use `uv run --no-sync` only after proving that uv selects the exact verified target
and cannot redirect to or reconcile another project environment.

The launcher constructs the dependency-sensitive environment explicitly: disable
user-site leakage, set the selected interpreter and source roots, redirect permitted
caches, and remove package-manager variables that could trigger mutation. Pass
application variables and secrets only according to the harness/trust policy; never
include their values in identity metadata or logs.

Resolve every imported first-party module back to the invoking worktree during a
smoke test. Validate subprocesses and console scripts too; checking only the parent
interpreter's `sys.path` is insufficient.

## 9. Immutability and Provisioning

Environment provisioning should:

1. Acquire a short-lived provisioning lock for the target closure identity.
2. Recheck whether another process completed it.
3. Reserve the final closure-keyed path with a sibling `INCOMPLETE` state record and
   never expose that path to consumers. Python venvs must normally be built at their
   final path because interpreter paths and console-script shebangs are absolute.
4. Install only the dependency layer selected by the project adapter at that path.
5. Precompile bytecode or redirect bytecode/cache writes away from the shared
   environment when required.
6. Run imports, entry-point, native-library, and source-binding smoke checks.
7. Produce a canonical installed-file/distribution inventory, component digests, an
   SBOM, and dependency provenance, excluding controller publication-state files,
   mtimes, and declared disposable caches. Hash or omit bytecode according to one
   deterministic adapter policy.
8. Compute the realization digest over that inventory, verify it, and write the
   complete manifest containing the digest and provenance.
9. Atomically rename a fully written, verified `READY` manifest into place, then
   remove `INCOMPLETE`; only a valid `READY` manifest makes the directory
   discoverable. Backends whose output is proven relocatable may use a temporary
   sibling plus atomic directory rename instead. Durability-sensitive publication
   must flush the manifest and parent directory before reporting success.
10. Make normal commands refuse package installation into the finished path.

On interruption, no consumer may attach to an environment without a valid `READY`
manifest. The next provisioner verifies and either resumes an explicitly resumable
backend or moves the incomplete path to quarantine before rebuilding at the same
final path. Never “fix” a venv by moving it and rewriting a few known shebangs.

Only the provisioner may mutate an environment. Worktree commands receive an
environment path and execute against it. Start with logical immutability enforced
by the CLI; apply filesystem read-only permissions only after compatibility tests,
because some packages incorrectly attempt to write beside their installed code.

Full content verification happens at publication, after suspected mutation, and in
sampled audits—not on every hot command. The hot path validates the authenticated
remote or controller-owned local `READY` manifest, schema, expected final root,
ownership/mode policy, and a cheap
tamper-generation record before acquiring its lease. Optional filesystem integrity
features may strengthen this later, but cannot replace isolation from hostile code.

Logical immutability protects cooperative tools, not hostile installation code.
Code running as the owning Unix user can normally change owner-write permissions
and corrupt other user-owned paths. Build unreviewed dependencies under a separate
UID, rootless container/user namespace, or disposable VM with no ambient secrets,
restricted network where feasible, and separate writable caches. It may consume
verified read-only blobs by digest; it must not share writable trusted stores.

Prefer copy-on-write clone/reflink mode when supported. Allow hardlinks only when
uv cache protections and package mutation tests prove that an environment cannot
modify cache content through a shared inode. Fall back to copies when correctness
requires it; deduplication is an optimization, not a safety boundary.

Do not put durable environment leases inside uv's cache. Current uv documentation
says `uv cache prune` removes all centralized project environments, and the feature
intentionally leaves dangling `.venv` links for later recreation. Either accept
those environments as disposable projections or keep controller-owned verified
realizations under a separately managed root.

Controller GC may remove only controller-owned realizations, projections, and
metadata. Native cache cleanup is a distinct, explicit adapter operation using the
backend's supported prune command and its own liveness semantics.

## 10. Global Tools

Manage cross-project commands through the appropriate isolated tool manager:

- Python CLI: `uv tool` or pipx.
- Cross-language CLI: Pixi global, mise, or a pinned package-manager wrapper.
- Node CLI: pnpm global tooling or a project-pinned package manager.
- System capability: OS package manager, Nix, or a declarative dev shell.
- Heavy reusable runtime: persistent service with a narrow API.

Initial candidates include Agent Reach, yt-dlp, trafilatura, ruff, black,
pre-commit, and mcporter. Each candidate still requires compatibility review;
“version-insensitive” must not mean “silently unpinned.” Store an owner, version
policy, update command, and rollback path for each global tool.

Project libraries must not import packages from global tool environments.
Model each global tool as its own pinned **tool capsule**, not as a giant global
Python or Node environment. “Version-insensitive” means the project's output does
not depend on the tool version; it does not mean unpinned or unowned.

`project-env` itself must bootstrap before any project environment exists and must
never import from one. Package it as its own pinned `uv tool`/PEX-style capsule or a
standalone binary, with an explicit update command, atomic version switch, prior-
version rollback, and a minimal recovery path that uses only the OS runtime. Its
version and adapter schema appear in every JSON response and provenance record.

## 11. Harness Integration Lifecycle

The harness remains the owner of task IDs, branches, worktree creation/removal,
processes, ports, and task-local runtime state. The environment subsystem starts at
attach/resolve and exposes hooks; it never deletes a Git worktree in v1.

### Attach and resolve

1. The harness allocates a task and worktree, then calls `project-env resolve` with
   their stable identities.
2. The resolver discovers checked-in project policy, computes the descriptor and
   closure, and returns a materialization plan without changing Git state.
3. A verified realization is selected or provisioned under a short-lived build
   lock. Unrelated read-only agent work may continue while it is created.
4. The harness stores the returned immutable identity, not a moving alias.

### Run

- Prefer `project-env run -- <command>`, which acquires a usage lease, invokes the
  exact verified interpreter or backend projection, and holds the lease for the
  child's full lifetime.
- If a harness launches outside the wrapper, it must use explicit lease/release
  calls with its session identity and guarantee release on cancellation.
- The source-binding adapter always targets the invoking worktree.
- Task databases, sockets, logs, generated files, and services remain harness-
  owned and outside a shared dependency environment.

### Review and promotion

The subsystem can compare candidate and canonical descriptors, provision the
candidate, and emit verification evidence. The user, Git workflow, or CI owns merge
approval. Updating a human-facing project alias is a separate explicit action after
canonical integration; running tasks remain pinned to their resolved path.

### Detach and collect

The harness releases its use lease before removing a worktree. Environment GC uses
active leases, pinned project generations, and explicit retention pins as roots.
Everything unreachable becomes a candidate only after the retention window. The
controller never infers liveness from access time alone and never interprets an
environment lease as authorization to discard source or task state.

## 12. Command Surface

Proposed initial commands:

```text
project-env doctor
project-env discover [path]
project-env status [path]
project-env resolve [path]
project-env explain [path] [--why-different <other>]
project-env run [path] -- <command...>
project-env audit
project-env bench [path] [--scenario <name>]
```

Default all inspection, audit, and garbage-collection commands to read-only.
Require explicit application for mutations.

The read-only v1 surface is `doctor`, `discover`, `status`, `resolve`,
`explain`, `audit`, and `bench`. Add `run`, `provision`, `lease`, `release`,
`alias set --apply`, and `gc --apply` only after the bakeoff. This prevents the
initial tool from becoming a worktree scheduler before identity and source binding
are proven.

Every command must support a schema-versioned `--json` response and stable exit
codes. Responses include controller schema, project-adapter schema, backend version,
all three identities, mutation intent, and blocking conditions. Human text is a
view over that contract, not something harnesses parse. Commands are idempotent
under retry, and no workflow requires shell activation. `run` accepts an argv array
after `--` and executes it directly; adapters must not concatenate project-controlled
values into a shell command or evaluate configuration as code.

## 13. Skill Responsibilities

The skill should:

- Trigger on worktree creation, venv creation, `uv sync`, dependency changes,
  environment promotion, duplicate-environment audits, or cleanup requests.
- Inspect project policy and current dependency inputs.
- Use `project-env` rather than reimplementing environment logic in shell.
- Explain shared versus experimental selection when it matters.
- Require verification before promotion.
- Refuse unsafe cleanup and report the exact lease or Git state blocking it.
- Read project-specific behavior from checked-in project configuration; keep only
  backend and security guidance in the skill's progressively loaded references.
- Prefer a backend's native store/projection when its measured behavior satisfies
  policy; do not force all ecosystems through a Python-shaped abstraction.

The skill should not:

- Automatically install arbitrary new dependencies globally.
- Treat environment reuse as permission to share mutable runtime state.
- Modify manifests merely to increase cache reuse.
- Delete work or terminate unrelated processes.
- Own leases, caches, or mutable state itself.

Keep the future `SKILL.md` under 500 lines and focused on trigger conditions,
decision points, and safe CLI use. Put deterministic work in tested scripts, load
backend/security references only when relevant, validate with Skill Creator's
validator, and forward-test read-only scenarios before enabling mutations.

## 14. Configuration Ownership and Precedence

`.files` owns the portable CLI, harness adapters, safe global defaults, and this
user's machine policy. A product owns its dependency and source-binding adapter in
its own repository, provisionally as `.project-env.toml`, so collaborators, CI,
worktrees, and other machines observe the same rules.

Global policy example in `.files/config/project-env/policy.toml`:

```toml
schema = 1

[defaults]
canonical_branches = ["dev", "main"]
cache_root = "/workspace/cache"
environment_root = "/workspace/environments"
lease_root = "/workspace/project-env/run"

[security]
remote_reads = false
remote_writes = false
unreviewed_build_isolation = "required"
```

Project-owned example in `zerOS/.project-env.toml`:

```toml
schema = 1
backend = "uv"
manifests = ["pyproject.toml", "uv.lock"]
python = "3.12"
dependency_groups = ["dev"]
profiles = ["base", "test", "voice", "gpu"]
source_binding = "module"
source_roots = ["src"]
install_strategy = "no-install-project"
```

Apply configuration in this order, with later values winning only where the schema
declares them overridable:

1. Built-in safe defaults.
2. Versioned global `.files` policy.
3. Checked-in project configuration.
4. Machine-local, untracked overrides for paths and capabilities.
5. Explicit CLI flags.

Security policy is monotonic rather than ordinary last-write-wins: project or
branch configuration may tighten global rules but cannot disable build isolation,
enable remote writes, add a trusted publisher, or broaden writable roots. A
break-glass relaxation requires an explicit interactive/admin action and an audit
record; an agent-provided flag is insufficient. Any branch change to project policy
is itself an unreviewed dependency-policy change until merged.

The controller may keep a machine-local discovery alias from a checkout path to a
repository, but it is not the authority for project behavior. Secrets, tokens, and
private index credentials never belong in any of these files. Do not finalize the
schema until the fixtures and zerOS pilot reveal the minimum required fields.

Resolve and validate all configured repository-relative paths before use. Source
roots, manifests, generated shims, and writable outputs may not escape the invoking
worktree through `..` or symlink traversal unless a global allowlist explicitly
names the target.

The v1 project schema is declarative and contains no shell hooks or executable
adapter paths. Backend adapter code lives in the trusted, versioned controller/tool
capsule; a project may select a known adapter and data options but cannot cause the
controller to import or evaluate branch-owned code.

## 15. State and Lease Identity

Use atomic JSON files plus `flock` for the single-host pilot. Keep state local and
rebuildable from Git/worktree/environment inspection. Do not make SQLite or a
daemon mandatory until file-based contention is measured.

Do not conflate two lifetimes:

- A **provisioning lock** exists only while one process constructs or verifies a
  target closure. It is released immediately after atomic publication or failure.
- A **usage lease** pins one exact realization while a child process or harness
  session may use it. `project-env run` owns and heartbeats this lease until the
  child exits, including signal/cancellation handling.

Harnesses that bypass `project-env run` must acquire and release a session lease
explicitly. A lease that expires while its verified process still exists remains a
root. The Linux pilot may use `flock`; the macOS adapter must use a tested native
locking primitive rather than assuming the command is installed.

`project-env run` supports foreground process trees. A command that daemonizes or
hands work to an editor/language server must use a harness-owned session lease; the
wrapper cannot safely infer that detached lifetime from its parent PID.

Separate descriptive state from roots. An active lease, project profile, or manual
pin is an explicit GC root. JSON indexes can be rebuilt; roots must be updated
atomically and reconciled against process and Git identity before collection.

A process lease must include enough identity to avoid PID-reuse errors:

```text
machine ID
boot ID
PID
process start time
task ID
worktree path and Git common directory
resolved environment identity and path
created, heartbeat, and expiry timestamps
```

A stale timestamp alone must not authorize cleanup. Reconcile lease identity
against the running process, Git state, and harness session state.

Lease acquisition and GC commit share the same per-realization exclusion boundary.
GC marks a candidate as deleting, reacquires and rechecks all roots, atomically
moves controller-owned data to a recoverable trash/staging area, and only then
deletes after a grace period. A concurrent lease either wins before the mark or
fails cleanly and retries resolution; it can never attach halfway through deletion.

## 16. Coordination and Capacity

Distinguish registered worktrees from simultaneously executing workloads.

The future scheduler may enforce configurable limits such as:

```text
registered worktrees: unlimited within storage policy
active agent sessions: machine-specific
CPU test jobs: bounded
browser/E2E jobs: tightly bounded
GPU services: one shared instance per model/profile
```

Schedule expensive work using capability and cache locality, not merely idle CPU.
A machine that already holds the matching model, toolchain, dependency closure,
and recent result subgraph may beat a nominally faster cold machine. Prewarming
may be speculative, but it must be cancellable and lower priority than interactive
work.

Port allocation and process leases belong to a future task-runtime manager, not
to v1 of the dependency environment manager. `project-env` may consume a task ID
but should not become the scheduler or process supervisor.

## 17. Trust and Supply-Chain Boundary

- Treat reviewed canonical locked dependencies as trusted inputs within the
  declared project policy, not as proof that their code is inherently benign.
- Keep dependency compatibility separate from execution trust. A source-only branch
  may reuse the canonical closure while still requiring sandboxed execution because
  its first-party code is unreviewed.
- Treat dependency changes from experimental or externally sourced branches as
  untrusted until reviewed.
- Never promote an experimental environment merely because tests passed.
- Require manifest diff, lockfile diff, source/index provenance, and native build
  review before a new identity becomes canonical.
- Do not expose credentials to dependency build steps unless explicitly needed.
- Preserve package hashes and locked-source metadata in environment provenance.
- Prevent experimental identities from changing global tools or shared services.
- Namespace caches by trust level for correctness and attribution, but do not call
  that a security boundary when processes share one Unix user.
- Build and run unreviewed dependency changes in a real isolation boundary: a
  separate UID, rootless container/user namespace, or disposable VM without ambient
  credentials and with separate writable stores. Permit read access only to
  verified immutable artifacts by digest.
- Apply the same boundary to any unreviewed first-party code when the threat model
  is adversarial rather than merely accidental. Mount only that task's worktree and
  runtime state writable; hide sibling projects, `.files` credentials, SSH keys,
  Tailscale state, and trusted cache write paths. `resolve --json` reports the
  required trust mode, and `run` refuses if the harness cannot satisfy it.
- Dependency install and lifecycle scripts are arbitrary code. Restrict secrets,
  writable mounts, and network access during unreviewed builds where feasible.
- Prefer a reviewed canonical builder as the initial writer to cross-machine
  artifact/result stores; developer machines begin read-only. CI is trusted only
  when its source ref, workflow, credentials, and provenance policy are trusted.
- Sign or otherwise authenticate publication manifests and always verify content
  digests on receipt. A network identity does not establish artifact correctness.

## 18. Cross-Machine Behavior

- Sync source, manifests, lockfiles, project policy, and skill code through Git.
- Materialize environments independently on Linux and macOS.
- Resolve a platform-specific closure from the same descriptor; never pretend the
  installed artifacts are cross-platform.
- Do not sync venvs, `node_modules`, sockets, databases, or runtime directories.
- Do not copy or remotely expose uv/pnpm internal cache layouts. Exchange immutable
  wheels through a PyPI-compatible Simple Repository API, generic blobs through an
  OCI Distribution-compatible registry, and build results through an established
  CAS/Remote Execution API when that complexity is justified. A smaller first
  broker may implement a signed manifest plus digest-addressed read API, but its
  wire format must not depend on a package manager's private on-disk schema. Tags
  and aliases are discovery hints; clients verify and pin the returned digest.
- Consider remote caches only after local cache correctness and hit rates are
  measured. Fetch metadata first and large blobs lazily.
- Use Tailscale for private service and artifact-cache connectivity. Gate remote
  cache use on a direct or acceptable peer-relay path measured by `tailscale ping`;
  DERP fallback is secure but can add latency and cap throughput.
- Configure explicit least-privilege Tailscale grants/ACLs, tags, and policy tests.
  A new tailnet's default policy allows communication among all devices, and
  Tailscale supplies encrypted network identity rather than application-level
  authorization or artifact integrity. Bind the service only to the tailnet/tsnet
  interface and add application authentication when the integration requires it.
- Do not bidirectionally synchronize active Git worktrees. Git remains the source
  exchange protocol; an artifact cache or one-way explicit transfer handles large
  generated data. Syncthing-style conflict copies and rsync mirrors are not a
  substitute for branch and merge semantics.
- Treat Taildrive as an optional human file-sharing surface, not dependency
  infrastructure, while it remains alpha.

## 19. Rollout

### Phase -1 — Observatory and architecture bakeoff

- Implement only a read-only inventory and benchmark harness.
- Record installed backend versions and supported experimental flags.
- Select three representative products: a small pure-Python project, zerOS with
  native/GPU dependencies, and a Node monorepo or application.
- Capture cold, warm-store, warm-environment, source-only-change, one-dependency-
  change, and concurrent-agent scenarios.
- Compare native uv, uv centralized-project-envs, the custom dependencies-only
  final-path venv, the relocatable wheel-layer experiment, Pixi where applicable,
  pnpm default, and pnpm global virtual store.
- Run cold cases with isolated temporary cache/environment roots; never clear a
  live global cache. Distinguish cold-network, warm-artifact, and warm-realization.
- Randomize scenario order, record background load and thermal/power conditions,
  and collect enough repetitions to report uncertainty. Target at least 100 hot
  samples for an empirical p95. For expensive cold cases, start with 10–20 and
  report median/range or uncertainty rather than labeling one extreme value p95.
- Measure the same real lint/test/build commands with and without the project's
  existing result cache. Do not collect shell history, prompts, source contents,
  window titles, or agent transcripts.
- Report confidence intervals and practical effect sizes. Do not infer p95 from a
  handful of samples or accept a custom layer on a relative percentage alone.
- Write an ADR accepting, rejecting, or deferring each backend based on measured
  thresholds and correctness fixtures.

Exit criterion: a reproducible results table identifies the actual dominant
latency and storage costs. No live environment is migrated or deleted.

### Phase 0 — Inventory and dry-run specification

- Inventory environment, cache, worktree, and process conventions.
- Record current zerOS shared-runtime behavior.
- Define dependency identity fixtures.
- Classify projects by source-binding mode and identify editable/local packages.
- Probe clone, hardlink, and copy behavior on the actual filesystem.
- Produce read-only `doctor`, `status`, and `audit` output samples.
- Make no migrations or deletions.

Exit criterion: the inventory accounts for active environments and distinguishes
logical size from physically deduplicated storage.

### Phase 1 — Read-only CLI, then skill skeleton

- Implement project discovery, hashing, source-binding analysis, status, and audit.
- Implement `explain --why-different` and benchmark result export.
- Define and fixture-test the schema-versioned JSON/exit-code contract before any
  harness integration.
- Validate CLI behavior independently of any harness.
- Initialize `worktree-env-manager` with Skill Creator tooling only after the CLI
  contract stabilizes; add concise instructions and UI metadata.
- Validate the skill and CLI.

Exit criterion: the tool makes correct, explainable selections without writing.

### Phase 2 — zerOS pilot

- Register zerOS and its Hunyuan/Whisper service boundaries.
- Provision a dependencies-only immutable environment for one canonical lockfile.
- Bind two different worktree source paths to that dependency layer and prove
  imports resolve to the invoking worktree.
- Test two ordinary worktrees sharing the same identity.
- Test one dependency-changing worktree receiving a new identity.
- Verify concurrent execution and provisioning locks.
- Compare the custom realization against the winning native baseline; abandon the
  custom path if it does not materially improve the weighted objective.

Exit criterion: no project-local package duplication is required for the pilot,
and isolation tests show no cross-worktree mutation.

### Phase 3 — Safe provisioning and leases

- Add task and environment leases.
- Make `project-env run` hold a usage lease for the complete child lifetime; add an
  explicit session lease API for harnesses that cannot use the wrapper.
- Add candidate provisioning and canonical alias switching.
- Add process identity metadata, but leave port allocation to runtime management.
- Test interrupted agents and stale leases.

Exit criterion: promotion is atomic and cleanup refuses active or unsafe state.

### Phase 4 — Garbage collection

- Add report-only GC.
- Define retention and lease-expiry policy.
- Keep controller GC and native backend prune operations separate.
- Add explicit `--apply` cleanup with a complete target list.
- Verify recovery behavior and recreate deleted environments from locks.

Exit criterion: stale state can be reclaimed without losing source or unique
dependency declarations.

### Phase 5 — Additional products and machines

- Add Flowkit, Alpha, and Hermes adapters one at a time.
- Validate macOS paths and platform identities.
- Evaluate pnpm's global virtual store as a separate Node pilot before adding any
  custom Node environment projection.
- Add result caching with Nx, Turbo, Pants, or the project's existing engine only
  where hit-rate measurements justify it.
- Evaluate a private remote cache over Tailscale only after local correctness.

Exit criterion: each product has documented ownership and reproducible setup on
both devices.

## 20. Validation Strategy

Create fixtures for:

- Main checkout and linked worktree discovery.
- Identical and different lockfiles.
- Two different projects resolving to one identical third-party closure.
- A universal lockfile change that does not affect the selected target platform,
  compared with the conservative full-lock v1 key.
- Descriptor/closure stability with an unexpected realization mismatch and
  quarantine behavior.
- The same closure materialized at different final roots produces independently
  verified realization identities without being mistaken for corruption.
- Concurrent requests for the same missing environment.
- Different Python implementations, ABI tags, operating systems, architectures,
  libc versions, and declared CUDA/GPU capability profiles.
- Dependency changes without branch-name hints.
- Branch-name hints without dependency changes.
- Dirty, untracked, unpushed, merged, and deleted worktrees.
- Active, stale, and orphaned leases.
- Lease acquisition racing GC, foreground cancellation, detached children, editor
  sessions, and recovery from trash staging.
- Interrupted provisioning before `READY` publication, corrupt/missing publication
  manifests, and temporary-directory rename only for proven-relocatable backends.
- Venv absolute interpreter paths and console-script shebangs before and after
  publication; a Python environment must never be moved after construction.
- Hardlink/reflink behavior and actual allocated disk usage.
- Editable installs and local path/workspace dependencies.
- Import provenance from two simultaneous worktrees using one dependency layer.
- `importlib.metadata`, entry points, package data, namespace packages, pytest
  plugins/import modes, multiprocessing, subprocesses, and dynamic versioning under
  each supported source-binding mode.
- Executable `.pth` files, `sitecustomize`, user-site leakage, and environment
  variables that alter interpreter/package-manager behavior.
- Accidental `uv run` or package-install attempts against an immutable env.
- Packages that write bytecode, caches, plugins, or data beside installed code.
- PID reuse, rebooted hosts, stale heartbeats, and changed boot IDs.
- Malicious or unreviewed dependency changes from an experimental branch.
- Source-only unreviewed code that reuses a canonical closure but attempts to write
  sibling worktrees, global policy, credentials, or trusted caches.
- A false cache hit caused by an omitted environment variable, tool version,
  platform property, generated file, or local source input.
- Result-cache poisoning and trusted/read-only writer separation.
- Same-user cache tampering versus a real isolated unreviewed build boundary.
- A branch attempting to weaken global policy, enable remote publication, inject
  shell syntax, or escape its worktree through configured paths or symlinks.
- Digest mismatch, forged publication metadata, unauthorized Tailscale peer, and
  remote broker outage with a warm local store.
- Profile composition with compatible and incompatible feature deltas.
- Dependency-only realization versus per-worktree native environment.
- uv centralized environment deletion by `uv cache prune` and dangling links.
- pnpm global virtual store compatibility with editors, bundlers, lifecycle scripts,
  `NODE_PATH`, and concurrent worktrees.
- Direct, peer-relayed, and DERP-relayed Tailscale artifact transfers.
- Offline operation with a fully warm local artifact store.
- Controller bootstrap, failed self-update, and rollback without a project venv.

Benchmark scenarios must include:

```text
cold: empty environment and empty relevant package cache
warm-store: package artifacts present, environment/projection absent
hot: verified realization and projection present
delta: one direct dependency or profile changes
source-only: source changes but dependency declarations do not
fan-in: N agents request the same missing identity concurrently
fan-out: N agents request N different identities concurrently
native: compiled dependency or lifecycle build is required
recovery: provisioning or transfer is interrupted at each atomic boundary
```

For each scenario record p50/p95 wall time, time to first useful command, CPU,
peak RSS, network bytes, allocated blocks, apparent bytes, inode count, cache hit
source, lock wait, and import provenance. Include correctness assertions in the
benchmark; a fast wrong result is a failed sample.

On reflink/deduplicating filesystems, add filesystem-specific shared-versus-exclusive
extent measurements; ordinary apparent size or per-file block counts can still
misstate the incremental cost of another worktree.

Pre-register an absolute usability budget and a relative improvement threshold.
The provisional 20% custom-backend gate is meaningful only with uncertainty bounds,
allocated physical-byte/inode measurements, and zero correctness failures. Include
the whole task-to-feedback path: dependency projection can be irrelevant when
compile, service startup, or tests dominate.

Forward-test the skill with fresh agents only after the read-only CLI is stable.
Do not allow forward tests to mutate live projects or production services.

## 21. Observability

`project-env status` should report:

```text
project, configuration sources, and canonical branch
worktree and task identity
descriptor, resolved closure, realization, and component digests
selected environment and verification state
backend, native feature flags, and projection mode
source-binding mode and resolved source roots
import provenance for the current worktree
shared or experimental classification
active leases
harness session and usage-lease ownership
logical and allocated storage
critical-path timing and cache hit/miss source
trust namespace and remote writer policy
controller, adapter, and JSON schema versions
blocking safety conditions
recommended next command
```

Avoid collecting shell history, source contents, prompts, credentials, or raw
agent transcripts.

## 22. Risks

- A shared mutable venv could corrupt all active worktrees.
- Incorrect dependency hashing could reuse an incompatible environment.
- Cross-filesystem layout could silently disable hardlink deduplication.
- Native dependencies may include undeclared host state.
- Global CLI upgrades may change behavior across every project.
- Stale process or lease data could block cleanup indefinitely.
- A future runtime manager could destroy unique work if it conflates environment
  GC with Git worktree cleanup; v1 must not own Git deletion.
- Environment aliases could change underneath long-running processes without
  per-task leases to the resolved immutable path.
- Editable or local path installs could bind a shared environment to the wrong
  worktree.
- Hardlinked writable packages could corrupt the global cache for every env.
- An experimental branch could poison canonical or global dependency state.
- Packages that write beside their code could fail in an immutable environment.
- A custom controller could duplicate uv, pnpm, Pixi, Nix, or build-engine behavior
  and become slower and less reliable than the native tools.
- Preview features such as uv centralized project environments or pnpm's global
  virtual store may change semantics or expose tool-compatibility bugs.
- Overly coarse environment hashes waste reuse; incomplete hashes create wrong
  cache hits.
- Hashing a whole universal lockfile is safe but may create platform-irrelevant
  misses; deriving a closure incorrectly can create unsafe hits.
- Project policy stored only in `.files` could diverge for collaborators and CI.
- A branch-controlled adapter could weaken security policy, escape the worktree, or
  inject a command if precedence, path handling, and argv boundaries are careless.
- A same-user “untrusted” namespace can still overwrite writable shared stores.
- A detached process or GC/lease race could use a realization after deletion.
- Reusing dependencies without caching builds and tests may optimize disk while
  barely changing the agent feedback loop.
- A remote cache can be slower than local execution for small artifacts or a
  relayed Tailscale path.
- A poisoned shared result cache can distribute incorrect outputs to every agent.
- Tailscale's default allow-all tailnet policy can expose a broker more broadly than
  intended, while encrypted transport alone cannot prevent artifact poisoning.
- Profile composition can hide conflicts if manifests are merged after, rather
  than before, dependency solving.

Mitigate these through immutable identities, atomic operations, fail-closed
cleanup, explicit provenance, trust namespaces, backend bakeoffs, and phased
rollout. Every custom layer needs an evidence-based reason to exist.

## 23. Research Synthesis

The research changes the plan in several material ways:

1. **uv already solves package-object reuse, but not this entire worktree problem.**
   Its cache is append-only and concurrency-safe, it links cached packages into
   environments, and it locks target environments during install. Its current
   centralized-project-envs preview relocates an environment into the cache, but
   the implementation keys it from workspace path plus interpreter identity, not
   from a dependency closure. Separate worktree paths therefore still receive
   separate environments. `uv cache prune` deletes all centralized environments.
2. **Python venv directories are realizations, not portable artifacts.** Installed
   scripts contain absolute interpreter paths, so the Python documentation says
   moved environments should be recreated. Cross-device reuse belongs at the
   wheel/package/content layer, not by syncing venv trees.
3. **Nix's useful abstraction is closure plus profile, not one global environment.**
   Unique store paths prevent interference; profiles atomically point at immutable
   generations; GC roots define liveness. These ideas map cleanly to environment
   realizations, project aliases, leases, and rollback without requiring Nix as v1.
4. **Dependency reuse and computation reuse are separate.** Bazel, Pants, Nx, and
   Turbo cache actions or tasks from declared inputs, commands, environments, and
   outputs. Sandboxing matters because an undeclared input makes a cache key wrong.
   This plane can reduce feedback latency more than venv deduplication alone.
5. **BuildKit's layer lesson is frequency ordering.** Stable expensive dependency
   inputs belong below volatile source; mutable download/build caches need explicit
   concurrency modes and are not image layers. The same distinction applies to
   dependency closures versus worktree source and task state.
6. **pnpm now contains a direct Node analogue.** Its experimental global virtual
   store keys central package directories by dependency-graph hash and explicitly
   targets repeated Git worktrees in multi-agent development. It also documents a
   shared trust boundary, editor/tool compatibility risks, `NODE_PATH` requirements,
   and mark-and-sweep registration. Test this before writing Node projection code.
7. **Declarative composition is the safe meaning of inheritance.** Pixi composes
   features into environments and can keep related environments in solve-groups;
   Flox merges included manifests and then locks the merged result. Both resolve
   conflicts before activation. This is superior to runtime `site-packages` chains.
8. **Portable Python capsules are a deployment option, not the default edit loop.**
   PEX can cache or expand into a venv and split third-party dependencies from
   first-party source in container layers. Plain zipapps cannot load C extensions
   from inside the archive. Capsules fit tools, CI, and remote execution better
   than arbitrary editable monorepos.
9. **Network sharing should be artifact-oriented.** A direct Tailscale connection
   normally has the best latency and throughput; DERP is secure but slower and
   throughput-limited. Query by digest, transfer only missing blobs, and avoid
   round trips on the hot local path. Do not turn a WAN mount into `site-packages`.
10. **Identity needs three levels.** Project policy belongs in a descriptor, an
    exact third-party graph belongs in a shareable resolved closure, and installed
    output belongs in a realization. Including project ID in the closure prevents
    valid reuse; omitting adapter/trust policy from the descriptor hides risk.
11. **uv's universal lock creates a deliberate v1 tradeoff.** Hashing the whole
    lock is conservative and explainable but can cause false misses across platform-
    irrelevant changes. A normalized, ephemeral `uv export` can become a closure
    input only after marker/local-package fixtures prove it equivalent.
12. **Logical trust namespaces are not sandboxes.** pnpm's documented writable-
    store trust boundary generalizes: arbitrary package scripts under one Unix user
    can mutate that user's caches, and unreviewed first-party tests can do the same.
    Adversarial execution needs a separate OS/container/VM boundary, not another
    directory name or chmod convention.
13. **Project policy belongs with the project.** `.files` is the global controller
    and personal policy layer; checked-in source-binding and backend behavior must
    travel with each product to work for other developers, CI, and every worktree.
    Security constraints still combine monotonically so a feature branch cannot
    grant itself more trust or broader writable access.
14. **Stable artifact APIs beat cache-directory replication.** The Python Simple
    Repository API exposes hashed distribution files, OCI registries address blobs
    by digest, and Remote Execution APIs define CAS/result exchange. These are safer
    cross-machine boundaries than uv/pnpm private storage layouts.
15. **The environment manager is not the whole runtime.** Worktree allocation,
    services, task state, scheduling, and result caching remain adjacent planes and
    should converge through a later runtime RFC only after the environment JSON
    contract is stable.
16. **The controller needs its own bootstrap boundary.** A manager that imports from
    the environment it is repairing creates circular failure. Ship it as a pinned,
    isolated tool capsule or binary with atomic update and rollback.

## 24. Architecture Options

These options are deliberately distinct enough to expose different assumptions:

### A. Native package-manager projections

Use uv per-worktree environments and pnpm's virtual/global virtual stores. Add only
policy, measurement, and cleanup. This is the lowest-complexity baseline and may
be sufficient when package contents dominate disk but projection metadata is cheap.

### B. Content-keyed dependencies-only Python realizations

Provision one verified third-party environment per closure/realization identity and
bind each worktree's source at execution. This offers the lowest hot worktree cost,
but source binding, console scripts, local workspace packages, and tools that write
into their environment create the largest Python-specific correctness surface.

### C. Pixi workspace and capability profiles

Adopt Pixi for Python plus Conda/native dependencies. Model `base`, `test`, `voice`,
and `gpu` as features and solve-groups. This reduces custom composition logic and
could replace some OS/venv fragmentation, at the cost of a new manifest/lock system
and a migration from existing uv-native projects.

### D. Nix, Flox, Devbox, or devenv closures

Describe the entire toolchain and services as an immutable closure with binary
caches and profiles. This provides the strongest reproducibility and cross-language
model. It also has the largest adoption, evaluation, macOS, GPU, and debugging cost.
Use it first for system capability gaps or a greenfield project, not as a forced
rewrite of every Python project.

### E. OCI/BuildKit development capsules

Put toolchain and dependencies in stable image layers, bind-mount source, and keep
task state in disposable writable layers/volumes. This gives a strong isolation
boundary and remote execution path. Container startup, filesystem performance,
UID mapping, editors, GPU passthrough, and macOS virtualization can hurt the tight
interactive loop.

### F. Pants/Bazel-style execution engine

Model lint, test, build, and generation as hermetic actions backed by a local or
remote CAS. This attacks repeated computation and scales to remote workers, but
requires accurate target/input modeling and meaningful repository adoption. It is
not a prerequisite for dependency deduplication.

### G. Portfolio controller (meta-option)

Keep a thin `.files` control plane over native stores: uv for Python artifacts,
pnpm global virtual store for proven-compatible Node projects, Pixi or Nix adapters
where native/system dependencies justify them, service APIs for large models, and
an existing task engine for result caching. Add custom Python realizations only for
projects where the bakeoff proves a material win.

G is not a competing backend and must not be scored against A–F; it is the policy
mechanism that can select them per project. Giving a hybrid the best attribute of
every component would make it win by definition while hiding integration cost.

### Qualitative bakeoff matrix

| Approach | Expected strength | Principal risk | Evidence gate |
|---|---|---|---|
| Native uv/pnpm | Lowest adoption and maintenance cost | Per-worktree projection overhead or preview incompatibility | Meets absolute ready/disk budgets |
| Shared Python realization | Very cheap hot worktrees | Source binding, writes, metadata, and absolute paths | Beats native materially with zero fixture failures |
| Pixi profiles | Python plus native capability composition | New manifest/solver workflow | Removes measured native setup pain in one project |
| Nix/Flox/devenv | Strong system-level closure and rollback | Onboarding, evaluation, macOS/GPU friction | Greenfield/system-heavy pilot wins end to end |
| OCI/BuildKit | Strong execution isolation and remote path | Startup, mounts, UID/editor/GPU complexity | Adversarial isolation plus latency budget passes |
| Pants/Bazel engine | Reuses expensive computation | Repository modeling and hermeticity cost | Representative test/build hit rate repays adoption |

## 25. Proposed Convergent Architecture

Adopt narrowed option G as the decision architecture, with option A as the default
and experimental control. V1 is a small environment control plane around multiple
native data planes:

```text
global policy + project config + worktree + requested capability
                            │
                            ▼
                 normalized descriptor
                            │
                            ▼
                 target resolved closure
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
    native backend projection       custom realization
             └──────────────┬──────────────┘
                            ▼
                 verified realization
                            │
                            ▼
              worktree source binding + run
                            │
                            ▼
             schema-versioned JSON evidence
```

The descriptor is computed from checked-in project configuration, authoritative
manifests/locks, global policy, and explicit target capabilities; it is not another
dependency manifest. The resolved closure is the cross-project reuse boundary.
Service capabilities and result-cache policy stay outside v1 and consume this
subsystem later through the JSON contract.

The broader runtime may later use progressive hydration:

1. **Metadata-ready** — worktree exists and descriptor is resolved.
2. **Tool-ready** — pinned global tools are available.
3. **Dependency-ready** — local realization or projection is verified.
4. **Service-ready** — only requested heavy services are healthy.
5. **Result-ready** — matching outputs have been restored or computation finished.

V1 implements only metadata/tool/dependency readiness. A later runtime manager can
let an agent read and plan while services or build state warm in the background;
the first command then waits only for its declared capability.

### Creative extensions to test, not assume

- **Relocatable wheel layer:** build all source distributions into verified wheels,
  install third-party packages into an immutable target tree without a venv, and
  pair it at launch with a pinned interpreter plus generated entry points. This can
  remove absolute venv paths and permit atomic directory publication. Reject it if
  `sys.prefix`, package-data, native-library, metadata, or tool compatibility tests
  fail; it is a bakeoff candidate, not runtime `site-packages` inheritance.
- **Ephemeral feature overlay:** for brainstorming dependencies not yet accepted in
  a project manifest, use uv's per-invocation additional-dependency mechanism or a
  disposable full environment inside the unreviewed-build isolation boundary.
  Never point this mode at a shared realization; promotion means editing and locking
  the project manifest normally.
- **Cost-aware GC:** retain artifacts by rebuild cost, size, recency, and predicted
  reuse instead of one TTL. A 10 GB downloadable wheel set and a 10 GB locally
  compiled CUDA closure should not have equal eviction priority.
- **Speculative delta realization:** when a branch edits one dependency, prefetch
  or build only its changed closure while the agent is still reasoning; cancel on
  manifest reversion.
- **Cache-local scheduling:** route a task to the device already holding its model,
  toolchain, dependency closure, and result subgraph when transfer cost exceeds
  remote execution overhead.
- **Peer artifact broker:** expose a read-mostly digest API over Tailscale/tsnet;
  prefer the Simple Repository API, OCI Distribution, or REAPI/CAS where they fit;
  otherwise exchange authenticated manifests and missing digest-addressed blobs.
  Never expose a writable cache tree or rely on peer availability for correctness.
- **Shadow verification:** randomly rerun a small percentage of local and remote
  cache hits and quarantine a namespace on disagreement.
- **Dependency entropy metric:** track distinct descriptor, closure, and realization
  counts per project over time. High entropy reveals lock drift or over-specific
  profiles; low closure entropy with many worktrees validates reuse.
- **Linux overlay projection:** test an immutable lower dependency tree plus a tiny
  writable task upper layer using OverlayFS. Reject it if mount privileges, inode
  semantics, debuggers, file watchers, or macOS parity outweigh materialization
  savings.
- **Profile generations:** promote a tested capsule by atomically switching a
  project profile pointer; retain prior generations for instant rollback.
- **Capability services:** move voice transcription, large models, browsers, and
  GPU pipelines behind versioned local/Tailscale APIs when process startup and
  duplicated memory dominate package installation.

### Falsifiable convergence gates

- Keep native uv if a hot worktree reaches the first representative command within
  the agreed latency budget and allocated duplication stays within budget.
- If native backends meet the budgets and no custom path clears its evidence gate,
  stop with the observatory, project policy, and thin launch wrappers; do not build
  an environment farm merely because it was planned.
- Keep the custom Python realization only if it meets an absolute usability budget
  and improves p95 task-to-feedback time or allocated physical storage by a material
  threshold, provisionally 20% with uncertainty bounds, while producing zero
  source-provenance, isolation, or mutation failures across the fixture corpus.
- Adopt pnpm global virtual store per project only after editor, bundler, lifecycle,
  and concurrent-install tests pass; otherwise keep pnpm's default content store.
- Adopt Pixi for a project only when it removes native/system environment work or
  profile duplication that uv cannot express, and its lock/activation latency wins.
- Adopt Nix/devenv more broadly only after one greenfield or system-heavy pilot
  demonstrates acceptable onboarding, evaluation, debugging, macOS, and GPU paths.
- Add remote cache reads only when measured direct/peer-relay network transfer plus
  lookup is faster than local reconstruction at the artifact's size percentile.
- Add remote cache writes only after trust namespaces, authentication, provenance,
  poisoning recovery, and writer policy are tested.
- Allow unreviewed source or dependency execution to touch shared infrastructure
  only after the selected UID/container/VM boundary passes adversarial write and
  credential tests.
- Add a daemon only when measured lock contention, repeated discovery, or prewarm
  scheduling cannot meet the budget with short-lived CLI calls and files.

## 26. Provisional Decisions and Open Review

This validation pass establishes the following defaults for the next design
iteration; they are recommendations, not a claim of user approval:

1. Optimize task-to-trustworthy-feedback, with wrong reuse or lost work as a hard
   failure.
2. Keep v1 to environment discovery, identity, native/custom provisioning,
   projection, source binding, verification, and process-scoped leases.
3. Use native uv/pnpm behavior as the control; custom Python realizations must earn
   their complexity in the bakeoff.
4. Use descriptor, resolved-closure, and realization identities. Branch names affect
   reporting/retention, never dependency compatibility.
5. Store project behavior with each project and global personal policy in `.files`;
   merge security constraints monotonically so branches can only tighten them.
6. Let the harness own worktrees and task state. Integrate through schema-versioned
   JSON and stable exit codes with no activation requirement.
7. Use atomic files and `flock` for the Linux pilot, while keeping the lock adapter
   replaceable for macOS and a future measured need for SQLite/daemon state.
8. Keep controller GC separate from native package-store pruning; report before
   applying either.
9. Default local/path workspace packages to an isolated project environment until a
   project adapter proves safe separation.
10. Keep remote sharing local-first, artifact-oriented, least-privilege, and
    read-only for developer clients initially.

The remaining choices need measurements or explicit preference:

1. Absolute p95 ready/feedback budgets and the physical disk/inode budget.
2. The small correctness fixture and the first narrow zerOS pilot surface.
3. Whether v1 supports both module and script binding or starts with script mode.
4. The local isolation backend for unreviewed execution: separate UID, rootless
   container/user namespace, or disposable VM.
5. Final Linux/macOS storage roots and retention weights.
6. Which global tools are stable enough for `.files` ownership.
7. Which existing build/test engine should become the later result-cache pilot.
8. Whether `.project-env.toml` is preferable to a `[tool.project-env]` table.

## 27. Initial Recommendation

- Begin with a backend-neutral observatory and Python/uv correctness fixtures.
- Benchmark native uv before building a custom environment farm.
- Run a separate pnpm global-virtual-store experiment because pnpm already targets
  multi-agent Git worktrees; do not make Node wait on Python implementation.
- Use JSON metadata plus filesystem locks for the zerOS pilot.
- Use the three-level identity model; treat branch names as hints and isolate based
  on closure inputs and trust policy.
- Require approval for canonical alias updates and all cleanup initially.
- Keep scheduling, ports, and process supervision outside v1.
- Keep project adapters checked into their products and global defaults in `.files`.
- Share third-party dependencies only; bind project source at execution time.
- Support module and script source bindings; isolate local workspace-package
  projects until a safe adapter exists.
- Prefer clone/reflink after probing; do not force hardlinks globally.
- Pilot a small zerOS Python surface before including Hunyuan's full GPU stack.
- Model reusable `base`, `test`, `voice`, and `gpu` capabilities as declarative
  profiles composed before solving, not venv inheritance.
- Treat heavy voice/GPU stacks as service candidates when memory and startup data
  show that process reuse matters more than package reuse.
- Evaluate task-result caching after environment identity is reliable; it is a
  separate, potentially larger latency win.
- Keep all remote-cache work local-first and direct-Tailscale-path-aware.
- Do not build a peer cache until a standard artifact protocol and explicit
  Tailscale grants/application authorization are selected.

## 28. Review Sequence

Review the plan in this order:

1. Confirm the narrowed v1 boundary and three-level identity model.
2. Choose the small fixture, zerOS pilot surface, and first source-binding mode.
3. Set absolute and relative bakeoff thresholds, then run Phase -1 with isolated
   cache roots.
4. Choose the unreviewed-build isolation backend and verify the security fixtures.
5. Approve the minimum project-owned configuration schema and machine-local roots.
6. Keep the skill named `worktree-env-manager`; write a separate
   `workspace-runtime` RFC only when service, scheduling, and result planes enter
   implementation scope.

Record accepted decisions directly in this plan. Move stable decisions into the
future skill references only when implementation begins.

## 29. Primary Research Sources

- [uv project environments and centralized preview](https://docs.astral.sh/uv/concepts/projects/layout/)
- [uv cache semantics, concurrency, pruning, and filesystem locality](https://docs.astral.sh/uv/concepts/cache/)
- [uv partial installations and sync behavior](https://docs.astral.sh/uv/concepts/projects/sync/)
- [uv universal and platform-specific resolution](https://docs.astral.sh/uv/concepts/resolution/)
- [uv lockfile export formats](https://docs.astral.sh/uv/concepts/projects/sync/#exporting-the-lockfile)
- [uv project execution and per-invocation dependencies](https://docs.astral.sh/uv/concepts/projects/run/)
- [uv centralized environment implementation](https://github.com/astral-sh/uv/pull/18214)
- [uv shared-environment gap](https://github.com/astral-sh/uv/issues/20247)
- [Python venv portability warning](https://docs.python.org/3/library/venv.html)
- [Nix profiles and atomic generations](https://nix.dev/manual/nix/2.32/package-management/profiles)
- [Nix garbage-collector roots](https://nix.dev/manual/nix/2.34/package-management/garbage-collector-roots)
- [Bazel remote cache action cache and CAS](https://bazel.build/remote/caching)
- [Remote Execution APIs and content-addressable storage](https://github.com/bazelbuild/remote-apis)
- [Bazel sandboxing and undeclared-input risk](https://bazel.build/docs/sandboxing)
- [Docker/BuildKit cache layers, mounts, and external caches](https://docs.docker.com/build/cache/optimize/)
- [pnpm global virtual store for repeated worktrees](https://pnpm.io/global-virtual-store)
- [Pixi environment features, solve-groups, and manifests](https://pixi.sh/latest/reference/pixi_manifest/)
- [Flox manifest composition](https://flox.dev/docs/concepts/composition)
- [Pants process caching and hermetic execution](https://www.pantsbuild.org/stable/docs/introduction/how-does-pants-work)
- [PEX dependency/source layer separation](https://docs.pex-tool.org/recipes.html)
- [Python zipapp native-extension limitation](https://docs.python.org/3/library/zipapp.html)
- [Python Simple Repository API and artifact hashes](https://packaging.python.org/en/latest/specifications/simple-repository-api/)
- [OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md)
- [Git worktree lifecycle, locking, repair, and pruning](https://git-scm.com/docs/git-worktree)
- [Tailscale connection types and performance boundary](https://tailscale.com/docs/reference/connection-types)
- [Tailscale performance diagnostics](https://tailscale.com/docs/reference/troubleshooting/poor-performance-tailnet)
- [Tailscale least-privilege ACLs and default allow-all policy](https://tailscale.com/docs/features/access-control/acls)
- [Syncthing synchronization and conflicts](https://docs.syncthing.net/users/syncing)
- [rsync delta-transfer algorithm](https://rsync.samba.org/tech_report/node2.html)
