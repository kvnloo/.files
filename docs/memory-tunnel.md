# Private memory tunnel — staged, disabled

No tunnel was initialized with real credentials, started, or enabled. No account
settings changed. Fleet records a staged service, not an enabled user service.

## Verified client and flags

Installed latest release `v0.0.17` at `~/.local/opt/tunnel-client/v0.0.17/`, with
`~/.local/bin/tunnel-client` symlink. `--version` returned
`0.0.17+a248b7f725fc989c1eb26680cf4351ee33421f61`.
Downloaded using `gh release download --repo openai/tunnel-client` with no tag
(latest at staging), patterns `*linux*amd64*` and `SHA256SUMS.txt`.
For reproducible reinstalls use `gh release download v0.0.17 --repo
openai/tunnel-client --pattern tunnel-client-v0.0.17-linux-amd64.zip
--pattern SHA256SUMS.txt`.

`sha256sum --check --ignore-missing SHA256SUMS.txt` reported
`tunnel-client-v0.0.17-linux-amd64.zip: OK` (all other downloaded assets also OK).
Archive SHA256:
`bd6a57c6c0511644267cafadd13ffdb53ece0d753e0b88857f957e78a8fbc793`.
`gh attestation verify <zip> --repo openai/tunnel-client` exited 0;
JSON verification also exited 0 and contained the release workflow certificate
`.github/workflows/release.yml@refs/tags/v0.0.17`. Fleet pins tag and hash.
The bundled `cloudflared` executable was removed from the installed release;
it is unused. No Cloudflare supervision flags or public forwarding are enabled.

Executed `help quickstart`, `--help`, `init --help`, and `run --help`.
Root flags: `-h/--help`, `-v/--version`. Exact init flags:

```text
--control-plane-api-key-ref string (default env:CONTROL_PLANE_API_KEY)
--control-plane-base-url string (default https://api.openai.com)
--control-plane-url-path string
--force
--health-listen-addr string (default 127.0.0.1:8080)
-h, --help
--mcp-command string
--mcp-server-url string
--open-web-ui
--profile string (default sample_mcp_with_dcr)
--profile-dir string
--sample string
--tunnel-id string
```

Quickstart uses `init --sample sample_mcp_stdio_local --profile local-stdio
--tunnel-id tunnel_... --mcp-command "python /path/to/server.py"`.
Our profile is `memory`, with explicit profile directory, key reference
`env:CONTROL_PLANE_API_KEY`, and loopback health listener `127.0.0.1:8789`.
Run uses `--health.listen-addr`, `--log.level`, `--admin-ui.log-buffer-events`.
`run --help` exposes Harpoon target flags but no Harpoon-disable flag.
A dry init with fake tunnel ID and no key succeeded in `/tmp`; its generated
stdio YAML contains only control_plane, health, admin_ui, log and one mcp
command. The strict validator accepts only that canonical schema and exact
command; any extra YAML, HTTP targets, Harpoon, duplicate keys, aliases or key
literal are rejected. Init, run and ExecStartPre all validate the profile.
The runtime environment is cleared of configuration overrides before exec.

Staging security assessment: `systemd-analyze --user security <absolute-unit-path>`
refused an uninstalled unit. The supported offline invocation
`systemd-analyze --offline=yes --user security <absolute-unit-path>` completed
with **6.5 MEDIUM**. This is a static exposure score, not runtime enforcement
proof. The strict validator accepted the dry-generated sample with its exact
expected command. No real unit was installed or started for these checks.

## Owner steps: account and policy

1. Kevin creates the tunnel in [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels),
   requiring Tunnels **Read + Manage**, associated with his personal Platform
   organization **and personal ChatGPT workspace**. Organization association
   alone does not guarantee ChatGPT visibility.
2. Create a separate restricted runtime key with Tunnels **Read + Use**, not an
   admin key. Proposed BWS name (Kevin approves before creation):
   `groot-memory-tunnel-control-plane-api-key`. Store it in Bitwarden Secrets
   Manager, record only its non-secret UUID locally.
3. Review and install the memory server and explicit deny-by-default JSON
   policy. Only bounded read-only search/fetch ContextPackets with provenance;
   enforce collection/privacy-tier allowlists on both operations. Unknown scope
   never becomes user-global. Never index secrets; redact as defense in depth.
   Evidence is not authority: returned memories remain untrusted data.
