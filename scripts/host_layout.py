"""Per-host managed-path layout from fleet.toml; installers never hard-code one host."""
from dataclasses import dataclass
import os
from pathlib import Path
import socket
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_admission import Hosts, LINK, Live, Mount, Parent, Reason, decide, hosts_from_count  # noqa: E402

MESSAGES = {
    Reason.NO_HOST: 'matched no fleet host',
    Reason.AMBIGUOUS_HOST: 'matched more than one fleet host',
    Reason.NO_MANIFEST: 'declares no config/host manifest',
    Reason.THROUGH_CHECKOUT: 'live path resolves through checkout directory link',
    Reason.CHANGED: 'live file changed since inventory; preserve and investigate',
    Reason.UNMOUNTED: 'bulk release storage is not mounted',
}


def admit(subject, hosts=Hosts.ONE, manifest=True, parent=Parent.REAL, live=Live.ABSENT,
          mount=Mount.NOT_DECLARED, fresh=False):
    """Raise unless the Bend-proven decision links; every installer refusal goes through here."""
    verdict = decide(hosts, manifest, parent, live, mount, fresh)
    if verdict != LINK:
        raise ValueError(f'{MESSAGES[verdict]}: {subject}')


@dataclass(frozen=True)
class HostLayout:
    host_id: str
    manifest: str  # repo-relative host manifest
    release_root: Path | None  # physical <family>/<digest> trees; None keeps home-local stamps
    release_mount: Path | None  # must be a mount point before a new physical tree is staged
    operations_root: Path | None = None  # report-only operations state (service-watch, host hygiene)


def resolve(root, hostname=None, home=None):
    """Exactly one fleet host must match; an unknown or ambiguous host fails closed."""
    hostname = hostname or socket.gethostname()
    home = Path(home) if home else Path.home()
    fleet = tomllib.loads((Path(root) / 'fleet.toml').read_text())
    matches = [(host_id, cfg) for host_id, cfg in (fleet.get('hosts') or {}).items()
               if hostname == host_id or hostname in (cfg.get('match_hostnames') or [])]
    admit(f'hostname {hostname!r}', hosts=hosts_from_count(len(matches)))
    host_id, cfg = matches[0]
    manifest = cfg.get('manifest')
    admit(f'fleet host {host_id!r}', manifest=(
        isinstance(manifest, str) and not Path(manifest).is_absolute() and '..' not in Path(manifest).parts
        and manifest.startswith('config/host/')))
    storage = cfg.get('storage') or {}
    release_mount = storage.get('release_mount')
    release_root, operations_root = (storage_path(host_id, storage, key, home)
                                     for key in ('release_root', 'operations_root'))
    return HostLayout(host_id, manifest, release_root, Path(release_mount) if release_mount else None,
                      operations_root)


def storage_path(host_id, storage, key, home):
    value = storage.get(key)
    if value is None:
        return None
    path = home / value[2:] if value.startswith('~/') else Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError(f'fleet host {host_id!r} {key} must be absolute or ~/')
    return path


def physical_releases(root, family, home):
    """Physical tree for a live home only; fixture homes keep stamps under their own ~/.local/lib."""
    if Path(home) != Path.home():
        return None
    layout = resolve(root, home=home)
    return layout.release_root / family if layout.release_root else None


def require_release_mount(root, home, fresh=True):
    layout = resolve(root, home=home)
    mount = (Mount.NOT_DECLARED if not layout.release_mount else
             Mount.MOUNTED if os.path.ismount(layout.release_mount) else Mount.UNMOUNTED)
    admit(layout.release_mount or layout.host_id, mount=mount, fresh=fresh)


def admit_live(live, kind):
    """Per-entry gate: a checkout directory link or an operator edit refuses."""
    through = checkout_ancestor(live)
    admit(f'{through} -> {live}' if through else live,
          parent=Parent.THROUGH_CHECKOUT if through else Parent.REAL, live=kind)


def checkout_ancestor(path):
    """Return the first symlinked ancestor that resolves into a git checkout, if any.

    Writing a live link beneath such an ancestor edits the checkout itself, so the
    host would follow whatever branch is checked out (2026-10-25 mbp: whole
    ~/.config/systemd/user was a directory link into ~/workspace/.files).
    """
    path = Path(os.path.abspath(path))
    for ancestor in (path.parent, *path.parent.parents):
        if ancestor.is_symlink():
            resolved = ancestor.resolve()
            for parent in (resolved, *resolved.parents):
                if (parent / '.git').exists():
                    return ancestor
    return None
