# Migration: private network overlay

This repo no longer names a real tailnet address or tailnet name. Everything that
needs one reads the untracked private overlay instead:

    ${DOTFILES_PRIVATE_DIR:-~/.config/dotfiles}/private.env          KEY=VALUE
    ${DOTFILES_PRIVATE_DIR:-~/.config/dotfiles}/hosts.private.yaml   per-node data

Both names are in `.gitignore`. `config/private.example.env` and
`config/hosts.private.example.yaml` document every key with reserved example
values. systemd units always read `%h/.config/dotfiles/private.env`, so if you set
`DOTFILES_PRIVATE_DIR`, also symlink that path to your directory.

A missing key is an error that names the key and the file. Nothing falls back to a
built-in address.

## 1. Write the overlay first (before deploying this change)

Write it on groot (everything), and on every machine where `scripts/onboard run
core-links` linked `~/.config/tern/hosts.names` (mbp). Phones need no overlay:
`fleet-phone-setup.sh` installs an already-filled `hosts.names` on them.

`~/.config/dotfiles/private.env` (mode 0600). Replace each `<fill>` with the value
that was previously hard-coded in this repo. Don't write real values anywhere in
the repo.

```sh
install -d -m 0700 ~/.config/dotfiles
install -m 0600 /dev/null ~/.config/dotfiles/private.env
cat > ~/.config/dotfiles/private.env <<'EOF'
# groot: k3s server, Dash bridge/Metro, z0 farm llama.cpp router, LumenFold fallback,
# service-watch local triage route, k3s smoke-job targets, Tern sidebar
GROOT_TAILNET_IP=<fill>
# mbp: fleet host lane, Tern sidebar
MBP_TAILNET_IP=<fill>
# omarchy-phone (S25 Ultra): Omarchy/PRoot guest node, Android Tailscale app node
S25_TAILNET_IP=<fill>
S25_ADB_HOST=<fill>
# galaxy-s22plus (S22+): localhost-0 guest node, Android Tailscale app node
S22_TAILNET_IP=<fill>
S22_ADB_HOST=<fill>
# lenovo-tab: Android Tailscale app node
TAB_TAILNET_IP=<fill>
# MagicDNS suffix (docs/operator commands only), the part after the host label in <host>.<tailnet>.ts.net
TAILNET_DOMAIN=<fill>
EOF
```

Where each value came from on `master` before this change:

| Key | Previously in |
|-----|---------------|
| GROOT_TAILNET_IP | `config/fleet/nodes.yaml` groot `tailnet_ip`; `config/dash-services/*.env`; `config/systemd/user/z0-farm-llama.service` |
| MBP_TAILNET_IP | `config/fleet/nodes.yaml` mbp `tailnet_ip` |
| S25_TAILNET_IP | `config/fleet/nodes.yaml` omarchy-phone `tailnet_ip` |
| S25_ADB_HOST | `config/fleet/nodes.yaml` omarchy-phone `android.adb_host` |
| S22_TAILNET_IP | `config/fleet/nodes.yaml` galaxy-s22plus `tailnet_ip` |
| S22_ADB_HOST | `config/fleet/nodes.yaml` galaxy-s22plus `android.adb_host` |
| TAB_TAILNET_IP | `config/fleet/nodes.yaml` lenovo-tab `tailnet_ip` (same value as its `adb_host`) |
| TAILNET_DOMAIN | `docs/SETUP.md` (the MagicDNS suffix in the phone's Tern login) |

`~/.config/dotfiles/hosts.private.yaml` needs no filling. Its strings are
`${KEY}` references into `private.env`, so copy the example as it is:

```sh
install -m 0600 config/hosts.private.example.yaml ~/.config/dotfiles/hosts.private.yaml
```

(the copy holds exactly this mapping)

```yaml
nodes:
  groot:          {tailnet_ip: ${GROOT_TAILNET_IP}}
  mbp:            {tailnet_ip: ${MBP_TAILNET_IP}}
  omarchy-phone:  {tailnet_ip: ${S25_TAILNET_IP}, android: {adb_host: ${S25_ADB_HOST}}}
  galaxy-s22plus: {tailnet_ip: ${S22_TAILNET_IP}, android: {adb_host: ${S22_ADB_HOST}}}
  lenovo-tab:     {tailnet_ip: ${TAB_TAILNET_IP}, android: {adb_host: ${TAB_TAILNET_IP}}}
```

Verify. Values are never printed, and the command exits 0 only when every key is set:

```sh
scripts/private-overlay check
scripts/fleet nodes        # every node resolves; no "missing private host value" error
```

## 2. Deploy, then restart these

groot, systemd user units:

| Unit | How | Why |
|------|-----|-----|
| `z0-farm-llama.service` | `scripts/apply-z0-farm` (copies the unit and restarts it) | `EnvironmentFile=` + `--host ${GROOT_TAILNET_IP}` |
| `lumenfold-tailnet-fallback.service` | `systemctl --user daemon-reload && systemctl --user restart lumenfold-tailnet-fallback.service` | same |
| `dash-bridge.service`, `dash-metro.service`, `dash-metro-relay.service` | `scripts/install-dash-services --dash-repo <dash checkout> --activate`, then `systemctl --user restart` the three | env files are now rendered from the overlay at install time |
| `service-watch.service` | `systemctl --user restart service-watch.service` (after the files-live release updates) | local llama route from the overlay |
| `dash-log-watch.service` | `systemctl --user restart dash-log-watch.service` | approved phone address from the overlay |
| `host-drift.timer` | `scripts/install-host-drift --apply` | ships `private_overlay.py`; compares rendered dash env files |
| `artifact-leases.timer` | `scripts/install-artifact-leases.sh --activate` | ships `private_overlay.py`; S25 guest address |
| `host-optimizer.path` (fleet-steward) | `scripts/apply-agent-oom` | closure includes `private_overlay.py` |
| `tern-hosts-sync.timer` | `systemctl --user start tern-hosts-sync.service` once | `hosts.names` now holds `${...}` references |

Phones: re-run `scripts/fleet-phone-setup.sh root@<guest-ip> ...` (or
`scripts/fleet enroll <node>`) so each guest gets the filled `hosts.names`. The
running `tern-hosts` runsv service rereads that file every 120 s. A restart is only
needed to pick up the new `tern-hosts-sync` code (`sv restart` that service).

mbp: once the repo is pulled, run `tern-hosts-sync` once.

Git hooks: run `scripts/setup-phone-caps-hooks.sh` again so the stamped pre-commit
hook includes `scripts/public-leak-check`.

k3s smoke jobs that probe groot's address now go through the renderer:
`scripts/private-overlay render config/k3s/smoke/isolation-job.yaml | kubectl create -f -`.
`scripts/setup-k3s.sh admit` does this on its own.

## 3. Leak guard

`scripts/public-leak-check --skip personal-path,mount-path,personal-email` runs in
`.githooks/pre-commit` and in `.github/workflows/public-leak-check.yml`. To check the
tree against your real values too, without writing them down:

```sh
scripts/public-leak-check --skip personal-path,mount-path,personal-email \
  --denylist <(sed -n 's/^[A-Z0-9_]*=//p' ~/.config/dotfiles/private.env)
```

Git history still holds the old values. Removing them would need a history rewrite
and a force-push of this public repo. That is the owner's decision and is not part
of this change.
