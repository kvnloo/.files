# Owner SSH parity and explicit owned-host onboarding

`fleet ssh` is a separate owner-user mesh, **not** the `agentjob` worker lane.
It installs reusable home-local PATH hooks and managed public-key trust files.
The helper neither discovers/adopts arbitrary tailnet peers nor edits live host
services. Machine-readable contract: `config/fleet/ssh-compatibility.json` and
`scripts/fleet-ssh requirements`.

## Boundaries

- Linux owner account: `kvn` (or another explicit non-root owner account).
  `agentjob` and Linux `root` are rejected. Its controller-only TCP2222 firewall,
  root-owned authorized keys, cgroup egress restriction and job caps stay intact.
- Phones: Linux guest node identity, not Android's VPN peer. Fake `root` is
  allowed only with `kind: phone, proot: true`; no systemd/cgroup/Android UI use.
- Existing owner keys, SSH entries and startup bodies are preserved. Managed
  `fleet-NODE` aliases do not replace `mbp`, `s22` or direct-IP entries.
- No ACL, firewall, sshd, service, user, password or BWS token changes. The helper
  has no BWS access. z0bridge owns node-local identity lifecycle and orchestration.
- Tailscale SSH on port22 is a **different authentication server** and need not
  consume OpenSSH `authorized_keys` or present an OpenSSH host key. Its ownership
  checks/approval expiry cannot be fixed by this helper. Select an existing,
  independently verified guest/owner OpenSSH endpoint; never open the worker
  lane or bypass host verification to make a matrix pass.

## Shell PATH installer

Run as the intended owner/guest account:

```sh
python3 scripts/fleet-ssh path-install --home "$HOME"
# Equivalent wrapper (requires fleet's existing PyYAML dependency):
python3 scripts/fleet ssh path-install --home "$HOME"
```

This writes `~/.config/fleet/path.sh`, `path.fish`, a managed source block at the
**start** of `.bashrc` (before interactive guards), `.profile`, existing
`.bash_profile`/`.bash_login`, and fish `conf.d/00-fleet-path.fish`. It does not
create a higher-priority bash login profile that would shadow an existing one.
Bash's SSH noninteractive startup uses `.bashrc` when built/configured to do so;
callers must verify plain SSH command execution on each real endpoint.

Existing `~/.local/bin`, `~/.npm-global/bin`, `~/.bun/bin`, `~/.cargo/bin` are
added without duplicate additions, empty PATH elements, external subprocesses or
interactive framework dependency. Spaces in HOME are supported. Directories
already on PATH keep their existing position. This installs no missing packages;
`fleet-toolchain.sh` and `/etc/fleet/toolchain.env` remain the host-build mechanism.
Fish's canonical OMF hook now sources `init.fish` only if readable, avoiding SSH
startup noise on hosts without OMF. No OMF install/network access occurs.

Identical reruns print `{"changed": []}`. Existing symlinked startup targets are
refused deliberately: update their canonical repository source instead of writing
through a link. Managed parent directories must be current-uid-owned and not
group/world writable. File replacement is atomic; concurrent helper writers are
serialized with a home-local flock. This is **not** a multi-file transaction or a
lock shared by arbitrary manual editors; do not edit these files concurrently.

## Explicit owned-host admission

Canonical `config/fleet/ssh-owned-hosts.json` starts empty and fails closed.
Membership in `nodes.yaml`, a reachable IP or `tailscale status` Peer alone is
not owner admission. Fill the separate public manifest only after approval;
`ssh-owned-hosts.example.json` contains intentionally invalid replacement markers.

Each node requires:

- safe unique `name`; `owned: true`; explicit `kind`, `user`, `address`, `port`;
- exact stable Tailscale `tailscale_id` and verified `owner_login`;
- bare unique Ed25519 `identity_public_key`, generated **on that source node**;
- bare unique Ed25519 `host_public_key`, matching `host_fingerprint` (SHA256),
  and `host_key_provenance` describing an independently authenticated verification.

Cloned identities/host keys are rejected. Obtain host keys via a trusted existing
channel or local console, **not** unauthenticated `ssh-keyscan` alone. Nonempty
provenance is an audit field, not cryptographic proof; the trusted orchestrator is
responsible for its truth. Tagged hosts are rejected until a separate explicit
ownership verifier exists. No universal BWS access token may be distributed.

