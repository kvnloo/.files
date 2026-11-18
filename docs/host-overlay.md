# Host overlay (private per-host values)

`.files` is public. Values that belong to one machine (absolute storage roots, non-default
service ports, which node runs the k3s control plane, device serials) belong in your
**private** `z0-hosts` repo, not here. `scripts/host_overlay.py` reads them at runtime.

## Set it up

The public template is [`kvnloo/z0-hosts-template`](https://github.com/kvnloo/z0-hosts-template).
A fork of a public repo cannot be private, so create your copy from the template:

```sh
gh repo create <you>/z0-hosts --private --template kvnloo/z0-hosts-template
gh repo clone <you>/z0-hosts ~/.config/z0-hosts
cp -r ~/.config/z0-hosts/hosts/example-host ~/.config/z0-hosts/hosts/<host_id>
$EDITOR ~/.config/z0-hosts/hosts/<host_id>/{host,files}.toml
python3 ~/.config/z0-hosts/scripts/validate.py
```

## How `.files` finds your values

1. The instance root is `$Z0_HOSTS_DIR`, default `~/.config/z0-hosts`.
2. `scripts/host_layout.py` resolves this machine to a `fleet.toml` host (for example
   `desktop` or `mbp`). An unknown or ambiguous hostname still fails closed there.
3. The host directory is `hosts/$Z0_HOST_ID` when that variable is set. Otherwise it is the one
   `hosts/<dir>/` that matches: its name is the fleet host, or its `host.toml` has
   `fleet_host = "<fleet host>"`, or its `match_hostnames` holds this hostname. Two matches
   fail closed (set `Z0_HOST_ID`).
4. `.files` reads `hosts/<dir>/files.toml` only.

When there is no instance, no matching directory or no `files.toml`, every value is the
neutral default:

| Key | Default |
|---|---|
| `storage.model_root` | `~/.local/share/z0` |
| `storage.workspace_root` | `~/workspace` |
| `storage.wallpaper_dir` | `$XDG_DATA_HOME/wallpapers` |
| `storage.theme_asset_root` | `$XDG_DATA_HOME/z0/themes` |
| other `storage.*` (`release_root`, `release_mount`, `offload_root`, `runs_dir`, `z0_farm_root`, `docker_data`, `containerd`, `k3s_data`, `swapfile`, `steam_library`) | empty: keep the `fleet.toml` or tool default |
| `services.<service>.<listener>` | unset: the service is not installed on this host (`0` means the same) |
| `k3s.control_plane`, `k3s.cpu_worker` | empty |

## What the reader refuses

- Keys named like an address (`ip`, `addr`, `tailnet`, `dns_name`, `fqdn`, ...) are never
  read. They are listed in `ignored`. Unknown keys and out-of-range ports are also ignored.
- A value that holds a tailnet address or a `*.ts.net` / `tail<hex>` name stops the reader
  with an error. Tools discover addresses at runtime with `tailscale ip -4` and
  `tailscale status --json`; the overlay stores none.

## Use it

```python
import host_overlay
overlay = host_overlay.resolve(ROOT)
overlay.path('model_root')           # Path, ~ and $VARS expanded; None when empty
overlay.port('dash', 'bridge_port')  # int, or None when not set on this host
```

```sh
scripts/host_overlay.py                          # JSON of the resolved values
scripts/host_overlay.py get storage.model_root   # prints the value; exit 1 when unset
```

Status: the reader is wired, but no `.files` script reads it yet. The values that are still
hard-coded in public `.files` files move to the overlay in a later change, one consumer at
a time.
