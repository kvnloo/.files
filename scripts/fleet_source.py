"""Select existing source files consistently for fleet staging, never Git metadata."""
from contextlib import contextmanager
import fnmatch
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import tarfile


def _existing(source, names):
    seen = set()
    for name in names:
        path = Path(os.fsdecode(name))
        if not name or path == Path('.') or path.is_absolute() or '..' in path.parts or '.git' in path.parts:
            continue
        if name in seen:
            continue
        seen.add(name)
        absolute = source / path
        if absolute.is_symlink() or absolute.is_file():
            yield name
        elif absolute.is_dir():
            # Gitlinks may select a checked-out submodule. Never recurse through
            # tar itself, which would also transport the submodule's .git file.
            for child in source_files(absolute):
                yield os.fsencode(path / os.fsdecode(child))


def _source_files(source):
    """Yield relative filename bytes, excluding sparse/absent and ignored files."""
    source = Path(source).resolve()
    probe = subprocess.run(['git', '-C', str(source), 'rev-parse', '--is-inside-work-tree'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if probe.returncode == 0 and probe.stdout.strip() == b'true':
        selected = subprocess.check_output([
            'git', '-c', 'core.sparseCheckout=false', '-C', str(source),
            'ls-files', '-t', '-z', '--cached', '--others', '--exclude-standard'],
            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
        names = (entry[2:] for entry in selected.split(b'\0') if entry and entry[:2] != b'S ')
        yield from _existing(source, names)
        return

    # Use a plain tree walk outside Git. A temporary, separate index lets Git
    # apply its own nested .gitignore/negation semantics without touching source.
    names = []
    for root, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name != '.git']
        links = [name for name in directories if (Path(root) / name).is_symlink()]
        directories[:] = [name for name in directories if name not in links]
        for name in files + links:
            path = (Path(root) / name).relative_to(source)
            if '.git' not in path.parts:
                names.append(os.fsencode(path))
    if not names:
        return
    with tempfile.TemporaryDirectory(prefix='fleet-source-ignore-') as metadata:
        subprocess.run(['git', 'init', '--quiet', metadata], check=True)
        ignored = subprocess.run([
            'git', '--git-dir', str(Path(metadata) / '.git'), '--work-tree', str(source),
            'check-ignore', '--no-index', '-z', '--stdin'], input=b'\0'.join(names) + b'\0',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=source, check=False)
        if ignored.returncode not in (0, 1):
            raise subprocess.CalledProcessError(ignored.returncode, ignored.args, ignored.stdout, ignored.stderr)
        excluded = set(ignored.stdout.split(b'\0'))
        yield from _existing(source, (name for name in names if name not in excluded))


def source_files(source, includes=()):
    """Select relative files; explicit inclusions are paths or shell-style globs."""
    for pattern in includes:
        path = Path(pattern)
        if not pattern or path.is_absolute() or '..' in path.parts:
            raise ValueError(f'invalid --src-include: {pattern!r}')
    matched = set()
    for name in _source_files(source):
        text = os.fsdecode(name)
        choices = [pattern for pattern in includes
                   if text == pattern.rstrip('/') or text.startswith(pattern.rstrip('/') + '/')
                   or fnmatch.fnmatchcase(text, pattern)]
        if not includes or choices:
            matched.update(choices)
            yield name
    missing = set(includes) - matched
    if missing:
        raise ValueError(f'--src-include matched no existing, non-ignored files: {sorted(missing)!r}')


def _fingerprints(source, includes):
    result = {}
    for name in source_files(source, includes):
        path = source / os.fsdecode(name)
        info = path.lstat()
        result[name] = (info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                        info.st_ino, os.readlink(path) if path.is_symlink() else None)
    return result


def _provenance(source):
    environment = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}
    head = subprocess.run(['git', '-C', str(source), 'rev-parse', '--verify', 'HEAD'],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment, check=False)
    status = subprocess.run(['git', '-C', str(source), 'status', '--porcelain', '-z'],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment, check=False)
    return {'git_head': head.stdout.decode().strip() if head.returncode == 0 else None,
            'dirty': bool(status.stdout) if status.returncode == 0 else None}


@contextmanager
def source_snapshot(source, includes=(), directory=None):
    """Freeze an attributable archive; refuse a tree changing during capture."""
    source = Path(source).resolve()
    if directory is None:
        from fleet_paths import runs_dir
        directory = runs_dir().parent / 'fleet-source-snapshots'
    directory = Path(directory).resolve()
    if directory.is_relative_to(source):
        raise ValueError('source snapshot storage must be outside --src')
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='source-', dir=directory) as temporary:
        archive = Path(temporary) / 'source.tar.gz'
        for attempt in range(3):
            try:
                provenance = _provenance(source)
                initial = _fingerprints(source, includes)
                with tarfile.open(archive, 'w:gz', dereference=False) as packed:
                    for name in sorted(initial):
                        packed.add(source / os.fsdecode(name), arcname=os.fsdecode(name), recursive=False)
                if initial != _fingerprints(source, includes) or provenance != _provenance(source):
                    continue
                with archive.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                metadata = {**provenance, 'sha256': digest, 'format': 'tar+gzip',
                            'files': len(initial), 'source_bytes': sum(value[1] for value in initial.values()),
                            'archive_bytes': archive.stat().st_size, 'includes': list(includes)}
                break
            except FileNotFoundError:
                continue
        else:
            raise RuntimeError('source changed during snapshot capture; no payload was submitted')
        yield archive, metadata
