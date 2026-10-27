#!/usr/bin/env python3
"""Bounded system-only atop rollups; never delete an archive without a verified shard."""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time

SCHEMA = 1
LABELS = 'CPU,CPL,MEM,SWP,PAG,PSI,DSK,NET'
NAME = re.compile(r'atop_(\d{8})$')
DISK = re.compile(r'(?:sd[a-z]+|nvme\d+n\d+|mmcblk\d+)$')
NET = re.compile(r'(?:en\w+|eth\d+|wl\w+)$')


def identity(path):
    s = path.stat(follow_symlinks=False)
    if path.is_symlink() or not path.is_file():
        raise ValueError('source must be a regular, non-symlink file')
    return dict(device=s.st_dev, inode=s.st_ino, size=s.st_size, mtime_ns=s.st_mtime_ns)


def day_of(path):
    match = NAME.fullmatch(path.name)
    if not match:
        raise ValueError('invalid archive filename')
    return dt.datetime.strptime(match[1], '%Y%m%d').date()


def normalized(r):
    """Atop interval counters are deltas already; sectors are always 512 bytes."""
    elapsed = float(r['elapsed'])
    out = {}
    def put(name, value, unit, event=False):
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            out[name] = (float(value), unit, event)
    cpu = r['CPU']
    fields = ('stime', 'utime', 'ntime', 'itime', 'wtime', 'Itime', 'Stime', 'steal')
    total = sum(cpu.get(k, 0) for k in fields)
    if total > 0:
        for k in fields:
            put('cpu.' + k, cpu.get(k, 0) * 100 / total, 'percent')
    for k in ('lavg1', 'lavg5', 'lavg15'):
        put('load.' + k, r['CPL'].get(k), 'load')
    for label, fields in [('MEM', ('physmem', 'freemem', 'availablemem', 'cachemem', 'buffermem', 'slabmem', 'shmem')),
                          ('SWP', ('totswap', 'freeswap', 'swcac', 'committed', 'commitlim'))]:
        for k in fields:
            put(label.lower() + '.' + k, r[label].get(k), 'bytes')
    for k in ('cs10', 'cs60', 'cs300', 'ms10', 'ms60', 'ms300', 'mf10', 'mf60', 'mf300', 'ios10', 'ios60', 'ios300', 'iof10', 'iof60', 'iof300'):
        put('pressure.' + k, r['PSI'].get(k), 'percent')
    for k in ('pgscans', 'allocstall', 'pgins', 'pgouts', 'swins', 'swouts', 'oomkills'):
        v = r['PAG'].get(k)
        if isinstance(v, (int, float)):
            put('paging.' + k, v / elapsed, 'events/s')
            if k == 'oomkills':
                put('events.oomkills', v, 'events', True)
    for disk in r['DSK']:
        name = disk['dskname']
        if not DISK.fullmatch(name):
            continue
        prefix = 'disk.' + name + '.'
        for k in ('nread', 'nwrite'):
            put(prefix + k, disk.get(k, 0) / elapsed, 'operations/s')
        for k in ('nrsect', 'nwsect'):
            put(prefix + k, disk.get(k, 0) * 512 / elapsed, 'bytes/s')
        put(prefix + 'busy', disk.get('io_ms', 0) / elapsed / 10, 'percent')
        put(prefix + 'queue', disk.get('avque', 0) / elapsed / 1000, 'requests')
        put(prefix + 'inflight', disk.get('inflight'), 'requests')
    for net in r['NET']:
        if NET.fullmatch(net['name']):
            for k in ('rbyte', 'sbyte', 'rerrs', 'serrs', 'rdrop', 'sdrop'):
                put('network.' + net['name'] + '.' + k, net.get(k, 0) / elapsed,
                    'bytes/s' if k.endswith('byte') else 'events/s')
    if len(out) > 300:
        raise ValueError('stable metric budget exceeded (300)')
    return out


