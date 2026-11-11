import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import fleet_runtimes as fr


class TaskKeyTests(unittest.TestCase):
    def test_wrapper_flags_and_shas_do_not_split_a_task(self):
        wrapped = ['env', 'FLEET_BUILD_JDK=17', 'sh', '-c', 'case $1 in ./gradlew|gradlew|gradle) ;; esac',
                   'fleet-build', 'android', './gradlew', '--no-daemon', '-Dorg.gradle.jvmargs=-Xmx4g', 'assembleFullDebug']
        self.assertEqual(fr.task_key(wrapped, 'noop'), 'noop:gradle assembleFullDebug')
        self.assertEqual(fr.task_key(['./gradlew', 'assembleFullDebug'], 'noop'), 'noop:gradle assembleFullDebug')
        self.assertEqual(fr.task_key("bash -c 'pip install -q pytest PyYAML && python -m pytest -q tests/x.py'"),
                         'pytest tests/x.py')
        self.assertEqual(fr.task_key(['bash', '-c', 'echo head=0123abcd4567ef; bun test']), 'bun test')


class PickTests(unittest.TestCase):
    def table(self, boat_n=0, boat_ok=0, boat_p50=None):
        return {'t': {'mbp': {'n': 9, 'ok': 9, 'p50': 1200.0},
                      **({'boat': {'n': boat_n, 'ok': boat_ok, 'p50': boat_p50}} if boat_n else {})}}

    def test_explores_until_min_ok_attempts_then_uses_the_fastest(self):
        self.assertEqual(fr.pick(self.table(), 't', {'mbp', 'boat'}, ['boat']), 'boat')
        self.assertEqual(fr.pick(self.table(1, 1, 30.0), 't', {'mbp', 'boat'}, ['boat']), 'boat')
        self.assertEqual(fr.pick(self.table(2, 2, 30.0), 't', {'mbp', 'boat'}, ['boat']), 'boat')
        self.assertEqual(fr.pick(self.table(2, 2, 3000.0), 't', {'mbp', 'boat'}, ['boat']), 'mbp')

    def test_failing_node_stops_being_explored_and_never_wins(self):
        self.assertEqual(fr.pick(self.table(2, 0), 't', {'mbp', 'boat'}, ['boat']), 'mbp')

    def test_ineligible_nodes_are_never_chosen(self):
        self.assertEqual(fr.pick(self.table(2, 2, 1.0), 't', {'mbp'}, ['boat']), 'mbp')
        self.assertIsNone(fr.pick({}, 't', {'mbp'}))


class FleetBuildRoutingTests(unittest.TestCase):
    """fleet-build end to end with fake backends: routing, fallback and recording."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('fleet-build', 'fleet_runtimes.py', 'fleet_paths.py'):
            shutil.copy2(ROOT / 'scripts' / name, self.root / name)
        fake = self.root / 'fleet'
        fake.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
with Path(os.environ['CALLS']).open('a') as f:
    f.write(json.dumps({'backend': Path(__file__).name, 'argv': sys.argv[1:]})+'\\n')
boat = '--node' in sys.argv and sys.argv[sys.argv.index('--node')+1]=='boat'
print('fleet: job abc-123 -> ' + ('boat' if boat else 'mbp'), file=sys.stderr)
sys.exit(int(os.environ.get('BOAT_RC' if boat else 'MBP_RC', '0')))
''')
        fake.chmod(0o700)
        shutil.copy2(fake, self.root / 'fleet-kueue')
        self.calls = self.root / 'calls'
        self.state = self.root / 'state'

    def invoke(self, *flags, **env):
        if self.calls.exists():
            self.calls.unlink()
        full = dict(os.environ, CALLS=str(self.calls), FLEET_STATE=str(self.state), **env)
        result = subprocess.run([str(self.root / 'fleet-build'), '--src', str(self.root), '--wait', '0', *flags,
                                 '--', 'python3', '-m', 'pytest', 'tests/x.py'],
                                cwd=self.root, env=full, capture_output=True, text=True)
        calls = [json.loads(l) for l in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def ledger(self):
        return [json.loads(l) for l in (self.state / 'runtimes.jsonl').read_text().splitlines()]

    def test_public_job_explores_boat_twice_then_follows_measurements(self):
        for _ in range(2):
            result, calls = self.invoke('--public')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c['backend'] for c in calls], ['fleet'])
            self.assertEqual(calls[0]['argv'][1:3], ['--node', 'boat'])
        self.assertEqual([(r['node'], r['rc']) for r in self.ledger()], [('boat', 0), ('boat', 0)])
        result, calls = self.invoke('--public')  # boat is measured fastest (mbp unmeasured): stay
        self.assertEqual([c['backend'] for c in calls], ['fleet'])

    def test_failed_exploration_reruns_on_the_default_lane_and_is_recorded(self):
        result, calls = self.invoke('--public', BOAT_RC='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c['backend'] for c in calls], ['fleet', 'fleet-kueue'])
        self.assertEqual([(r['node'], r['rc']) for r in self.ledger()], [('boat', 1), ('mbp', 0)])
        self.assertEqual(self.ledger()[0]['repo'], self.root.name)

    def test_private_and_local_data_jobs_never_route_to_boat(self):
        for flags in ([], ['--public', '--local-data']):
            result, calls = self.invoke(*flags)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c['backend'] for c in calls], ['fleet-kueue'])
        self.assertEqual({r['node'] for r in self.ledger()}, {'mbp'})

    def test_explicit_node_wins_over_measurements(self):
        result, calls = self.invoke('--public', '--node', 'mbp')
        self.assertEqual([c['backend'] for c in calls], ['fleet-kueue'])


if __name__ == '__main__':
    unittest.main()
