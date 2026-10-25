#!/usr/bin/env python3
"""Preserve referenced releases and rollback; offload other SHA trees, never delete."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

HOME = Path('/home/kvn')
BASE = HOME / '.local/lib'
DEST = Path('/mnt/zer0models/releases')
SHA = re.compile(r'^[0-9a-f]{40,64}$')


def references():
    refs, errors = set(), []
    process_receipts = []
    roots = [HOME / '.config/systemd', HOME / '.local/bin', HOME / '.omp/agent/extensions']
    for root in roots:
        for base, dirs, files in os.walk(root, followlinks=False):
            for name in dirs + files:
                path = Path(base) / name
                try:
                    if path.is_symlink():
                        refs.add(str(path.resolve()))
                    elif path.is_file() and root == roots[0]:
                        text = path.read_text().replace('%h', str(HOME))
                        refs.update(re.findall(re.escape(str(BASE)) + r'/[^\s\"\';:]+', text))
                except (OSError, UnicodeError) as exc:
                    errors.append(str(path) + ':' + type(exc).__name__)
    # Every release-family pointer, not merely the conventional current name.
    for family in BASE.iterdir():
        if family.is_symlink() or not family.is_dir():
            continue
        for path in family.iterdir():
            if path.is_symlink() and not SHA.fullmatch(path.name):
                refs.add(str(path.resolve()))
    # Authorized scope: readable system declarations plus every kvn process.
    # Unreadable non-kvn processes are assumed not to depend on undeclared
    # private home releases. This assumption is recorded in the evidence.
    system_roots = [Path('/etc/systemd/system'), Path('/usr/lib/systemd/system'), Path('/etc/rancher/k3s')]
    system_roots += list(Path('/etc').glob('cron*'))
    skipped_system = []
    for root in system_roots:
        paths = [root] if root.is_file() else (Path(base) / name for base, _, files in os.walk(root) for name in files)
        for path in paths:
            try:
                text = path.read_text()
                refs.update(re.findall(re.escape(str(BASE)) + r'/[^\s\"\';:]+', text))
            except (OSError, UnicodeError):
                skipped_system.append(str(path))
    try:
        pods = json.loads(subprocess.check_output(['kubectl', '--kubeconfig', str(HOME / '.kube/k3s.yaml'), 'get', 'pods', '-A', '-o', 'json'], text=True, stderr=subprocess.PIPE, timeout=30))
        for pod in pods['items']:
            for volume in pod.get('spec', {}).get('volumes', []):
                if 'hostPath' in volume:
                    refs.add('hostPath:' + volume['hostPath']['path'])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        errors.append('k3s hostPath visibility unknown:' + type(exc).__name__)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != HOME.stat().st_uid:
                continue
            for name in ('cwd', 'exe'):
                refs.add(os.readlink(proc / name).removesuffix(' (deleted)'))
            for line in (proc / 'maps').read_text().splitlines():
                parts = line.split(None, 5)
                if len(parts) == 6 and parts[5].startswith('/'):
                    refs.add(parts[5].removesuffix(' (deleted)'))
        except (FileNotFoundError, ProcessLookupError):
            pass
        except (OSError, PermissionError) as exc:
            try:
                command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
                comm = (proc / 'comm').read_text().strip()
                # Globally preserving every declared candidate is stricter
                # than only preserving declarations for this unit/container.
                home_command = any(value in command for value in (str(BASE), str(HOME / '.local/bin'), '~/.local/lib', '~/.local/bin'))
                process_receipts.append({'pid': int(proc.name), 'comm': comm, 'rule': 'keep-unknown' if home_command else 'no-home-command-path; globally preserve declared candidates'})
                if home_command:
                    errors.append(str(proc) + ':' + type(exc).__name__)
            except (FileNotFoundError, ProcessLookupError):
                pass
            except OSError as unknown:
                errors.append(str(proc) + ':cmdline unknown:' + type(unknown).__name__)
    return {'schema': 'z0.release-references.v1', 'timestamp': time.time(), 'collector_uid': os.getuid(), 'references': sorted(refs), 'errors': errors, 'process_receipts': process_receipts, 'skipped_system_configs': skipped_system, 'assumption': 'Unreadable infrastructure processes with no private-home command path cannot depend on an undeclared candidate; every system declaration and k3s hostPath reference is retained globally.'}


def referenced(path, refs):
    return any((str(path) == value[9:] or str(path).startswith(value[9:].rstrip('/') + '/')) if value.startswith('hostPath:') else (value == str(path) or value.startswith(str(path) + '/')) for value in refs)


def plan(evidence):
    rows = []
    for family in sorted(BASE.iterdir()):
        if family.is_symlink() or not family.is_dir():
            continue
        releases = sorted((p for p in family.iterdir() if SHA.fullmatch(p.name) and p.is_dir() and not p.is_symlink()), key=lambda p: p.stat().st_mtime, reverse=True)
        current = (family / 'current').resolve()
        previous = next((p for p in releases if p != current), None)
        for path in releases:
            reasons = []
            if evidence['errors']:
                reasons.append('reference visibility unknown')
            if path == current:
                reasons.append('current')
            if path == previous:
                reasons.append('previous rollback release')
            if referenced(path, evidence['references']):
                reasons.append('live reference')
            if (DEST / family.name / path.name).exists():
                reasons.append('destination already exists; preserve both')
            size = int(subprocess.check_output(['du', '-sx', '-B1', str(path)], text=True).split()[0])
            rows.append({'family': family.name, 'source': str(path), 'destination': str(DEST / family.name / path.name), 'bytes': size, 'keep': reasons})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--references', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.collect:
        print(json.dumps(references()))
        return 0
    evidence = json.loads(args.references.read_text()) if args.references else references()
    if evidence.get('schema') != 'z0.release-references.v1' or time.time() - evidence['timestamp'] > 300:
        raise RuntimeError('missing or stale reference evidence')
    rows = plan(evidence)
    print(json.dumps({'mode': 'apply' if args.apply else 'dry-run', 'rows': rows, 'errors': evidence['errors'], 'process_receipts': evidence.get('process_receipts', []), 'assumption': evidence.get('assumption')}), flush=True)
    if not args.apply:
        return 0
    if os.getuid() != 1000 or not os.path.ismount('/mnt/zer0models'):
        raise RuntimeError('apply requires owner and mounted bulk disk')
    lock = Path('/tmp/files-live-deploy.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    spec = importlib.util.spec_from_file_location('storage_mover', Path(__file__).with_name('zer0_storage_tier.py'))
    mover = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mover)
    for row in rows:
        if row['keep']:
            continue
        source = Path(row['source'])
        # Refresh the authorized user-process/system-declaration scope.
        fresh = references()
        if fresh['errors'] or referenced(source, fresh['references']):
            print(json.dumps({'event': 'kept-on-refresh', 'source': str(source), 'errors': fresh['errors']}), flush=True)
            continue
        mover.migrate(source, DEST / row['family'], dry_run=False, source_root=source.parent)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
