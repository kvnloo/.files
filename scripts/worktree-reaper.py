#!/usr/bin/env python3
"""Inventory, preserve and reap inactive Git checkouts without touching live users.

The same classifier serves the operator run and daily maintenance. Every removal
has a durable receipt; preservation is completed before any destructive command.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOTS = ['/mnt/zer0models/z0-wt', '/mnt/zer0models/worktrees', '/mnt/zer0models/hermes-wt', '/home/kvn/tmp', '/home/kvn/workspace', '/mnt/zer0models/github']
DEFAULT_ROOTS = ROOTS
OUTPUT = Path('/mnt/zer0models/workspace/zer0/data/operations/worktree-reaper')
ARCHIVE = Path('/mnt/zer0models/wt-archive')
DAY = 86400
SKIP_DISCOVERY = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.cache', '.gradle', '.build', 'target', '.next', '.pnpm-store'}
OUTPUT_CONTAINERS = {'runs', 'artifacts', 'cache', 'test-output', 'test-outputs', 'test-results'}
PATH_PATTERN = re.compile(r'(?:/mnt/zer0models|/home/kvn|/workspace)(?:/[^\s\x00\"\'`;<>|(){}\[\],:=]*)?')
HOOK_REFERENCES = {}
# The deployment owner keeps both sides of the active backend stack until its
# normal PR merge/cutover; transient process activity is not ownership evidence.
ACTIVE_GUARD_SOURCES = {
    '/mnt/zer0models/z0-wt/bend-ops-laws': 'active-guard-stack:PR192-stack-ancestor',
    '/mnt/zer0models/z0-wt/bend-policy-laws': 'active-guard-stack:PR212-deployed-backend',
}


def command(args, cwd=None, timeout=60, env=None, check=True):
    p = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args[0:3]} exited {p.returncode}: {p.stderr.decode(errors="replace")[-1500:]}')
    return p


def git(path, *args, check=True, timeout=60, env=None):
    e = os.environ.copy()
    for key in ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        e.pop(key, None)
    e.update({'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'})
    if env:
        e.update(env)
    return command(['git', '-C', path, *args], timeout=timeout, env=e, check=check)


def text(path, *args, **kwargs):
    return git(path, *args, **kwargs).stdout.decode(errors='surrogateescape').strip()


def emit(out, event, **fields):
    row = {'timestamp': dt.datetime.now(dt.timezone.utc).isoformat(), 'event': event, **fields}
    with (out / 'manifest.jsonl').open('a') as f:
        f.write(json.dumps(row, ensure_ascii=True) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return row


def discover(roots):
    found = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for base, dirs, files in os.walk(root, followlinks=False):
            if '.git' in dirs or '.git' in files:
                if text(base, 'rev-parse', '--is-inside-work-tree', check=False) == 'true':
                    found.add(os.path.realpath(base))
                # Do not crawl dependency/build trees inside each checkout.
                # Git's own registrations below enumerate linked worktrees.
                dirs[:] = []
                continue
            if 'pyvenv.cfg' in files:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in SKIP_DISCOVERY | OUTPUT_CONTAINERS and not os.path.islink(os.path.join(base, d))]
    # Registration and submodule metadata enumerate nested Git checkouts without
    # recursively stat'ing every dependency/build artifact in each repository.
    pending = list(found)
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        targets = []
        p = git(path, 'worktree', 'list', '--porcelain', check=False)
        targets.extend(line[9:] for line in p.stdout.decode(errors='replace').splitlines() if line.startswith('worktree '))
        if os.path.isfile(os.path.join(path, '.gitmodules')):
            p = git(path, 'config', '--file', '.gitmodules', '--get-regexp', r'^submodule\..*\.path$', check=False)
            targets.extend(os.path.join(path, line.split(None, 1)[1]) for line in p.stdout.decode(errors='replace').splitlines() if len(line.split(None, 1)) == 2)
        for target in targets:
            target = os.path.realpath(target)
            in_scope = any(target == os.path.realpath(r) or target.startswith(os.path.realpath(r) + '/') for r in roots)
            generated = any(target.startswith(os.path.realpath(r) + '/') and set(Path(os.path.relpath(target, os.path.realpath(r))).parts) & OUTPUT_CONTAINERS for r in roots)
            if in_scope and not generated and os.path.exists(os.path.join(target, '.git')) and target not in found:
                if text(target, 'rev-parse', '--is-inside-work-tree', check=False) == 'true':
                    found.add(target)
                    pending.append(target)
    return sorted(found)


def active_guard_references():
    return {os.path.realpath(path): {reason} for path, reason in ACTIVE_GUARD_SOURCES.items()}


def references():
    refs = collections.defaultdict(set)
    errors = []
    def add(path, reason):
        if path and path.startswith('/'):
            refs[os.path.realpath(path.removesuffix(' (deleted)'))].add(reason)
    def paths(data, reason):
        for token in ('${HOME}', '$HOME', '%h', '~'):
            data = data.replace(token, '/home/kvn')
        for m in PATH_PATTERN.finditer(data):
            add(m.group(0).rstrip('\\'), reason)
    for target, reasons in HOOK_REFERENCES.items():
        refs[target].update(reasons)
    for target, reasons in active_guard_references().items():
        refs[target].update(reasons)
    for root in ['/home/kvn/.local/bin', '/home/kvn/.config/systemd/user']:
        for base, dirs, files in os.walk(root, followlinks=False):
            for name in [*dirs, *files]:
                link = Path(base) / name
                if link.is_symlink():
                    add(str(link.resolve()), f'deployment-symlink:{link}')
    # Read every process link we are allowed to inspect, never process contents.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        for name in ('cwd', 'exe'):
            try:
                add(os.readlink(proc / name), f'process:{proc.name}:{name}')
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    add(os.readlink(fd), f'process:{proc.name}:fd:{fd.name}')
                except (OSError, ProcessLookupError):
                    pass
            maps = (proc / 'maps').read_text(errors='replace')
            for line in maps.splitlines():
                parts = line.split(None, 5)
                if len(parts) == 6:
                    add(parts[5], f'process:{proc.name}:mapping')
        except (OSError, ProcessLookupError):
            pass
    # Unit files include inactive units and drop-ins, not merely running services.
    for root in ['/etc/systemd/system', '/etc/systemd/user', '/usr/lib/systemd/system', '/usr/lib/systemd/user', '/run/systemd/system', '/run/systemd/user', '/home/kvn/.config/systemd/user']:
        for base, dirs, files in os.walk(root, followlinks=False):
            for filename in files:
                p = Path(base) / filename
                try:
                    if p.stat().st_size < 2_000_000:
                        paths(p.read_text(errors='replace'), f'systemd:{p}')
                except OSError:
                    pass
    # Only config files and symlinks: do not scrape private chat histories.
    for root in ['/home/kvn/.omp', '/home/kvn/.claude', '/home/kvn/.codex', '/home/kvn/.hermes']:
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d not in SKIP_DISCOVERY | {'sessions', 'logs', 'history', 'cache', 'backups', 'projects', 'skills', 'conversations', 'plugins', 'plugin-data', 'archives', 'archive', 'artifacts', 'datasets', 'outputs', 'browser-profiles'}]
            for filename in [*dirs, *files]:
                p = Path(base) / filename
                try:
                    if p.is_symlink():
                        add(str(p.resolve()), f'config-symlink:{p}')
                    elif p.is_file() and p.suffix in {'.json', '.toml', '.yaml', '.yml', '.ini', '.conf'} and p.stat().st_size < 2_000_000:
                        paths(p.read_text(errors='replace'), f'config:{p}')
                except OSError:
                    pass
    for args, reason in [(['crontab', '-l'], 'crontab:user'), (['sudo', '-n', 'crontab', '-l'], 'crontab:root')]:
        try:
            p = command(args, timeout=10, check=False)
            if p.returncode == 0:
                paths(p.stdout.decode(errors='replace'), reason)
        except (OSError, subprocess.TimeoutExpired):
            pass
    for root in ['/etc/cron.d', '/etc/cron.daily', '/etc/cron.hourly', '/etc/cron.weekly']:
        for base, _, files in os.walk(root):
            for name in files:
                p = Path(base) / name
                try:
                    paths(p.read_text(errors='replace'), f'crontab:{p}')
                except OSError:
                    pass
    try:
        p = command(['tern', 'ls', '--json'], timeout=20, check=False)
        if p.returncode == 0:
            def walk(v):
                if isinstance(v, dict):
                    for k, x in v.items():
                        if k.lower() in {'cwd', 'workingdirectory', 'working_directory'} and isinstance(x, str):
                            add(x, 'tern:pane-cwd')
                        else:
                            walk(x)
                elif isinstance(v, list):
                    for x in v:
                        walk(x)
            walk(json.loads(p.stdout))
        else:
            errors.append('tern pane inventory unavailable: ' + p.stderr.decode(errors='replace')[-200:])
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        errors.append('tern pane inventory: ' + str(e))
    try:
        kubeconfig = Path('/home/kvn/.kube/k3s.yaml')
        kube_args = ['--kubeconfig', str(kubeconfig)] if kubeconfig.is_file() else []
        p = command(['kubectl', *kube_args, 'get', 'pods,pv', '-A', '-o', 'json', '--request-timeout=10s'], timeout=20, check=False)
        if p.returncode == 0:
            def hosts(v):
                if isinstance(v, dict):
                    if isinstance(v.get('hostPath'), dict):
                        add(v['hostPath'].get('path', ''), 'k3s:hostPath')
                    for x in v.values():
                        hosts(x)
                elif isinstance(v, list):
                    for x in v:
                        hosts(x)
            hosts(json.loads(p.stdout))
        else:
            errors.append('k3s hostPath inventory unavailable: ' + p.stderr.decode(errors='replace')[-200:])
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        errors.append('k3s hostPath inventory: ' + str(e))
    return refs, errors


def live_reasons(path, refs):
    return sorted({reason + ':' + target for target, reasons in refs.items() if target == path or target.startswith(path + '/') for reason in reasons})


def newest_mtime(path, cutoff=None):
    latest = os.lstat(path).st_mtime
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in [*dirs, *files]:
            if name == '.git':
                continue
            try:
                latest = max(latest, os.lstat(os.path.join(base, name)).st_mtime)
                if cutoff and latest > cutoff:
                    return latest
            except FileNotFoundError:
                pass
    return latest


def inspect(path, roots, refs, now):
    # Relative git-dir output is relative to the checkout, not the controller cwd.
    rawcommon = text(path, 'rev-parse', '--git-common-dir')
    common = os.path.realpath(os.path.join(path, rawcommon))
    head = text(path, 'rev-parse', '--verify', 'HEAD^{commit}', check=False)
    branch = text(path, 'symbolic-ref', '--short', '-q', 'HEAD', check=False)
    upstream = text(path, 'rev-parse', '--abbrev-ref', '@{upstream}', check=False)
    ahead = behind = None
    if upstream:
        counts = text(path, 'rev-list', '--left-right', '--count', f'HEAD...{upstream}', check=False).split()
        if len(counts) == 2:
            ahead, behind = map(int, counts)
    remote = text(path, 'remote', 'get-url', 'origin', check=False)
    default = text(path, 'symbolic-ref', '-q', 'refs/remotes/origin/HEAD', check=False)
    if not default:
        for ref in ('refs/remotes/origin/main', 'refs/remotes/origin/master', 'refs/heads/main', 'refs/heads/master'):
            if git(path, 'show-ref', '--verify', '--quiet', ref, check=False).returncode == 0:
                default = ref
                break
    merged = bool(head and default and git(path, 'merge-base', '--is-ancestor', 'HEAD', default, check=False).returncode == 0)
    pushed = bool(head and text(path, 'for-each-ref', '--contains', 'HEAD', '--format=%(refname)', 'refs/remotes/'))
    plain_clone = os.path.isdir(os.path.join(path, '.git'))
    unpublished = int(text(path, 'rev-list', '--count', '--branches', '--not', '--remotes') or '0') if plain_clone else None
    status = git(path, 'status', '--porcelain=v1', '-z', '--untracked-files=all').stdout.split(b'\0')
    dirty = untracked = 0
    i = 0
    while i < len(status):
        item = status[i]
        if item:
            if item.startswith(b'??'):
                untracked += 1
            else:
                dirty += 1
                if item[:1] in {b'R', b'C'} or item[1:2] in {b'R', b'C'}:
                    i += 1
        i += 1
    last = text(path, 'log', '-1', '--format=%ct', check=False)
    last_time = int(last) if last.isdigit() else None
    mtime = newest_mtime(path, now - DAY)
    reasons = live_reasons(path, refs)
    if mtime > now - DAY:
        reasons.append('modified-within-24h:' + dt.datetime.fromtimestamp(mtime, dt.timezone.utc).isoformat())
    root = next((r for r in roots if path == os.path.realpath(r) or path.startswith(os.path.realpath(r) + '/')), '')
    safe = not dirty and not untracked and (pushed or merged) and (not plain_clone or (bool(remote) and unpublished == 0))
    return {'path': path, 'root': root, 'parent_repo': common, 'branch': branch or '(detached)', 'head': head, 'upstream': upstream or None, 'ahead': ahead, 'behind': behind, 'default_ref': default or None, 'merged_into_default': merged, 'head_in_remote_tracking': pushed, 'unpublished_commit_count': unpublished, 'dirty_count': dirty, 'untracked_count': untracked, 'last_commit_timestamp': last_time, 'last_commit_age_days': (now-last_time)/DAY if last_time else None, 'mtime_timestamp': mtime, 'mtime_age_days': (now-mtime)/DAY, 'remote': remote, 'plain_clone': plain_clone, 'live_reasons': reasons, 'class': 'LIVE' if reasons else ('SAFE' if safe else 'WIP')}


def archive_name(row):
    name = re.sub('[^A-Za-z0-9._-]', '-', Path(row['path']).name).strip('.') or 'checkout'
    suffix = hashlib.sha256(row['path'].encode()).hexdigest()[:8]
    return f'archive/wt-{name}-{dt.datetime.now(dt.timezone.utc):%Y%m%d}-{suffix}'


def preserve(row, out, archive):
    path = row['path']
    branch = archive_name(row)
    ref = 'refs/heads/' + branch
    commit = row['head']
    staged_commit = None
    identity = {'GIT_AUTHOR_NAME': 'Worktree archive', 'GIT_AUTHOR_EMAIL': 'worktree-archive@localhost', 'GIT_COMMITTER_NAME': 'Worktree archive', 'GIT_COMMITTER_EMAIL': 'worktree-archive@localhost'}
    if row['dirty_count']:
        # Preserve the original staged tree independently of the working tree:
        # a file can contain different, valuable staged and unstaged edits.
        staged_tree = text(path, 'write-tree')
        staged_args = ['commit-tree', staged_tree]
        if row['head']:
            staged_args.extend(['-p', row['head']])
        staged_args.extend(['-m', f'Archive original index from {path}'])
        staged_commit = text(path, *staged_args, env=identity)
    # A private index records tracked changes, deletions and nonignored untracked
    # files without changing the user's original branch, index or working files.
    if row['dirty_count'] or row['untracked_count'] or not row['head']:
        idx = archive / (hashlib.sha256(path.encode()).hexdigest()[:16] + '.index')
        try:
            idx.unlink(missing_ok=True)
            env = {'GIT_INDEX_FILE': str(idx), 'GIT_AUTHOR_NAME': 'Worktree archive', 'GIT_AUTHOR_EMAIL': 'worktree-archive@localhost', 'GIT_COMMITTER_NAME': 'Worktree archive', 'GIT_COMMITTER_EMAIL': 'worktree-archive@localhost'}
            git(path, 'read-tree', row['head'] or '--empty', env=env)
            git(path, 'add', '-A', '--', '.', env=env, timeout=180)
            tree = text(path, 'write-tree', env=env)
            args = ['commit-tree', tree]
            if staged_commit or row['head']:
                args.extend(['-p', staged_commit or row['head']])
            args.extend(['-m', f'Archive WIP from {path} before worktree cleanup'])
            commit = text(path, *args, env=env)
        finally:
            idx.unlink(missing_ok=True)
    if not commit:
        raise RuntimeError('Cannot preserve a checkout without HEAD or a snapshot commit')
    git(path, 'update-ref', ref, commit)
    record = {'path': path, 'archive_branch': branch, 'archive_commit': commit, 'staged_commit': staged_commit, 'remote': row['remote'], 'bundle': None, 'push_ok': False}
    emit(out, 'archive_ref_created', **record)
    if row['remote']:
        p = git(path, 'push', '--no-follow-tags', 'origin', f'{ref}:{ref}', timeout=120, check=False)
        record['push_ok'] = p.returncode == 0
        if record['push_ok']:
            remote_head = text(path, 'ls-remote', '--heads', 'origin', ref, timeout=60).split()
            record['push_ok'] = bool(remote_head and remote_head[0] == commit)
        if p.returncode:
            record['push_error'] = p.stderr.decode(errors='replace')[-1500:]
    # All plain clones receive a full bundle, including other local branches and
    # stashes. Worktree bundles are incremental to remote refs where possible.
    if row['plain_clone'] or not record['push_ok']:
        bundle = archive / (branch.replace('/', '--') + '.bundle')
        if row['plain_clone']:
            args = ['bundle', 'create', str(bundle), '--all']
        else:
            args = ['bundle', 'create', str(bundle), ref]
        git(path, *args, timeout=600)
        git(path, 'bundle', 'verify', str(bundle), timeout=120)
        record['bundle'] = str(bundle)
        record['bundle_bytes'] = bundle.stat().st_size
        record['bundle_sha256'] = hashlib.file_digest(bundle.open('rb'), 'sha256').hexdigest()
    if not record['push_ok'] and not record['bundle']:
        raise RuntimeError('Preservation did not reach durable remote or bundle storage')
    if record['bundle']:
        record['restore_command'] = f"git clone {__import__('shlex').quote(record['bundle'])} {__import__('shlex').quote(path)} && git -C {__import__('shlex').quote(path)} checkout {__import__('shlex').quote(branch)}"
    else:
        record['restore_command'] = f"git clone {__import__('shlex').quote(row['remote'])} {__import__('shlex').quote(path)} && git -C {__import__('shlex').quote(path)} checkout {__import__('shlex').quote(branch)}"
    emit(out, 'archived', **record)
    return record


def report(out, rows, actions, before, after, errors, mode):
    freed = sum(a.get('size_bytes', 0) for a in actions if a['event'] == 'removed')
    archives = [a for a in actions if a['event'] == 'archived']
    archive_bytes = sum(a.get('bundle_bytes', 0) for a in archives)
    summary = {'timestamp': dt.datetime.now(dt.timezone.utc).isoformat(), 'mode': mode, 'checkout_count': sum(after.values()), 'before_counts': before, 'after_counts': after, 'live_count': sum(r['class']=='LIVE' for r in rows), 'safe_count': sum(r['class']=='SAFE' for r in rows), 'wip_count': sum(r['class']=='WIP' for r in rows), 'removed_count': sum(a['event']=='removed' for a in actions), 'bytes_freed': freed, 'archive_bytes': archive_bytes, 'net_estimated_bytes_freed': freed-archive_bytes, 'errors': errors}
    summary['bytes_freed_by_root'] = {root: sum(a.get('size_bytes', 0) for a in actions if a['event'] == 'removed' and (a['path'] == os.path.realpath(root) or a['path'].startswith(os.path.realpath(root) + '/'))) for root in before}
    tmp = out / 'latest.json.tmp'
    tmp.write_text(json.dumps(summary, indent=2) + '\n')
    tmp.replace(out / 'latest.json')
    lines = ['# Worktree reaper', '', f"Run: {summary['timestamp']} ({mode})", '', '| Root | Before | After | Allocated bytes removed |', '|---|---:|---:|---:|']
    for root, count in before.items():
        removed_bytes = summary['bytes_freed_by_root'][root]
        lines.append(f'| `{root}` | {count} | {after.get(root, 0)} | {removed_bytes:,} |')
    lines += ['', f"Removed: {summary['removed_count']}. Allocated checkout bytes removed: {freed:,}. Bundle bytes: {archive_bytes:,}. Estimated net freed: {freed-archive_bytes:,} bytes.", '', 'Allocated bytes use sequential niced/ioniced `du -s -B1` on removal candidates only. Shared Git objects and filesystem compression can make physical free-space change differ. All original inventory and every action are in `manifest.jsonl`.', '', '## Kept LIVE checkouts', '']
    for row in rows:
        if os.path.exists(row['path']) and row['class'] == 'LIVE':
            lines.append(f"- `{row['path']}`")
            lines.extend('  - ' + reason for reason in row['live_reasons'])
    lines += ['', '## Archives and restore commands', '']
    for a in archives:
        lines += [f"- `{a['path']}` → `{a['archive_branch']}` ({'pushed' if a['push_ok'] else 'bundle fallback'})", f"  - Bundle: `{a['bundle']}`" if a['bundle'] else '  - Remote: `' + a['remote'] + '`', '  - Restore: `' + a['restore_command'] + '`']
    lines += ['', '## Errors / deferred actions', ''] + (['- ' + str(e) for e in errors] or ['None.'])
    (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    emit(out, 'summary', **summary)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Archive and remove every non-LIVE checkout now')
    mode.add_argument('--daily', action='store_true', help='Remove SAFE >=3d and archive WIP >=14d')
    mode.add_argument('--inventory', action='store_true', help='Read-only inventory (default)')
    parser.add_argument('--root', action='append', dest='roots')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    args = parser.parse_args()
    os.nice(15)
    args.output.mkdir(parents=True, exist_ok=True)
    args.archive.mkdir(parents=True, exist_ok=True)
    lock = (args.archive / '.reaper.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another reaper holds the lifecycle lock')
    roots = args.roots or ROOTS
    emit(args.output, 'discovery_started', roots=roots)
    paths = discover(roots)
    # Hooks are executable infrastructure even when no process currently has
    # them open. Resolve effective config (including includeIf/global settings).
    for path in paths:
        hooks = text(path, 'config', '--path', '--get', 'core.hooksPath', check=False)
        if hooks:
            target = os.path.realpath(os.path.join(path, os.path.expanduser(hooks)))
            HOOK_REFERENCES.setdefault(target, set()).add('git-core.hooksPath:' + path)
    refs, errors = references()
    reference_errors = list(errors)
    now = time.time()
    rows = []
    emit(args.output, 'run_started', mode='apply' if args.apply else 'daily' if args.daily else 'inventory', roots=roots, checkout_count=len(paths), reference_errors=errors)
    for path in paths:
        try:
            row = inspect(path, roots, refs, now)
            rows.append(row)
            emit(args.output, 'inventory_checkpoint', **row)
            print(json.dumps({'inventory': path, 'class': row['class'], 'dirty': row['dirty_count'], 'untracked': row['untracked_count']}), flush=True)
        except Exception as e:
            errors.append({'path': path, 'inventory_error': str(e)})
            emit(args.output, 'inventory_error', path=path, error=str(e))
    # A parent directory cannot be removed while a live nested checkout remains.
    for row in sorted(rows, key=lambda r: -len(r['path'])):
        if row['class'] == 'LIVE':
            for parent in rows:
                if row['path'].startswith(parent['path'] + '/'):
                    parent['class'] = 'LIVE'
                    parent['live_reasons'].append('contains-live-checkout:' + row['path'])
            for owner in rows:
                if row['parent_repo'].startswith(owner['path'] + '/') and owner['plain_clone']:
                    owner['class'] = 'LIVE'
                    owner['live_reasons'].append('git-object-store-for-live-checkout:' + row['path'])
    for row in rows:
        emit(args.output, 'inventory', **row)
    before = {r: sum(p == os.path.realpath(r) or p.startswith(os.path.realpath(r)+'/') for p in paths) for r in roots}
    actions = []
    mutating = args.apply or args.daily
    # Missing Tern/k3s visibility is never interpreted as proof of inactivity.
    # Retry the collector/operator environment before applying a destructive run.
    if mutating and reference_errors:
        emit(args.output, 'preflight_failed', errors=errors)
        report(args.output, rows, actions, before, before, errors, 'preflight-blocked')
        return 1
    for row in sorted(rows, key=lambda r: (r['plain_clone'], -len(r['path']))):
        if not mutating or row['class'] == 'LIVE':
            continue
        if args.daily and row['mtime_age_days'] < (3 if row['class']=='SAFE' else 14):
            continue
        try:
            # Recollect links immediately before preservation, then once more
            # immediately before removal to close the inventory/activity race.
            fresh, issues = references()
            if issues:
                raise RuntimeError('Live reference refresh failed: ' + str(issues))
            reasons = live_reasons(row['path'], fresh)
            if newest_mtime(row['path'], time.time()-DAY) > time.time()-DAY:
                reasons.append('modified-within-24h:recheck')
            if reasons:
                row['class'] = 'LIVE'
                row['live_reasons'].extend(reasons)
                actions.append(emit(args.output, 'kept_newly_live', path=row['path'], reasons=reasons))
                continue
            size = int(command(['nice', '-n', '19', 'ionice', '-c', '3', 'du', '-s', '-B1', '--', row['path']], timeout=300).stdout.split()[0])
            # Even a clean plain clone can contain non-HEAD branches or stashes.
            # Bundling it is mandatory before deleting its private object store.
            if row['class'] == 'WIP' or row['plain_clone']:
                archive = preserve(row, args.output, args.archive)
                actions.append({'event': 'archived', **archive})
            fresh, issues = references()
            reasons = live_reasons(row['path'], fresh)
            if issues or reasons:
                raise RuntimeError('Checkout became live after archive: ' + str(reasons or issues))
            # Archive writes only .git metadata, which is deliberately excluded
            # from activity age. Any changed working content still blocks removal.
            if text(row['path'], 'rev-parse', '--verify', 'HEAD^{commit}', check=False) != row['head']:
                raise RuntimeError('HEAD changed during archival')
            if newest_mtime(row['path'], time.time()-DAY) > time.time()-DAY:
                raise RuntimeError('Working files changed during archival')
            emit(args.output, 'remove_intent', path=row['path'], size_bytes=size, parent_repo=row['parent_repo'], remote=row['remote'], branch=row['branch'])
            if row['plain_clone']:
                linked = text(row['path'], 'worktree', 'list', '--porcelain').splitlines()
                others = [l[9:] for l in linked if l.startswith('worktree ') and os.path.realpath(l[9:]) != row['path'] and os.path.exists(l[9:])]
                if others:
                    raise RuntimeError('Primary clone still owns linked worktrees: ' + str(others))
                shutil.rmtree(row['path'])
            else:
                git(row['path'], 'worktree', 'remove', '--force', row['path'], timeout=300)
            actions.append(emit(args.output, 'removed', path=row['path'], size_bytes=size, original_class=row['class'], remote=row['remote'], branch=row['branch']))
        except Exception as e:
            err = {'path': row['path'], 'error': str(e)}
            errors.append(err)
            actions.append(emit(args.output, 'action_error', **err))
    for common in sorted({r['parent_repo'] for r in rows if os.path.isdir(r['parent_repo'])}):
        if mutating:
            p = command(['git', '--git-dir', common, 'worktree', 'prune'], check=False)
            emit(args.output, 'pruned', parent_repo=common, returncode=p.returncode)
    after_paths = discover(roots) if mutating else paths
    after = {r: sum(p == os.path.realpath(r) or p.startswith(os.path.realpath(r)+'/') for p in after_paths) for r in roots}
    report(args.output, rows, actions, before, after, errors, 'apply' if args.apply else 'daily' if args.daily else 'inventory')
    return int(bool(errors))

if __name__ == '__main__':
    raise SystemExit(main())
