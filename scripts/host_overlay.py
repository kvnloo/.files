#!/usr/bin/env python3
"""Private per-host values for .files, read from the user's z0-hosts instance.

The instance is a private repo made from the public template kvnloo/z0-hosts-template
(docs/host-overlay.md). This reader loads hosts/<id>/files.toml for the fleet host that
scripts/host_layout.py resolves. With no instance, or no directory for this host, every
value is the neutral default below. Address-shaped keys (ip, addr, tailnet, dns_name, ...)
are never read: addresses are discovered at runtime with `tailscale ip -4` and
`tailscale status --json`.

CLI:
  scripts/host_overlay.py                 # JSON of the resolved overlay
  scripts/host_overlay.py get storage.model_root
  scripts/host_overlay.py get services.dash.bridge_port
"""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import socket
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_layout  # noqa: E402

COMPONENT = 'files'
DEFAULT_DIR = Path('~/.config/z0-hosts')
# Neutral defaults: "" means "not set here; keep the fleet.toml or tool default".
DEFAULTS = {
    'storage': {
        'model_root': '~/.local/share/z0',
        'workspace_root': '~/workspace',
        'release_root': '',
        'release_mount': '',
        'offload_root': '',
        'runs_dir': '',
        'z0_farm_root': '',
        'docker_data': '',
        'containerd': '',
        'k3s_data': '',
        'swapfile': '',
        'steam_library': '',
        'wallpaper_dir': '$XDG_DATA_HOME/wallpapers',
        'theme_asset_root': '$XDG_DATA_HOME/z0/themes',
    },
    'k3s': {'control_plane': '', 'cpu_worker': ''},
}
ADDRESS_KEY = re.compile(
    r'(?i)(^|_)(ip|ip4|ip6|ipv4|ipv6|addr|address|cidr|tailnet|tailscale_ip|magicdns|dns_name|fqdn)(_|$)')
TAILNET_V4 = re.compile(r'(?<![\d.])100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}(?!\d)')
TAILNET_NAME = re.compile(r'(?i)\.ts\.net\b|\btail[0-9a-f]{4,}\b')


@dataclass(frozen=True)
class HostOverlay:
    fleet_host: str                 # fleet.toml host id from host_layout.resolve
    overlay_id: str | None          # hosts/<overlay_id>/ in the instance, None = defaults only
    source: Path | None             # files.toml that was read, None when absent
    storage: dict
    services: dict                  # {service: {listener: port}}; ports > 0 only
    k3s: dict
    ignored: tuple = field(default=())  # keys dropped: address-shaped or unknown

    def path(self, key, home=None):
        """storage[key] as an absolute Path (~ against home, $VARS from the environment), or None."""
        value = self.storage.get(key) or ''
        if not value:
            return None
        home = Path(home) if home else Path.home()
        if value == '~' or value.startswith('~/'):
            value = str(home) + value[1:]
        return Path(os.path.expandvars(value))

    def port(self, service, listener='port'):
        """Port of services.<service>.<listener>, or None when not set on this host."""
        return (self.services.get(service) or {}).get(listener)

    def as_dict(self):
        return {'fleet_host': self.fleet_host, 'overlay_id': self.overlay_id,
                'source': str(self.source) if self.source else None, 'storage': self.storage,
                'services': self.services, 'k3s': self.k3s, 'ignored': list(self.ignored)}


def hosts_dir(env=None):
    env = os.environ if env is None else env
    raw = env.get('Z0_HOSTS_DIR') or ''
    return Path(raw).expanduser() if raw else DEFAULT_DIR.expanduser()


def _toml(path):
    try:
        return tomllib.loads(path.read_text())
    except FileNotFoundError:
        return {}