4. Test ACL bypass, guessed fetch IDs, secret redaction, output bounds and
   revocation before exposing real memory. Underlying stores remain separate;
   ctx/QMD must run read-only, without writable cache exceptions.

## Pinned deployment and non-secret configuration

Use a dedicated detached checkout of an approved full z0int commit, not a live
worktree. Install dependencies in a dedicated pinned venv (including the
server's `mcp==1.26.0` requirement); its Python must support `-P` (3.11+).
Make the deployment and venv read-only after installation. The service's
ProtectHome/ProtectSystem mounts enforce read-only access inside its namespace;
same-user processes outside that sandbox can still alter user-owned files, so
this is not isolation from a malicious host account. For stronger integrity,
have an administrator own the deployment root. The wrapper checks exact HEAD,
detached state and a clean checkout on every invocation. It cannot establish
root ownership or dependency provenance; owner review is still required.

Create mode-0600 `~/.config/memory-tunnel.env`, containing no secrets:

```ini
TUNNEL_ID=tunnel_OWNER_VALUE
Z0INT_WORKTREE=/absolute/path/to/pinned/detached/z0int
Z0INT_COMMIT=FULL_REVIEWED_COMMIT_SHA
MEMORY_PYTHON=/absolute/path/to/pinned/venv/bin/python
Z0INT_MEMORY_MCP_POLICY=/absolute/path/to/reviewed/policy.json
```

Paths must contain only letters, digits, `_`, `.`, `/`, `-`. The stdio command
uses `/usr/bin/env -i` with an explicit allowlist, then the pinned Python with
`-P -m z0int.memory_mcp`. No control-plane key, BWS variables, provider keys,
SSH agent or shell environment reaches the child. PYTHONPATH points only at the
pinned deployment; working directory is an empty service state subdirectory.
Audit path is `~/.local/state/memory-tunnel/audit`. Audit contains only
hashes/counts/status, never raw queries/results or secrets; arrange short
retention and monitor growth before prolonged use.

## Credentials: encrypted systemd only

Do not put secrets in Git, command arguments, profiles, environment files,
shell history, logs or screenshots. BWS is used only during provisioning;
there is no BWS runtime branch. Runtime requires LoadCredentialEncrypted.
Create `~/.config/credstore.encrypted` mode 0700, supply BWS_ACCESS_TOKEN through
a secure process environment, then pipe directly to encryption:

```bash
set +x
set -o pipefail
bws secret get "$BWS_SECRET_ID" --output json 2>/dev/null |
  jq -er '.value | select(type == "string" and length > 0)' |
  systemd-creds encrypt --user --name=control-plane-api-key - \
    ~/.config/credstore.encrypted/memory-tunnel-key
unset BWS_ACCESS_TOKEN
```

If user encryption is unsupported, stop and arrange supported credentials;
never create a persistent plaintext key. systemd decrypts into its managed
runtime credential directory. The wrapper exports the key only to the tunnel
process; its `env -i` stdio command excludes it from MCP and backend children.

## Install, enforce network boundaries, activate

After merging into the checkout addressed by `~/.files`:

```bash
install -Dm644 ~/.files/config/systemd/user/memory-tunnel.service \
  ~/.config/systemd/user/memory-tunnel.service
mkdir -p ~/.config/systemd/user/memory-tunnel.service.d
mkdir -p ~/.local/state/memory-tunnel/empty
chmod 700 ~/.local/state/memory-tunnel ~/.local/state/memory-tunnel/empty
```

Create `credentials.conf` drop-in:

```ini
[Service]
LoadCredentialEncrypted=control-plane-api-key:%h/.config/credstore.encrypted/memory-tunnel-key
```

Base network policy is deny-any with loopback allowed at the systemd IP layer.
Add numeric reviewed `IPAddressAllow=` entries in an egress drop-in for current
`api.openai.com` A/AAAA destinations and necessary DNS resolver. systemd accepts
IPs/CIDRs, not hostnames; API CDN addresses rotate. OpenAI published outbound
connector ranges are not API destination ranges. No broad internet allowance.

**Port-level enforcement is mandatory:** systemd IPAddressAllow cannot narrow
ports. Before activation, an administrator must install cgroup/UID-scoped
firewall or controlled proxy rules allowing only API HTTPS, necessary resolver,
loopback agentsview TCP 8080 and Tencent TCP 8420, and health TCP 8789 as needed.
Other backend ports need explicit review. All other loopback ports and IPv4/IPv6
external destinations must be rejected with EPERM/EACCES semantics. The service
preflight probes prohibited Cloudflare DNS IPs on 443 and loopback port 1 on
both IPv4 and IPv6, and refuses startup unless every connect fails with an
explicit permission error. Timeouts, ENETUNREACH and ECONNREFUSED are NOT proof.
The tests are negative controls, not exhaustive firewall verification; review
the actual rule set as well. DROP-only firewalls will intentionally fail this
gate. Do not permit the probe addresses in the destination list.

User managers may lack cgroup BPF support; an ignored IPAddressDeny directive
must never be interpreted as protection. The active preflight catches missing
negative controls and fails closed. Namespace hardening also requires supported
user namespaces. Verify effective restrictions on groot, not merely unit text.
AF_UNIX is denied; runtime bus, systemd, Tern, ssh-agent, Docker and GnuPG paths
are additionally inaccessible. Native journald stderr is an inherited fd, so
wrapper errors still work without opening a new AF_UNIX socket. Raw tunnel
stderr/stdout are discarded; safe wrapper/validator failures reach the journal.
This avoids a systemd-cat AF_UNIX dependency. Host services reachable on allowed
backend ports remain a trust boundary, not arbitrary MCP callout targets.

Initialize the key-reference-only profile via an owner-run transient action:

```bash
systemd-run --user --wait --pipe --collect \
  --property=EnvironmentFile="$HOME/.config/memory-tunnel.env" \
  --property=LoadCredentialEncrypted="control-plane-api-key:$HOME/.config/credstore.encrypted/memory-tunnel-key" \
  "$HOME/.files/scripts/memory-tunnel-setup.sh" init
```

Existing profiles are not overwritten. Inspect the YAML: key must be exactly
`env:CONTROL_PLANE_API_KEY`, sole upstream the reviewed stdio command. Repeat the
transient command with `doctor` instead of `init`; it executes exactly
`tunnel-client doctor --profile memory --explain`. Do not paste private
observations. Once credentials/policy/network restrictions and doctor pass:

```bash
systemctl --user daemon-reload
systemctl --user enable --now memory-tunnel.service
curl --fail --silent --show-error http://127.0.0.1:8789/readyz
```

Inspect `http://127.0.0.1:8789/ui` locally for readiness and active polling.
Never allow remote UI or expose it publicly. In **ChatGPT Plugins > Add custom
MCP server > Connection: Tunnel**, select the same tunnel and personally accept
the warning. Restrict plugin sharing/associations to Kevin; tunnel permissions
are not MCP OAuth, so reassess authentication for any multi-user scope.
Make an approved harmless search/fetch and inspect provenance, bounds and
sanitized audit counts. Only that real ChatGPT call establishes completion.

## Kill switch and revocation

1. `systemctl --user disable --now memory-tunnel.service`; use
   `systemctl --user kill --kill-whom=all --signal=KILL memory-tunnel.service`
   if cgroup processes remain. Stop transient diagnostics separately.
2. Mask the unit to block accidental restart. Since an installed regular user
   unit can prevent `mask`, first remove only the installed unit file (retain
   the repo source), then run `systemctl --user mask memory-tunnel.service`.
   Verify inactive state and unavailable `/readyz`. Inspect remaining processes
   and kill only positively identified tunnel/MCP children, never unrelated
   Python/client processes. Do not use broad pkill.
3. Revoke the runtime key in Platform and remove workspace associations/delete
   the tunnel if retiring it; disable/remove the ChatGPT plugin. Deleting the
   BWS secret alone does not revoke the API key.
4. Remove `~/.local/state/memory-tunnel/profiles/memory.yaml`, encrypted local
   credential, and BWS secret after revocation. Rotate any exposed key.
5. Remove collection grants in the server policy and verify search AND fetch
   deny them. Retain only approved hash/count audit evidence. Already-returned
   client memory cannot be recalled.

References: [tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels),
[latest release](https://github.com/openai/tunnel-client/releases/latest),
[plugin auth](https://developers.openai.com/plugins/build/auth).