class Buckets:
    def __init__(self, db):
        self.db = db
        self.pending = {60: {}, 300: {}}
        self.metric_units = {}
        self.rows = 0

    def flush(self, resolution, before=float('inf')):
        buckets = self.pending[resolution]
        for key in list(buckets):
            start, metric = key
            if start + resolution > before:
                continue
            samples = buckets.pop(key)
            values = sorted(v for v, _, _ in samples)
            covered = sum(w for _, w, _ in samples)
            weighted = sum(v * w for v, w, _ in samples)
            events = sum(e for _, _, e in samples) if samples[0][2] is not None else None
            self.db.execute('INSERT INTO bucket VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (resolution, start, metric, len(samples), covered, weighted / covered,
                 values[0], values[-1], values[math.ceil(.95 * len(values)) - 1], events, SCHEMA))
            self.rows += 1

    def add(self, start, end, metrics):
        for resolution in (60, 300):
            self.flush(resolution, start)
            for name, (value, unit, event) in metrics.items():
                if name not in self.metric_units:
                    self.metric_units[name] = unit
                    self.db.execute('INSERT INTO metric VALUES (?,?)', (name, unit))
                t = start
                while t < end:
                    bucket = math.floor(t / resolution) * resolution
                    stop = min(end, bucket + resolution)
                    self.pending[resolution].setdefault((bucket, name), []).append(
                        (value, stop - t, value * (stop - t) / (end - start) if event else None))
                    t = stop


