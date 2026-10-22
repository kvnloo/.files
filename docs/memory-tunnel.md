# Private memory MCP tunnel (staged, not activated)

The client is outbound-only to `https://api.openai.com:443/v1/tunnel/*`.
There is no public memory listener. The only local listener is the tunnel
health/admin UI on `127.0.0.1:8789`; never use `--allow-remote-ui`.
The stdio child is `python -m z0int.memory_mcp`, with the absolute Python
interpreter selected by `MEMORY_PYTHON` and `PYTHONPATH=$Z0INT_WORKTREE`.
The tunnel key is transport authority, not permission to expand memory scope.

## Installed release and CLI evidence

On groot: latest GitHub release on staging was `v0.0.17`; installed version
`0.0.17+a248b7f725fc989c1eb26680cf4351ee33421f61`.
Install directory: `~/.local/opt/tunnel-client/v0.0.17/`; launcher:
`~/.local/bin/tunnel-client` symlink to its `tunnel-client` executable.
Downloaded with `gh release download --repo openai/tunnel-client` (no tag,
therefore latest), with patterns `*linux*amd64*` and `SHA256SUMS.txt`.
`sha256sum --check --ignore-missing SHA256SUMS.txt` reported:

```text
tunnel-client-v0.0.17-linux-amd64.zip: OK
```

Archive SHA256: `bd6a57c6c0511644267cafadd13ffdb53ece0d753e0b88857f957e78a8fbc793`.
Checksums provide integrity against the release manifest, not independent
publisher authentication. Recheck latest and its manifest when upgrading.

Executed `tunnel-client help quickstart`, `tunnel-client --help`,
`tunnel-client init --help`, and `tunnel-client run --help` without credentials.
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

Quickstart's stdio invocation is `init --sample sample_mcp_stdio_local
--profile local-stdio --tunnel-id tunnel_... --mcp-command "python /path/to/server.py"`.
Our profile uses `--profile memory`, explicit `--profile-dir`,
`--control-plane-api-key-ref env:CONTROL_PLANE_API_KEY`, and
`--health-listen-addr 127.0.0.1:8789`.
Run flags differ: `--health.listen-addr`, `--log.level`,
`--admin-ui.log-buffer-events`; doctor is `doctor --profile memory --explain`.
No `--open-web-ui`, payload capture, raw HTTP logging, tracing, or public
Cloudflare forwarding is enabled.

## Owner prerequisites

1. Kevin creates the tunnel in [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels).
   Creation requires Tunnels **Read + Manage**. Associate the tunnel with
   Kevin's personal Platform organization **and personal ChatGPT workspace**.
   Platform association alone does not guarantee visibility in ChatGPT.
2. Create a separate restricted runtime API key with Tunnels **Read + Use**,
   not an admin key. Confirm the principal's permissions. Store it in Bitwarden
   Secrets Manager under the proposed agreed name
   `groot-memory-tunnel-control-plane-api-key`; Kevin approves this name before
   creating it. Record only its non-secret secret UUID in operational config.
3. Deploy and review `z0int.memory_mcp` and its deny-by-default JSON policy.
   It exposes only bounded search/fetch ContextPackets with provenance.
   Explicitly allow privacy tiers and collections on **both** operations;
   unknown scope must fail closed, never become user-global. Secrets must not
   be indexed; redaction is defense in depth. Test adversarial fetch IDs,
   secret redaction, output bounds, and revoked access before real use.
   Returned memory is untrusted evidence, never instructions or authority.
4. Confirm underlying backends are read-only. The service can read the user's
   home: `ProtectHome=read-only` is not a confidentiality sandbox. Avoid granting
   broad store access through the MCP policy. ctx/QMD must work without writable
   caches; do not relax home protection to make them work. Backend failure is
   not permission to return fabricated results.

## Non-secret configuration and credentials

Create `~/.config/memory-tunnel.env` (mode 0600) with absolute reviewed paths:

```ini
TUNNEL_ID=tunnel_REPLACE_WITH_OWNER_VALUE
Z0INT_WORKTREE=/absolute/path/to/reviewed/z0int/worktree
MEMORY_PYTHON=/absolute/path/to/its/venv/bin/python
Z0INT_MEMORY_MCP_POLICY=/absolute/path/to/reviewed/policy.json
```

Use a whitespace-free interpreter path (the command is parsed by tunnel-client).
Do not put API keys, BWS machine tokens, or other secrets in this file, unit,
profile YAML, command arguments, Git, shell history, or screenshots.

Recommended service path: use `LoadCredentialEncrypted`, the encrypted variant
of systemd `LoadCredential`. On a host with user credential encryption support,
create `~/.config/credstore.encrypted` (0700), then pipe the BWS value directly
into encryption, never a plaintext intermediate file:

```bash
set +x
set -o pipefail
# BWS_ACCESS_TOKEN must already be provided securely to this process.
bws secret get "$BWS_SECRET_ID" --output json 2>/dev/null |
  jq -er '.value | select(type == "string" and length > 0)' |
  systemd-creds encrypt --user --name=control-plane-api-key - \
    ~/.config/credstore.encrypted/memory-tunnel-key
