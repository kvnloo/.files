#!/usr/bin/env python3
"""Lease-only artifact reclamation. Unknown liveness is a keep, never permission."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
import uuid

SCHEMA = 'z0.artifact-lease.v1'
TTL = 7 * 86400
SIDECAR = '.artifact-lease.json'
# Roots are policy, not caller-controlled command-line arguments.
ROOTS = {
    'groot': ['/mnt/zer0models/z0-wt', '/mnt/zer0models/worktrees', '/home/kvn/.local/state/fleet/jobs', '/home/kvn/.local/state/fleet/runs', '/home/kvn/.omp/wt'],
    'mbp': ['/home/kvn/.local/state/fleet/kueue', '/home/agentjob/jobs', '/home/kvn/jobs', '/home/kvn/.omp/wt'],
    's22': ['/root/fleet-jobs', '/root/edge-probe-s22', '/root/slm-opt', '/root/.cache/pip', '/root/.omp/wt'],
    's25': ['/root/fleet-jobs', '/root/edge-probe-s25', '/root/slm-opt', '/root/.cache/pip', '/root/.omp/wt'],
}

def atomic_json(path, value, *, replace=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex)
    try:
        with temp.open('x') as f:
            json.dump(value, f, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        if replace:
            os.replace(temp, path)
        else:
            try:
                os.link(temp, path)
            except FileExistsError:
                return False
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    finally:
        temp.unlink(missing_ok=True)


def within(path, root):
    return path != root and path.is_relative_to(root)


def allowed(path, roots):
    """Reject symlink components and root itself, not merely textual prefixes."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        return False
    if any(p.is_symlink() for p in [path, *path.parents]):
        return False
    return any(within(path, Path(root)) for root in roots)


def validate(lease, path, node, now):
    if lease.get('schema') != SCHEMA or lease.get('path') != str(path) or lease.get('node') != node:
        return 'lease identity mismatch'
    if not isinstance(lease.get('owner'), str) or not lease['owner']:
        return 'missing owner'
    if lease.get('kind') not in {'worktree', 'spool', 'model', 'cache', 'tmp'}:
        return 'unknown kind'
    for field in ('created_at', 'ttl'):
        value = lease.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return 'invalid ' + field
    receipts = lease.get('keep_receipts')
    if not isinstance(receipts, list) or any(not isinstance(p, str) or not p or Path(p).is_absolute() or '..' in Path(p).parts for p in receipts):
        return 'invalid receipt paths'
    if lease['created_at'] > now or lease['created_at'] + lease['ttl'] >= now:
        return 'unexpired'
    return None