def verify(path, expected=None):
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        manifest = json.loads(db.execute('SELECT json FROM manifest').fetchone()[0])
        if manifest['schema'] != SCHEMA or manifest['accepted_samples'] < 1:
            raise ValueError('empty or incompatible conversion')
        rows = dict(db.execute('SELECT resolution,COUNT(*) FROM bucket GROUP BY resolution'))
        # The initial shard has both resolutions; 60s rows may expire later.
        if rows.get(300, 0) < 1 or sum(rows.values()) != manifest['rows']:
            raise ValueError('aggregate row coverage mismatch')
        if manifest['accepted_samples'] + manifest['reset_samples'] != manifest['samples']:
            raise ValueError('sample accounting mismatch')
        if manifest['reset_samples'] > max(8, manifest['samples'] // 100):
            raise ValueError('excessive excluded/reset samples; retain raw for manual review')
        if db.execute('SELECT COUNT(*) FROM bucket WHERE n<1 OR covered_seconds<=0 OR covered_seconds>resolution+0.001 OR min>mean+ABS(min)*1e-12+1e-12 OR mean>max+ABS(max)*1e-12+1e-12 OR p95<min OR p95>max OR schema_version<>1').fetchone()[0]:
            raise ValueError('aggregate invariant failed')
        if expected is not None and manifest['source'] != expected:
            raise ValueError('source stat identity differs')
        return manifest


def convert(args):
    raw = Path(args.raw)
    day = day_of(raw)
    if day >= dt.date.today():
        raise ValueError('active/current or future archive is protected')
    before = identity(raw)
    original = json.loads(args.source_identity) if args.source_identity else before
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.atop-rollup-', suffix='.sqlite', dir=dest.parent)
    os.close(fd)
    proc = None
    try:
        with contextlib.closing(sqlite3.connect(temp)) as db:
            db.executescript('''
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE metric(metric_id TEXT PRIMARY KEY, unit TEXT NOT NULL);
            CREATE TABLE bucket(resolution INTEGER, bucket_start_utc INTEGER, metric_id TEXT REFERENCES metric,
              n INTEGER, covered_seconds REAL, mean REAL, min REAL, max REAL, p95 REAL, event_count REAL,
              schema_version INTEGER, PRIMARY KEY(resolution,bucket_start_utc,metric_id)) WITHOUT ROWID;
            CREATE TABLE manifest(json TEXT NOT NULL);
            ''')
            buckets = Buckets(db)
            reader = subprocess.check_output([args.atop, '-V'], stderr=subprocess.STDOUT, text=True).strip()
            env = dict(os.environ, LC_ALL='C', HOME='/nonexistent', TERM='dumb')
            proc = subprocess.Popen([args.atop, '-J' + LABELS, '-r', str(raw)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
            count = accepted = resets = gaps = 0
            covered = 0.0
            previous = None
            host = None
            first = last = None
            for line in proc.stdout:
                if not line.strip():
                    continue
                if not line.startswith('{'):
                    raise ValueError('reader emitted non-JSON; refusing incomplete conversion')
                r = json.loads(line)
                if not all(k in r for k in ('CPU', 'CPL', 'MEM', 'SWP', 'PAG', 'PSI', 'DSK', 'NET')):
                    raise ValueError('reader format is incompatible')
                count += 1
                stamp, elapsed = int(r['timestamp']), float(r['elapsed'])
                if host is not None and host != r['host']:
                    raise ValueError('archive contains mixed hosts')
                host = r['host']
                if first is None:
                    first = stamp
                last = stamp
                # A first raw record may represent all activity since boot. Never turn
                # it into an interval rate. Reject long/reset/overlapping intervals too.
                if previous is None or not 0 < elapsed <= 120 or stamp <= previous or stamp - elapsed < previous - .001:
                    resets += 1
                    previous = stamp
                    continue
                if stamp - elapsed > previous + 1:
                    gaps += 1
                start = stamp - elapsed
                metrics = normalized(r)
                buckets.add(start, stamp, metrics)
                covered += elapsed
                accepted += 1
                previous = stamp
            if proc.wait() != 0:
                raise ValueError('atop reader failed; source retained')
            for resolution in (60, 300):
                buckets.flush(resolution)
            manifest = dict(schema=SCHEMA, filename=raw.name, archive_date=day.isoformat(), source=original,
                reader=reader, host=host, samples=count, accepted_samples=accepted, reset_samples=resets,
                gaps=gaps, covered_seconds=covered, first_timestamp=first, last_timestamp=last,
                rows=buckets.rows, series=len(buckets.metric_units), converted_utc=int(time.time()),
                policy='system allowlist; first/reset/overlap/>120s samples excluded; sample nearest-rank p95')
            db.execute('INSERT INTO manifest VALUES (?)', (json.dumps(manifest, sort_keys=True),))
            db.commit()
        if identity(raw) != before:
            raise ValueError('source changed during conversion')
        verify(Path(temp), original)
        with open(temp, 'rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temp, dest)
        print(json.dumps(manifest, sort_keys=True))
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        Path(temp).unlink(missing_ok=True)


def maintain(args):
    rawdir, rollups = Path(args.raw_dir), Path(args.rollups)
    rollups.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    with open(rollups / '.retention.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = rollups / 'retirement-ledger.jsonl'
        for raw in sorted(rawdir.glob('atop_*')):
            day = day_of(raw)
            if day >= today - dt.timedelta(days=7):
                continue
            shard = rollups / (raw.name + '.sqlite')
            if not shard.is_file():
                print(json.dumps(dict(retained=raw.name, reason='missing aggregate')))
                continue
            stat = identity(raw)
            m = verify(shard, stat)
            if m['filename'] != raw.name or m['archive_date'] != day.isoformat():
                raise ValueError('manifest filename/date mismatch')
            if not args.retire:
                print(json.dumps(dict(eligible=raw.name, bytes=stat['size'])))
                continue
            # Keep the descriptor identity across the final unlink check. Archive dir
            # is root-owned; only exact date-named regular files can be retired.
            before = os.statvfs(rawdir)
            if identity(raw) != stat:
                raise ValueError('source changed before retirement')
            raw.unlink()
            directory_fd = os.open(rawdir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            after = os.statvfs(rawdir)
            event = dict(time_utc=int(time.time()), retired=raw.name, source=stat,
                aggregate_bytes=shard.stat().st_size, covered_seconds=m['covered_seconds'],
                df_available_before=before.f_bavail * before.f_frsize,
                df_available_after=after.f_bavail * after.f_frsize,
                df_delta_bytes=(after.f_bavail * after.f_frsize - before.f_bavail * before.f_frsize))
            with open(ledger, 'a') as out:
                out.write(json.dumps(event, sort_keys=True) + '\n')
                out.flush()
                os.fsync(out.fileno())
            print(json.dumps(event, sort_keys=True))
        for shard in sorted(rollups.glob('atop_*.sqlite')):
            day = day_of(Path(shard.stem))
            if day < today - dt.timedelta(days=365):
                # Never discard the sole conversion of a raw file still awaiting retirement.
                if not (rawdir / shard.stem).exists():
                    shard.unlink()
            elif day < today - dt.timedelta(days=30):
                with contextlib.closing(sqlite3.connect(shard)) as db:
                    db.execute('DELETE FROM bucket WHERE resolution=60')
                    m = json.loads(db.execute('SELECT json FROM manifest').fetchone()[0])
                    m['rows'] = db.execute('SELECT COUNT(*) FROM bucket').fetchone()[0]
                    db.execute('UPDATE manifest SET json=?', (json.dumps(m, sort_keys=True),))
                    db.commit()


def remote(args):
    rawdir, rollups = Path(args.raw_dir), Path(args.rollups)
    rollups.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    package = Path(args.atop_package)
    if not package.is_file():
        raise ValueError('matching cached atop package required for remote reader')
    with open(rollups / '.conversion.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        processed = 0
        for raw in sorted(rawdir.glob('atop_*')):
            if day_of(raw) >= dt.date.today():
                continue
            stat = identity(raw)
            dest = rollups / (raw.name + '.sqlite')
            if dest.exists():
                verify(dest, stat)
                continue
            with tempfile.TemporaryDirectory(prefix='atop-fleet-', dir='/workspace/cache') as fetched:
                command = ['flock', '-w', '30', '/tmp/mbp-turnstile.lock', 'true']
                subprocess.run(command, check=True)
                cmd = ['flock', '-s', '-w', '30', '/tmp/mbp-quiet.lock', str(Path.home() / '.local/bin/fleet-build'),
                    '--node', 'mbp', '--mem', '1G', '--cpus', '1', '--timeout', '3600', '--wait', '0',
                    '--src', str(root), '--input', str(raw) + ':input/' + raw.name,
                    '--input', str(package) + ':input/atop.pkg.tar.zst', '--fetch', 'output/' + dest.name,
                    '--out', fetched, '--', 'bash', '-c',
                    'mkdir -p reader output && tar -xf input/atop.pkg.tar.zst -C reader usr/bin/atop && exec python3 atop-rollup.py convert "$@"',
                    'atop-convert', '--atop', './reader/usr/bin/atop', '--raw', 'input/' + raw.name,
                    '--output', 'output/' + dest.name, '--source-identity', json.dumps(stat)]
                subprocess.run(cmd, cwd=root, check=True)
                candidate = Path(fetched) / dest.name
                verify(candidate, stat)
                if identity(raw) != stat:
                    raise ValueError('original archive changed during remote conversion')
                # Copy only the small verified shard, never an expanded archive.
                import shutil
                temporary = dest.with_suffix('.sqlite.import')
                shutil.copyfile(candidate, temporary)
                os.chmod(temporary, 0o600)
                verify(temporary, stat)
                os.replace(temporary, dest)
            processed += 1
            if args.limit and processed >= args.limit:
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('convert')
    p.add_argument('--raw', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--source-identity')
    p.add_argument('--atop', default='/usr/bin/atop')
    p.set_defaults(func=convert)
    p = sub.add_parser('verify')
    p.add_argument('shard')
    p.set_defaults(func=lambda a: print(json.dumps(verify(Path(a.shard)), sort_keys=True)))
    for action, function in [('maintain', maintain), ('remote', remote)]:
        p = sub.add_parser(action)
        p.add_argument('--raw-dir', default='/mnt/zer0models/hw_monitor/atop')
        p.add_argument('--rollups', default='/mnt/zer0models/hw_monitor/rollups')
        if action == 'maintain':
            p.add_argument('--retire', action='store_true', help='approved retirement after verified coverage only')
        else:
            p.add_argument('--atop-package', default='/var/cache/pacman/pkg/atop-2.13.0-1.1-x86_64_v3.pkg.tar.zst')
            p.add_argument('--limit', type=int, default=1, help='closed days; 0 means full backfill')
        p.set_defaults(func=function)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
