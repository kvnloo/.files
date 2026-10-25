#!/usr/bin/env python3
"""Retire expired fetched src/ trees, preserving complete copies and receipts.

No deletion: source copies are atomically renamed to the bulk archive. Unknown
lease, terminal status, process visibility, or liveness means keep.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import time

from fleet_paths import runs_dir, storage_policy


def terminal(job):
    try:
        marker = job / 'exit'
        if not marker.is_symlink() and marker.read_text().strip().lstrip('-').isdigit():
            return True
    except OSError:
        pass
    try:
        receipt = json.loads(job.with_suffix('.json').read_text())
        value = receipt['terminal']['exit_code']
        return isinstance(value, int) and not isinstance(value, bool)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def retain(apply=False):
    runs = runs_dir()
    days = storage_policy().get('source_retention_days', 7)
    archive = runs.parent / 'fleet-source-archive'
    archive.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('artifact_leases', Path(__file__).with_name('artifact-leases.py'))
    leases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(leases)
    with (archive / '.retention.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        refs, errors = leases.local_references('groot', leases.backend())
        if errors:
            print(json.dumps({'event': 'kept', 'reason': 'liveness unknown', 'errors': errors}))
            return 0
        cutoff = time.time() - days * 86400
        for job in runs.iterdir():
            source = job / 'src'
            if job.is_symlink() or not job.is_dir() or source.is_symlink() or not source.is_dir():
                continue
            try:
                lease = json.loads((job / leases.SIDECAR).read_text())
                if leases.validate(lease, job, socket.gethostname(), time.time()) or lease.get('kind') != 'spool':
                    continue
                if not terminal(job) or max(source.stat().st_mtime, source.stat().st_ctime) >= cutoff:
                    continue
                if any(Path(ref).is_relative_to(source) or source.is_relative_to(Path(ref)) for ref in refs):
                    continue
                # Require all descendants old, not just the directory entry.
                recent = any(max((Path(base) / name).lstat().st_mtime, (Path(base) / name).lstat().st_ctime) >= cutoff
                             for base, dirs, files in os.walk(source) for name in dirs + files)
                destination = archive / job.name
                if recent or destination.exists() or source.stat().st_dev != archive.stat().st_dev:
                    continue
                row = {'event': 'archive-source' if apply else 'would-archive-source', 'source': str(source), 'archive': str(destination)}
                if apply:
                    os.rename(source, destination)
                    with (archive / 'receipts.jsonl').open('a') as stream:
                        stream.write(json.dumps({**row, 'timestamp': time.time(), 'lease': lease}) + '\n')
                print(json.dumps(row))
            except (OSError, ValueError, TypeError):
                # Partial fetches and ambiguous metadata are not cleanup authority.
                continue
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    raise SystemExit(retain(parser.parse_args().apply))