def tree_identity(path):
    rows = []
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '.git')
        for name in sorted(files):
            if name == '.git':
                continue
            file = Path(base) / name
            st = file.lstat()
            rows.append((str(file.relative_to(path)), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
    return rows


def terminal_spool(path):
    # Existing native fleet workers publish numeric exit only after completion.
    # An absent/ambiguous terminal receipt keeps queued and disconnected jobs.
    marker = path / 'exit'
    try:
        return not marker.is_symlink() and marker.read_text().strip().lstrip('-').isdigit()
    except OSError:
        return False


def size_bytes(path):
    """Allocated bytes, no symlink traversal and no filesystem crossing."""
    device = path.stat().st_dev
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink() and (Path(base) / d).stat().st_dev == device]
        for name in files:
            st = (Path(base) / name).lstat()
            total += st.st_blocks * 512
    return total


def backend():
    spec = importlib.util.spec_from_file_location('worktree_reaper', Path(__file__).with_name('worktree-reaper.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_references(node, reaper):
    """Use #63 classifier, plus strict process visibility and serving registry."""
    refs, errors = reaper.references() if node == 'groot' else reaper.symlink_references(home=str(Path.home()))
    # #63's symlink collector returns refs/errors. On non-groot nodes collect
    # process and unit/config references here without assuming groot services.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for name in ('cwd', 'exe'):
                value = os.readlink(proc / name).removesuffix(' (deleted)')
                if value.startswith('/'):
                    refs.setdefault(os.path.realpath(value), set()).add('process:' + proc.name)
            for fd in (proc / 'fd').iterdir():
                try:
                    value = os.readlink(fd).removesuffix(' (deleted)')
                    if value.startswith('/'):
                        refs.setdefault(os.path.realpath(value), set()).add('open:' + proc.name)
                except FileNotFoundError:
                    pass
            for line in (proc / 'maps').read_text().splitlines():
                bits = line.split(None, 5)
                if len(bits) == 6 and bits[5].startswith('/'):
                    refs.setdefault(bits[5].removesuffix(' (deleted)'), set()).add('mapping:' + proc.name)
        except (FileNotFoundError, ProcessLookupError):
            pass
        except (PermissionError, OSError) as exc:
            errors.append('process visibility unknown:' + proc.name + ':' + type(exc).__name__)
    for root in [Path('/etc/systemd'), Path.home() / '.config/systemd', Path.home() / '.z0int/config', Path.home() / '.local/state/phone-native-inference']:
        if not root.exists():
            continue
        for base, dirs, files in os.walk(root, followlinks=False, onerror=lambda exc: errors.append(str(exc))):
            for name in files:
                file = Path(base) / name
                try:
                    if file.stat().st_size > 2_000_000:
                        errors.append('oversized serving/unit config:' + str(file))
                        continue
                    data = file.read_text(errors='replace')
                    # General absolute paths, including phone/MBP roots.
                    import re
                    for value in re.findall(r'/[^\s\x00\"\'`;<>|(){}\[\],:=]+', data):
                        refs.setdefault(os.path.realpath(value), set()).add('config:' + str(file))
                except OSError as exc:
                    errors.append('config visibility unknown:' + str(exc))
    return refs, errors


def reasons(path, refs):
    result = []
    for target, why in refs.items():
        other = Path(target)
        if path == other or path.is_relative_to(other) or other.is_relative_to(path):
            # A process cwd=/ or /root is not a claim on every descendant.
            if other == path or other.is_relative_to(path):
                result.extend(sorted(why))
    return sorted(set(result))


def candidates(node):
    for root_text in ROOTS[node]:
        root = Path(root_text)
        if not root.is_dir() or root.is_symlink():
            continue
        # Fixed experiment/cache directories are themselves payload containers.
        # Their children receive independent leases; never delete policy roots.
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.is_symlink() and not child.name.startswith('.'):
                yield child


def receipt_copy(path, lease, destination):
    destination.mkdir(parents=True, exist_ok=False)
    wanted = set(lease['keep_receipts']) | {SIDECAR}
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            source = Path(base) / name
            if source.is_symlink():
                continue
            rel = source.relative_to(path)
            if str(rel) in wanted or source.suffix in {'.log', '.json', '.jsonl', '.txt', '.csv'}:
                target = destination / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    hashes = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob('*') if p.is_file()}
    atomic_json(destination / 'receipt-hashes.json', hashes)
    return str(destination)


def isolation_owner_live(path):
    marker = path / '.omp-isolation-owner.json'
    if not marker.exists():
        return False
    try:
        owner = json.loads(marker.read_text())
        pid = owner['pid']
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return True
        os.kill(pid, 0)
        token = owner.get('startToken')
        if token:
            data = (Path('/proc') / str(pid) / 'stat').read_text()
            return data[data.rfind(')') + 2:].split()[19] == token
        return True
    except ProcessLookupError:
        return False
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return True


def git_payload(path):
    if (path / '.git').exists():
        return path
    if (path / '.omp-isolation-owner.json').exists() and (path / 'm/.git').exists():
        return path / 'm'
    return None


def inspect(path, node, refs, errors, now):
    row = {'path': str(path), 'bytes': 0, 'eligible': False, 'reasons': []}
    if not allowed(path, ROOTS[node]):
        row['reasons'] = ['outside allowlist or symlink']
        return row
    row['bytes'] = size_bytes(path)
    if (path / SIDECAR).is_symlink():
        row['reasons'] = ['symlink lease']
        return row
    try:
        lease = json.loads((path / SIDECAR).read_text())
        if not isinstance(lease, dict):
            raise ValueError('not an object')
    except (OSError, ValueError) as exc:
        row['reasons'] = ['lease unknown:' + type(exc).__name__]
        return row
    row['lease'] = lease
    invalid = validate(lease, path, node, now)
    row['reasons'] = ([invalid] if invalid else []) + reasons(path, refs)
    if errors:
        row['reasons'].append('LIVE unknown: incomplete reference inventory')
    if lease.get('kind') == 'spool' and not terminal_spool(path):
        row['reasons'].append('terminal spool receipt unknown')
    if isolation_owner_live(path):
        row['reasons'].append('LIVE or unknown OMP isolation owner')
    if (path / '.omp-retained-backend.json').exists():
        row['reasons'].append('retained native backend requires owner teardown')
    if os.path.ismount(path) or any(os.path.ismount(Path(base) / name) for base, dirs, _ in os.walk(path) for name in dirs):
        row['reasons'].append('mounted payload requires owner teardown')
    if lease.get('kind') == 'worktree' and git_payload(path) is None:
        row['reasons'].append('worktree repository unknown')
    # A spool/cache containing Git data cannot bypass archive-first behavior.
    nested_git = any('.git' in dirs or '.git' in files for _, dirs, files in os.walk(path, followlinks=False))
    if nested_git and lease.get('kind') != 'worktree':
        row['reasons'].append('contains git data without worktree lease')
    row['eligible'] = not row['reasons']
    return row


def inventory_report(args, out):
    """Bounded metadata only: never collect HOME references or grant eligibility."""
    rows = []
    # Groot does no descendant traversal; remote size collection is separate.
    for index, path in enumerate(candidates(args.node)):
        try:
            metadata = path.lstat()
            row = {'path': str(path), 'bytes': None, 'metadata_bytes': metadata.st_blocks * 512,
                   'size_status': 'UNKNOWN', 'live': 'UNKNOWN', 'eligible': False,
                   'reasons': ['report-only: recursive size and liveness not evaluated']}
        except OSError as exc:
            row = {'path': str(path), 'bytes': None, 'size_status': 'UNKNOWN',
                   'live': 'UNKNOWN', 'eligible': False, 'reasons': [str(exc)]}
        atomic_json(out / 'items' / (str(index) + '.json'), row)
        rows.append(row)
    report = {'schema': 'z0.artifact-reap.v1', 'node': args.node,
              'timestamp': time.time(), 'apply': False, 'mode': 'bounded-report',
              'would_reap_bytes': 0, 'removed_bytes': 0, 'known_bytes': 0,
              'unknown_size_count': len(rows), 'reference_errors': ['liveness not evaluated'],
              'items': rows, 'actions': []}
    atomic_json(out / 'report.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0


def run(args):
    reaper = backend()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    lock = (out / 'LOCK').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not args.apply and not args.enroll:
        return inventory_report(args, out)
    lifecycle_lock = None
    if args.apply and args.node == 'groot':
        # Serialize with #63's still-active archive-first incident actor.
        reaper.ARCHIVE.mkdir(parents=True, exist_ok=True)
        lifecycle_lock = (reaper.ARCHIVE / '.reaper.lock').open('a')
        fcntl.flock(lifecycle_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    now = time.time()
    refs, errors = local_references(args.node, reaper)
    rows = []
    actions = []
    for path in candidates(args.node):
        if args.enroll and not (path / SIDECAR).exists() and not (path / SIDECAR).is_symlink():
            kind = 'worktree' if git_payload(path) is not None else 'spool' if path.parent.name in {'jobs', 'fleet-jobs'} else 'cache'
            created = atomic_json(path / SIDECAR, {'schema': SCHEMA, 'owner': 'unknown', 'path': str(path), 'node': args.node, 'kind': kind, 'created_at': now, 'ttl': TTL, 'keep_receipts': []}, replace=False)
            if created:
                actions.append({'event': 'retroleased', 'path': str(path), 'expires_at': now + TTL})
        rows.append(inspect(path, args.node, refs, errors, now))
    for row in sorted((row for row in rows if row['eligible']), key=lambda row: row['lease']['created_at'] + row['lease']['ttl']):
        if not args.apply or not row['eligible'] or (out / 'PAUSED').exists():
            continue
        path = Path(row['path'])
        # Refresh every predicate at the point of risk, including lease identity.
        refs, fresh_errors = local_references(args.node, reaper)
        fresh = inspect(path, args.node, refs, fresh_errors, time.time())
        if not fresh['eligible'] or fresh.get('lease') != row['lease']:
            actions.append({'event': 'kept_on_refresh', 'path': str(path), 'reasons': fresh['reasons']})
            continue
        identity = path.stat()
        content_before = tree_identity(path)
        archive = out / 'receipts' / (hashlib.sha256(str(path).encode()).hexdigest()[:16] + '-' + uuid.uuid4().hex)
        receipt = receipt_copy(path, row['lease'], archive)
        if row['lease']['kind'] == 'worktree':
            gitpath = git_payload(path)
            gitrow = reaper.inspect(str(gitpath), ROOTS[args.node], refs, time.time())
            if gitrow['class'] == 'LIVE':
                actions.append({'event': 'kept_live_git', 'path': str(path)})
                continue
            gitarchive = out / 'git-archives'
            gitarchive.mkdir(exist_ok=True)
            reaper.preserve(gitrow, out, gitarchive)
        refs, fresh_errors = local_references(args.node, reaper)
        fresh = inspect(path, args.node, refs, fresh_errors, time.time())
        current = path.stat()
        if (out / 'PAUSED').exists() or not fresh['eligible'] or fresh['lease'] != row['lease'] or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino) or tree_identity(path) != content_before:
            actions.append({'event': 'kept_before_remove', 'path': str(path)})
            continue
        if row['lease']['kind'] == 'worktree':
            if reaper.text(str(gitpath), 'rev-parse', '--verify', 'HEAD^{commit}', check=False) != gitrow['head']:
                raise RuntimeError('HEAD changed during archival')
            if not gitrow['plain_clone']:
                reaper.git(str(gitpath), 'worktree', 'remove', '--force', str(gitpath), timeout=300)
            else:
                linked = reaper.text(str(gitpath), 'worktree', 'list', '--porcelain').splitlines()
                if any(line.startswith('worktree ') and Path(line[9:]) != gitpath and Path(line[9:]).exists() for line in linked):
                    actions.append({'event': 'kept_primary_with_dependents', 'path': str(path)})
                    continue
                if not shutil.rmtree.avoids_symlink_attacks:
                    raise RuntimeError('fd-safe recursive removal unavailable')
                shutil.rmtree(path)
            if gitpath != path and path.exists():
                shutil.rmtree(path)
        else:
            if not shutil.rmtree.avoids_symlink_attacks:
                raise RuntimeError('fd-safe recursive removal unavailable')
            shutil.rmtree(path)
        actions.append({'event': 'removed', 'path': str(path), 'bytes': row['bytes'], 'receipts': receipt})
        atomic_json(out / 'actions.json', actions)
    filesystems = {}
    for root in ROOTS[args.node]:
        if Path(root).exists():
            disk = shutil.disk_usage(root)
            filesystems[root] = {'total': disk.total, 'free': disk.free, 'free_percent': 100 * disk.free / disk.total}
    report = {'schema': 'z0.artifact-reap.v1', 'node': args.node, 'timestamp': now, 'apply': args.apply,
              'pressure_free_percent': min((row['free_percent'] for row in filesystems.values()), default=None),
              'filesystems': filesystems,
              'would_reap_bytes': sum(row['bytes'] for row in rows if row['eligible']),
              'removed_bytes': sum(a.get('bytes', 0) for a in actions if a['event'] == 'removed'),
              'reference_errors': errors, 'items': rows, 'actions': actions}
    atomic_json(out / 'report.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', choices=sorted(ROOTS), required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--enroll', action='store_true', help='retrolease unknown artifacts for seven days from now')
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
