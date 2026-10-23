import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('atop_rollup', Path(__file__).parents[1] / 'scripts/atop-rollup.py')
rollup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollup)


class RollupTests(unittest.TestCase):
    def db(self):
        db = sqlite3.connect(':memory:')
        db.executescript('CREATE TABLE metric(metric_id TEXT PRIMARY KEY,unit TEXT); CREATE TABLE bucket(resolution,bucket_start_utc,metric_id,n,covered_seconds,mean,min,max,p95,event_count,schema_version);')
        self.addCleanup(db.close)
        return db

    def test_duration_weighting_and_exact_underlying_p95(self):
        db = self.db()
        b = rollup.Buckets(db)
        b.add(0, 10, {'load': (1., 'load', False)})
        b.add(10, 60, {'load': (9., 'load', False)})
        b.add(60, 70, {'load': (100., 'load', False)})
        for resolution in (60, 300):
            b.flush(resolution)
        mean, p95, n, coverage = db.execute('SELECT mean,p95,n,covered_seconds FROM bucket WHERE resolution=300').fetchone()
        self.assertAlmostEqual(mean, 1460 / 70)
        self.assertEqual((p95, n, coverage), (100., 3, 70.))

    def test_boundaries_split_coverage_and_event_counts(self):
        db = self.db()
        b = rollup.Buckets(db)
        b.add(55, 65, {'oom': (2., 'events', True)})
        b.flush(60)
        rows = db.execute('SELECT covered_seconds,event_count FROM bucket ORDER BY bucket_start_utc').fetchall()
        self.assertEqual(rows, [(5., 1.), (5., 1.)])

    def test_interval_deltas_are_not_differenced_again(self):
        r = {'elapsed': 10, 'CPU': {'utime': 100, 'itime': 900}, 'CPL': {}, 'MEM': {}, 'SWP': {},
             'PSI': {}, 'PAG': {'oomkills': 2, 'swins': 100},
             'DSK': [{'dskname': 'sda', 'nrsect': 20, 'io_ms': 12000}],
             'NET': [{'name': 'enp4s0', 'rbyte': 1000}, {'name': 'veth123', 'rbyte': 99999}]}
        m = rollup.normalized(r)
        self.assertEqual(m['cpu.utime'][0], 10)
        self.assertEqual(m['disk.sda.nrsect'][0], 1024)
        self.assertEqual(m['disk.sda.busy'][0], 120)
        self.assertEqual(m['paging.swins'][0], 10)
        self.assertEqual(m['events.oomkills'][0], 2)
        self.assertNotIn('network.veth123.rbyte', m)

    def test_active_file_is_protected_before_reader_starts(self):
        import argparse
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / ('atop_' + rollup.dt.date.today().strftime('%Y%m%d'))
            raw.touch()
            with self.assertRaisesRegex(ValueError, 'protected'):
                rollup.convert(argparse.Namespace(raw=str(raw), output=str(Path(d) / 'x.sqlite'), source_identity=None, atop='/missing'))
            self.assertTrue(raw.exists())

    def test_missing_aggregate_never_deletes_raw(self):
        import argparse
        with tempfile.TemporaryDirectory() as d:
            rawdir, out = Path(d) / 'raw', Path(d) / 'rollups'
            rawdir.mkdir()
            raw = rawdir / 'atop_20200101'
            raw.write_bytes(b'preserve')
            rollup.maintain(argparse.Namespace(raw_dir=str(rawdir), rollups=str(out), retire=True))
            self.assertTrue(raw.exists())


if __name__ == '__main__':
    unittest.main()