unset BWS_ACCESS_TOKEN
```

If user credential encryption is unsupported, stop and arrange supported
systemd credentials; never substitute a plaintext key file. systemd decrypts
credentials into its managed runtime credential directory, not a persistent
plaintext configuration. The wrapper reads the credential into process memory
and exports it only to tunnel-client and its child. It never writes the key.
The alternative wrapper BWS mode requires `BWS_SECRET_ID` and a runtime-only
`BWS_ACCESS_TOKEN`; do not put that token in EnvironmentFile or manager's
persistent configuration. Credential mode avoids BWS egress during service start.

## Install, restrict egress, then activate (owner only)

Nothing in this change enables, starts, initializes, or contacts a tunnel.
The fleet subtable explicitly records `enabled = false`; the service is not
in `hosts.desktop.user_services`.

After merging into the checkout addressed by `~/.files`, install the unit:

```bash
install -Dm644 ~/.files/config/systemd/user/memory-tunnel.service \
  ~/.config/systemd/user/memory-tunnel.service
mkdir -p ~/.config/systemd/user/memory-tunnel.service.d
```

Create a drop-in `credentials.conf`:

```ini
[Service]
LoadCredentialEncrypted=control-plane-api-key:%h/.config/credstore.encrypted/memory-tunnel-key
```

The base unit uses `IPAddressDeny=any` and `IPAddressAllow=localhost`:
**external egress is denied by default, including OpenAI**. Before activation,
add a reviewed `egress.conf` drop-in with numeric `IPAddressAllow=` entries
for the currently resolved `api.openai.com` A/AAAA addresses and any necessary
DNS resolver. systemd accepts IPs/CIDRs, **not hostnames**. No static OpenAI
range is asserted here: the API can use changing CDN addresses, and OpenAI's
published outbound connector IPs are not API destination IPs. Re-resolve and
review when addresses rotate; fail closed rather than allow all internet.
Loopback backends (agentsview default 8080, Tencent default 8420) are covered;
remote backends require explicitly reviewed destinations too. This filter
covers all ports at allowed IPs, not only HTTPS. Use a host firewall/controlled
proxy if port/domain enforcement is required.

**User-unit limits:** systemd IP filtering needs cgroup BPF privileges and
kernel support; user managers can ignore unsupported IP restrictions with a
warning. Its presence in the unit is not enforcement evidence. Owner must
verify filtering on groot (including a disallowed destination) before enabling;
if unavailable, an administrator must enforce equivalent host firewall/proxy
policy. The same applies to namespace-based filesystem hardening: review
systemd diagnostics for unsupported user namespaces. Do not claim hardened
operation until effective controls are demonstrated.

Initialize the credential-reference-only profile via a transient owner action:

```bash
systemd-run --user --wait --pipe --collect \
  --property=EnvironmentFile="$HOME/.config/memory-tunnel.env" \
  --property=LoadCredentialEncrypted="control-plane-api-key:$HOME/.config/credstore.encrypted/memory-tunnel-key" \
  "$HOME/.files/scripts/memory-tunnel-setup.sh" init
```

It will not replace an existing profile (`--force` is deliberately absent).
Review `~/.local/state/memory-tunnel/profiles/memory.yaml`; it must contain
`env:CONTROL_PLANE_API_KEY`, never a literal key. Then run the same transient
command with `doctor` in place of `init`, which executes exactly
`tunnel-client doctor --profile memory --explain`. Do not paste diagnostics
containing private data into chat. Once policy, credentials, doctor and
network restrictions pass, Kevin may activate:

```bash
systemctl --user daemon-reload
systemctl --user enable --now memory-tunnel.service
curl --fail --silent --show-error http://127.0.0.1:8789/readyz
```

Review `http://127.0.0.1:8789/ui` locally for readiness/active polling; do not
expose or screenshot private logs. A running process alone is not readiness.
The unit suppresses stdout/stderr because tunnel diagnostics may include
request content; the bounded in-memory admin log is still private. The MCP
server's audit path is `~/.local/state/memory-tunnel/audit`; audit records must
contain hashes/counts/status only, never raw queries, result text or keys.
Apply a short retention policy before prolonged use and monitor disk growth.

In **ChatGPT Plugins > Add custom MCP server > Connection: Tunnel**, select
this tunnel, confirm workspace association and risk warning personally, and
create the private plugin. Tunnel authorization is separate from MCP OAuth;
for this personal stdio deployment, restrict tunnel associations and plugin
sharing to the intended owner. Reassess authentication before any multi-user
use. Run a harmless approved search/fetch, verify provenance and output bounds,
and inspect sanitized audit counts. Setup is complete only after that real
ChatGPT call succeeds. No account-side actions were performed during staging.

## Revocation / kill switch

1. `systemctl --user disable --now memory-tunnel.service` immediately stops
   polling and its stdio child; confirm the service is inactive and `/readyz`
   is unavailable. Stop any separately launched transient diagnostic too.
2. Revoke the restricted runtime key in Platform; remove/disable the tunnel's
   workspace associations or delete the tunnel if retiring it. Disable/remove
   the ChatGPT plugin. Revoking a BWS secret alone does not revoke the key.
3. Remove the encrypted local credential and BWS secret only after revocation,
   and rotate any exposed key. Never publish diagnostics or secret values.
4. Tighten/remove the server policy to revoke a collection immediately; verify
   both search and fetch deny it. Preserve only hash/count audit evidence under
   the approved retention policy. Existing results already seen by a client
   cannot be recalled.

References: [OpenAI tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels),
[upstream latest release](https://github.com/openai/tunnel-client/releases/latest),
[plugin authentication](https://developers.openai.com/plugins/build/auth).