The orchestrator supplies a **fresh authenticated** `tailscale status --json`
snapshot: every admitted stable ID must resolve exactly once, with matching IP
and `User.LoginName`. This helper validates the supplied evidence, not the
origin/freshness of arbitrary JSON; a new host's own self-report is not an
independent admission authority. Reject mismatches rather than rotating pins.

## Minimal integration API

The direct helper uses Python>=3.9 stdlib and POSIX flock; OpenSSH must support
Ed25519, Include and `restrict`. It is suitable for Linux and Android PRoot.
No YAML, root, shell framework, service manager or online package install needed.

```sh
# On each explicit source node, as its owner/guest account:
python3 scripts/fleet-ssh validate --manifest "$MANIFEST" --tailscale-status "$STATUS"
python3 scripts/fleet-ssh render --manifest "$MANIFEST" --node "$SOURCE"
python3 scripts/fleet-ssh path-install --home "$HOME"
python3 scripts/fleet-ssh install --manifest "$MANIFEST" --tailscale-status "$STATUS" \
  --node "$SOURCE" --home "$HOME"
python3 scripts/fleet-ssh verify --manifest "$MANIFEST" --node "$SOURCE" --home "$HOME"
```

The orchestrator must already have generated the source-local private identity
`~/.ssh/fleet/id_ed25519-SOURCE` mode0600. Private key material never appears in
the manifest. Verify derives its public key via `ssh-keygen -y` and compares it
to the admitted source identity without printing key material.

Install maintains:

- `~/.ssh/fleet/config`: owner endpoint aliases, source-local identity,
  `IdentitiesOnly`, strict pinned verification, no password/agent forwarding or
  multiplex reuse/proxies;
- `~/.ssh/fleet/known_hosts`: exact admitted host-key aliases;
- `~/.ssh/fleet/authorized_keys`: desired peer public fragment, source-IP-scoped
  with `restrict` (command execution, no PTY/forwarding);
- one managed block in actual `authorized_keys`, preserving unmanaged keys;
- a managed Include at the start of SSH config, with `Host *` context reset.

Removing a manifest peer removes only its **managed** authorization/pin/alias.
An existing unmanaged key remains authorized intentionally; inventory/revoke it
separately if that is desired. Private key deletion/rotation belongs to z0bridge.

Exit0 is success, exit1 is validation/failure; stdout is one JSON result, errors
one JSON object on stderr. `validate` without a status snapshot is only syntactic
validation (`ownership_checked: false`). `install` always requires the snapshot.
The global `fleet ssh ...` wrapper preserves existing worker commands untouched.

## Verify real outgoing edges (explicit opt-in)

```sh
python3 scripts/fleet-ssh verify --manifest "$MANIFEST" --node "$SOURCE" --probe
```

`--probe` requires the account's real HOME and uses the dedicated strict SSH
config to run `true` on every other admitted endpoint. No auth/network config is
mutated. Collect results from **every** source and aggregate the directed matrix
externally. Even successful single-source output keeps `all_to_all_verified:
false`. Offline verification proves only files and private/public identity;
`Online=false` in Tailscale status alone is not a failed reachability probe.

Connectivity is not shell parity: separately verify plain SSH `command -v pi`,
`bash -lc 'command -v pi'`, and `fish -c 'command -v pi'`, plus desired tool
versions, on each real node. Missing tools are provisioning blockers, not SSH
failures. The supervisor/phone adapter may call this API on explicit rejoin
events using approved state; it must not poll-and-admit peers or weaken pins.

## Deterministic regression tests

```sh
# Small source-fixture tests (no network, auth changes or real HOME edits):
env -u PYTHONPATH /usr/bin/python3 -m unittest discover -s tests -p test_fleet_ssh.py -v
# Fleet execution, from this worktree (no fallback onto groot):
scripts/fleet-build --node mbp --light --wait 0 -- \
  python3 -m unittest discover -s tests -p test_fleet_ssh.py -v
python3 scripts/fleet ssh requirements
git diff --check
```

Fixtures exercise HOME paths with spaces, real bash login and fish noninteractive
startup, guard ordering, absent OMF, no duplicate/empty PATH elements, idempotent
mtime preservation, Linux/PRoot admission, ownership/IP/tag mismatch rejection,
strict OpenSSH config parsing and host lookup, private/public match, drift,
symlink/writable directory refusal, existing-key preservation and managed revoke.
Fish-only test is skipped if fish is absent; a skip is not fish parity proof.
No live all-to-all enrollment is claimed by these fixtures.