def find_overlay_dir(instance, fleet_host, hostname, env=None):
    """hosts/<id>/ for this machine, or None. More than one candidate fails closed."""
    env = os.environ if env is None else env
    hosts = Path(instance) / 'hosts'
    if not hosts.is_dir():
        return None
    if env.get('Z0_HOST_ID'):
        chosen = hosts / env['Z0_HOST_ID']
        return chosen if chosen.is_dir() else None
    matches = []
    for d in sorted(p for p in hosts.iterdir() if p.is_dir()):
        meta = _toml(d / 'host.toml')
        if d.name == fleet_host or meta.get('fleet_host') == fleet_host \
                or hostname in (meta.get('match_hostnames') or []):
            matches.append(d)
    if len(matches) > 1:
        names = ', '.join(d.name for d in matches)
        raise ValueError(f'z0-hosts: fleet host {fleet_host!r} matches more than one host directory: {names}; '
                         'set Z0_HOST_ID')
    return matches[0] if matches else None


def _refuse_addresses(value, where):
    if isinstance(value, str) and (TAILNET_V4.search(value) or TAILNET_NAME.search(value)):
        raise ValueError(f'z0-hosts: {where} holds a tailnet address or name; '
                         'remove it (addresses are discovered at runtime)')
    if isinstance(value, list):
        for i, item in enumerate(value):
            _refuse_addresses(item, f'{where}[{i}]')


def _section(raw, name, defaults, ignored):
    out = dict(defaults)
    for key, value in (raw.get(name) or {}).items():
        where = f'{name}.{key}'
        if ADDRESS_KEY.search(key) or key not in defaults or not isinstance(value, str):
            ignored.append(where)
            continue
        _refuse_addresses(value, where)
        out[key] = value
    return out


def _services(raw, ignored):
    out = {}
    for service, listeners in (raw.get('services') or {}).items():
        if ADDRESS_KEY.search(service) or not isinstance(listeners, dict):
            ignored.append(f'services.{service}')
            continue
        for listener, port in listeners.items():
            where = f'services.{service}.{listener}'
            if ADDRESS_KEY.search(listener) or isinstance(port, bool) or not isinstance(port, int) \
                    or not 0 <= port <= 65535:
                ignored.append(where)
            elif port:
                out.setdefault(service, {})[listener] = port
    return out


def resolve(root, hostname=None, home=None, env=None):
    """Overlay for the fleet host this machine resolves to; defaults when there is none."""
    hostname = hostname or socket.gethostname()
    fleet_host = host_layout.resolve(root, hostname=hostname, home=home).host_id
    instance = hosts_dir(env)
    host_dir = find_overlay_dir(instance, fleet_host, hostname, env)
    source = host_dir / f'{COMPONENT}.toml' if host_dir else None
    raw = _toml(source) if source else {}
    if source and not source.is_file():
        source = None
    ignored = [f'<top>.{key}' for key in raw if key not in ('storage', 'services', 'k3s')]
    storage = _section(raw, 'storage', DEFAULTS['storage'], ignored)
    k3s = _section(raw, 'k3s', DEFAULTS['k3s'], ignored)
    services = _services(raw, ignored)
    return HostOverlay(fleet_host, host_dir.name if host_dir else None, source,
                       storage, services, k3s, tuple(ignored))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = Path(__file__).resolve().parents[1]
    try:
        overlay = resolve(root)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not argv:
        print(json.dumps(overlay.as_dict(), indent=2, sort_keys=True))
        return 0
    if argv[0] != 'get' or len(argv) != 2:
        print('usage: host_overlay.py [get <section>.<key>[.<listener>]]', file=sys.stderr)
        return 2
    node = overlay.as_dict()
    for part in argv[1].split('.'):
        if not isinstance(node, dict) or part not in node:
            return 1  # unset: print nothing, exit 1, so shell callers can fall back
        node = node[part]
    if node in ('', None):
        return 1
    print(node if not isinstance(node, (dict, list)) else json.dumps(node))
    return 0


if __name__ == '__main__':
    sys.exit(main())
