"""Creator-side artifact leases; publication never replaces an existing lease."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import socket
import tempfile
import time

TTL = 604800


def payload(path, owner, node, kind, keep_receipts=()):
    receipts = list(keep_receipts)
    for receipt in receipts:
        relative = PurePosixPath(receipt)
        if not receipt or relative.is_absolute() or '..' in relative.parts or '\\' in receipt:
            raise ValueError('keep_receipts must be safe relative paths')
    if not owner or not node or not kind:
        raise ValueError('owner, node and kind are required')
    return dict(schema='z0.artifact-lease.v1', owner=owner, path=str(path), node=node,
                kind=kind, created_at=int(time.time()), ttl=TTL, keep_receipts=receipts)


def create(path, owner, node, kind, keep_receipts=()):
    directory = Path(path).resolve()
    value = payload(directory, owner, node, kind, keep_receipts)
    lease = directory / '.artifact-lease.json'
    fd, temporary = tempfile.mkstemp(prefix='.artifact-lease-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, lease)
        except FileExistsError:
            return False
        return True
    finally:
        os.unlink(temporary)


def shell_create(path, owner, node, kind, keep_receipts=()):
    """POSIX shell publication, also usable with Android's native toolbox.

    The caller supplies a trusted shell expression for its job directory. Resolve
    HOME on the worker, not on the submitting machine. JSON-escape its path using
    shell substitutions before publishing the complete temporary inode.
    """
    value = payload('', owner, node, kind, keep_receipts)
    del value['path']
    encoded = json.dumps(value, sort_keys=True)[:-1]
    return (f'd={path}; mkdir -p "$d" && (cd "$d" || exit; '
            'p=$(pwd -P) || exit; '
            # Fleet directories never contain newline, quote or backslash; fail closed.
            'case "$p" in *\'"\'*|*\'\\\'*|*"\n"*) exit 1;; esac; '
            't=$(mktemp .artifact-lease-XXXXXX) && '
            f'printf \'%s, "path": "%s"}}\\n\' {shlex.quote(encoded)} "$p" > "$t" && '
            '{ ln "$t" .artifact-lease.json 2>/dev/null || [ -e .artifact-lease.json ]; }; '
            'rc=$?; rm -f "$t"; exit "$rc")')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('--owner', required=True)
    parser.add_argument('--node', default=socket.gethostname())
    parser.add_argument('--kind', required=True)
    parser.add_argument('--keep-receipt', action='append', default=[])
    args = parser.parse_args()
    create(args.path, args.owner, args.node, args.kind, args.keep_receipt)


if __name__ == '__main__':
    main()
