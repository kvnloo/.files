# passd remote custody

Groot, tailnet name `0`, holds the encrypted vault and master key.
Its systemd user gateway binds only `100.113.138.100:55460`, following the
frontier-kb pattern. Agents connect directly over Tailscale and hold only
machine tokens. No Tailscale serve, ACL edits, sudo, or cluster deployment.
Machine identity grants zero leases; agents request typed operations,
and the user approves an exact TTL and use budget on groot.

## Install

On groot, from `~/workspace/.files`:

```bash
scripts/proton-pass-install.sh --plan
scripts/proton-pass-install.sh
scripts/passd-install.sh --custody --plan
scripts/passd-install.sh --custody
```

The Proton installer keeps Proton's entitlement check and default features.
Installers back up regular files before replacing them with links.
They never start services. `--skip-build` installs just the Proton links.

The user runs these on groot, using the same master password for both prompts:

```bash
secret-tool store --label='passd master password' service org.passd key master-password
~/.local/bin/passd init
systemctl --user daemon-reload
systemctl --user start passd.service
~/.local/bin/passd sync import-proton /path/to/export.zip
rm -- /path/to/export.zip
systemctl --user enable --now passd.service passd-gateway.service
```

Import uses the running local daemon. The ZIP is an unencrypted snapshot:
delete it after import.
Secret Service must be unlocked in the graphical session. The service stages
the password in a 0600 runtime tmpfs file and removes it when it stops.
Same-uid processes can read that file; see passd's `REMOTE_CUSTODY.md`.

On mbp or another agent host, run `scripts/passd-install.sh` without `--custody`.
The user creates a machine token on groot with `passd agent create mbp`,
then securely sets `PASSD_AGENT_TOKEN` and `PASSD_REMOTE=100.113.138.100:55460`
on mbp. Define capabilities and approve/deny/revoke on groot via its local
Unix socket with `PASSD_REMOTE` and `PASSD_AGENT_TOKEN` unset.
Do not copy the master password, database, or Proton export to mbp.

Run `scripts/passd-remote-e2e.sh` from mbp for the dummy-only milestone test.
It uses a disposable store, port 55461, raw gateway-response capture, and a
62-second expiry wait. SSH supervises cleanup; no real vault is opened.
The optional `~/.config/passd/gateway.env` can override the gateway listen
address; keep it on groot's tailnet IP.

## Why not kind

A kind node shares the custody host kernel, and etcd is unencrypted by default.
Custody stays outside agent-reachable clusters. If hermes-lab pods ever need
access, use a selectorless Service to the host, like z0intelligence
`deploy/lab/up`, while retaining passd's machine-token and lease checks.

## Known gaps

Groot also runs hermes/omp agents. A dedicated OS user is recommended and needs
sudo to provision; it still cannot protect custody from hostile host root.
The custody host must not run coding agents for the remote-custody guarantee.
There are no signed phone approvals or hardware unlock yet. Proton snapshot
import is one-way; it does not keep Proton and passd continuously synchronized.
