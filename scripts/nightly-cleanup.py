#!/usr/bin/env python3
"""Small, conservative nightly cache/worktree cleanup. No clone or product deletion."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

BASE = Path('/mnt/zer0models')
ARCHIVE = Path('/workspace/cache/nightly-cleanup')
ROOTS = ('z0-wt', 'hermes-wt', 'worktrees', 'workspaces', 'github', 'repos',
         'local-3d', 'world-generation-prototypes', 'workspace')
SAFE = {'node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
        '.next', '.turbo', '.gradle', '.cache'}
PROTECTED = {'products', 'data', 'sessions', 'memories', '.hermes', '.omp', '.git', '.venv', 'venv'}
MANIFESTS = ('package.json', 'pyproject.toml', 'Cargo.toml', 'CMakeLists.txt', 'Makefile', 'Package.swift')


def git(path, *args):
    return subprocess.run(['git', '--no-optional-locks', '-C', str(path), *args],
                          capture_output=True, text=True, timeout=90, check=True).stdout.strip()


def log(event, path, **fields):
    with (ARCHIVE / 'ledger.jsonl').open('a') as out:
        out.write(json.dumps(dict(time=time.time(), event=event, path=str(path), **fields), sort_keys=True) + '\n')
        out.flush()
        os.fsync(out.fileno())


def available():
    s = os.statvfs(BASE)
    return s.f_bavail * s.f_frsize


def live_paths():
    """Do not print process contents; retain only filesystem references for exclusion."""
    found = set()
    for proc in Path('/proc').glob('[0-9]*'):
        for item in [proc / 'cwd', proc / 'exe', *list((proc / 'fd').glob('*'))]:
            try:
                value = os.readlink(item).removesuffix(' (deleted)')
                if value.startswith('/'):
                    found.add(Path(value).resolve())
            except OSError:
                pass
        for name in ('maps', 'cmdline', 'environ'):
            try:
                text = (proc / name).read_bytes().decode(errors='replace')
                values = [line.split(None, 5)[-1] for line in text.splitlines() if len(line.split(None, 5)) == 6] if name == 'maps' else text.split('\0')
                for value in values:
                    for part in value.split('=', 1)[-1].split(os.pathsep):
                        if part.startswith(str(BASE) + '/'):
                            found.add(Path(part.removesuffix(' (deleted)')).resolve())
            except OSError:
                pass
    # Shared dependency symlinks can be in use even after their files are closed.
    for path in list(found):
        for parent in (path, *path.parents):
            if parent == BASE or BASE not in parent.parents:
                break
            for name in SAFE | {'.venv', 'venv'}:
                dep = parent / name
                if dep.is_symlink():
                    found.add(dep.resolve())
    return found


def busy(path, refs):
    return any(path == ref or path in ref.parents for ref in refs)


def stale_tree(path, days, ignore_git=False):
    cutoff = time.time() - days * 86400
    # Stat before scandir: our own directory read must not look like user activity.
    pending = [path]
    while pending:
        entry = pending.pop()
        stat = entry.lstat()
        if max(stat.st_mtime, stat.st_atime, stat.st_ctime) >= cutoff:
            return False
        if entry.is_dir() and not entry.is_symlink():
            with os.scandir(entry) as children:
                pending.extend(Path(child.path) for child in children if not (ignore_git and child.name == '.git'))
    return True


def candidates():
    roots = [BASE / name for name in ROOTS] + list(BASE.glob('quackles-*'))
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        # Match last night's bounded project discovery; never traverse data/products.
        for current, dirs, _ in os.walk(root, followlinks=False):
            path = Path(current)
            depth = len(path.relative_to(root).parts)
            dirs[:] = [name for name in dirs if name not in PROTECTED and not (path / name).is_symlink()]
            if (path / '.git').exists():
                yield path
                dirs[:] = []
            elif depth >= 3:
                dirs[:] = []


def cleanup_project(project):
    if busy(project, live_paths()):
        return
    stale_worktree = (project / '.git').is_file() and stale_tree(project, 14, ignore_git=True)
    # Cache discovery is bounded to three levels below a known source checkout.
    for current, dirs, _ in os.walk(project, followlinks=False):
        parent = Path(current)
        depth = len(parent.relative_to(project).parts)
        dirs[:] = [name for name in dirs if name not in PROTECTED and not (parent / name).is_symlink()]
        for name in list(dirs):
            cache = parent / name
            allowed = name in SAFE or (name == 'target' and (parent / 'Cargo.toml').is_file())
            allowed |= (name in {'build', 'dist', '.build'} or name.startswith('cmake-build-')) and any((parent / f).is_file() for f in MANIFESTS)
            if not allowed:
                continue
            dirs.remove(name)
            if git(project, 'ls-files', '--', str(cache.relative_to(project))):
                continue
            if not stale_tree(cache, 7) or busy(project, live_paths()):
                continue
            before = available()
            log('intent', cache, kind='regenerable-cache', df_available_before=before)
            shutil.rmtree(cache)
            log('deleted', cache, kind='regenerable-cache', df_available_before=before,
                df_available_after=available(), df_delta_bytes=available() - before)
        if depth >= 3:
            dirs[:] = []
    # Linked worktrees only: never recursively delete the primary clone/common store.
    if not stale_worktree or any((project / name).exists() for name in ('products', 'data', 'sessions', 'memories')):
        return
    if git(project, 'status', '--porcelain', '--untracked-files=all'):
        return
    if (project / '.gitmodules').exists() or git(project, 'ls-files', '--others', '--ignored', '--exclude-standard'):
        return
    worktrees = git(project, 'worktree', 'list', '--porcelain')
    entries = worktrees.split('\n\n')
    if any(('worktree ' + str(project)) in block.splitlines() and ('locked' in block or 'prunable' in block) for block in entries):
        return
    head = git(project, 'rev-parse', 'HEAD')
    branch = git(project, 'branch', '--show-current')
    # Check current remote heads rather than calling stale tracking refs "pushed".
    # Detached/no-upstream work remains unpushed and must be bundled.
    remote = merge = ''
    if branch:
        try:
            remote = git(project, 'config', '--get', 'branch.' + branch + '.remote')
            merge = git(project, 'config', '--get', 'branch.' + branch + '.merge')
        except subprocess.CalledProcessError:
            pass
    heads = git(project, 'ls-remote', '--heads', remote, merge).splitlines() if remote and remote != '.' and merge else []
    pushed = False
    if len(heads) == 1:
        remote_head = heads[0].split()[0]
        pushed = subprocess.run(['git', '-C', str(project), 'merge-base', '--is-ancestor', head, remote_head],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    bundle = None
    if not pushed:
        # Full self-contained archive: failure (including missing promisor objects)
        # keeps the worktree. No thin/incremental bundles or force removal.
        bundle = ARCHIVE / (project.name + '-' + head[:12] + '-' + str(time.time_ns()) + '.bundle')
        git(project, 'bundle', 'create', str(bundle), '--all', 'HEAD')
        with __import__('tempfile').TemporaryDirectory(dir=ARCHIVE) as empty:
            subprocess.run(['git', 'init', '--bare', '-q', empty], check=True)
            git(Path(empty), 'bundle', 'verify', str(bundle))
        log('bundled', project, head=head, bundle=str(bundle))
    if busy(project, live_paths()) or git(project, 'status', '--porcelain', '--untracked-files=all'):
        return
    before = available()
    log('intent', project, kind='stale-worktree', head=head, pushed=pushed, bundle=str(bundle) if bundle else None)
    common = Path(git(project, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
    git(common, 'worktree', 'remove', str(project))
    log('deleted', project, kind='stale-worktree', head=head, pushed=pushed,
        bundle=str(bundle) if bundle else None, df_available_before=before,
        df_available_after=available(), df_delta_bytes=available() - before)


def main():
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with (ARCHIVE / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for project in candidates():
            try:
                cleanup_project(project)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                # Never log captured git stdout/stderr (remote URLs may hold secrets).
                log('retained', project, reason=type(error).__name__)


if __name__ == '__main__':
    main()
