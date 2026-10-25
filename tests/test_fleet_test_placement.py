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
from fleet_test_placement import choose, python_test


def queue(cpu='4', memory='8Gi'):
    return {'spec': {'resourceGroups': [{'flavors': [{'name': 'node-mbp', 'resources': [
        {'name': 'cpu', 'nominalQuota': '4'}, {'name': 'memory', 'nominalQuota': '10441814016'}]}]}]},
        'status': {'flavorsReservation': [{'name': 'node-mbp', 'resources': [
            {'name': 'cpu', 'total': cpu}, {'name': 'memory', 'total': memory}]}]}}


class PlacementTests(unittest.TestCase):
    def test_saturated_mbp_overflows_only_direct_python_test_runners(self):
        for command in (['python3', '-m', 'pytest'], ['python3', '-m', 'unittest', 'discover'], ['pytest', '-q']):
            with self.subTest(command=command):
                result = choose(command, '3G', '2', queue())
                self.assertEqual(result['selected_lane'], 'phones')
                self.assertEqual(result['mbp_free']['cpu'], '0')
                self.assertEqual(result['phone_resource_policy'], 'overflow: mem unspecified, default not applied on phone (O10)')
        for command in (['bash', '-lc', 'pytest'], ['bun', 'test'], ['cargo', 'test'], ['python3', 'server.py']):
            self.assertFalse(python_test(command))
            self.assertEqual(choose(command, '128M', '1', queue())['selected_lane'], 'mbp')

    def test_free_mbp_capacity_stays_on_mbp_and_defaults_remain_honest(self):
        result = choose(['pytest'], '3G', '2', queue('1', '1Gi'))
        self.assertEqual(result['selected_lane'], 'mbp')
        self.assertEqual(result['requested_memory'], '3G')
        self.assertEqual(result['mbp_free']['cpu'], '3')
        self.assertEqual(choose(['pytest'], '3G', '2', queue('0', '8Gi'))['selected_lane'], 'phones')

    def test_held_queue_or_cordoned_node_overflows_even_with_free_quota(self):
        held = queue('0', '0')
        held['spec']['stopPolicy'] = 'Hold'
        result = choose(['pytest'], '128M', '1', held)
        self.assertEqual(result['selected_lane'], 'phones')
        self.assertEqual(result['reason'], 'mbp-queue-held')
        node = {'spec': {'unschedulable': True}, 'status': {'conditions': [
            {'type': kind, 'status': 'True' if kind == 'Ready' else 'False'}
            for kind in ('Ready', 'DiskPressure', 'MemoryPressure', 'PIDPressure')]}}
        result = choose(['pytest'], '128M', '1', queue('0', '0'), node=node)
        self.assertEqual(result['selected_lane'], 'phones')
        self.assertEqual(result['reason'], 'mbp-node-unavailable')

    def test_explicit_memory_above_one_gib_never_overflows(self):
        self.assertEqual(choose(['pytest'], '2G', '1', queue(), True)['reason'],
                         'explicit-memory-above-phone-test-scope')
        result = choose(['pytest'], '1G', '1', queue(), True)
        self.assertEqual(result['selected_lane'], 'phones')
        self.assertIn('no caps applied on phone (O10)', result['phone_resource_policy'])


class WrapperPlacementTests(unittest.TestCase):
    def dispatch(self, options, command=('python3', '-m', 'unittest')):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ('fleet-build', 'fleet_test_placement.py', 'fleet_queue_health.py'):
                shutil.copy2(ROOT / 'scripts' / filename, root / filename)
            transport = ('#!' + sys.executable + '\nimport json,os,sys\n'
                         'print(json.dumps({"transport":os.path.basename(sys.argv[0]),"argv":sys.argv[1:],'
                         '"placement":json.loads(os.environ.get("FLEET_TEST_PLACEMENT") or "null")}))\n')
            for filename in ('fleet', 'fleet-kueue'):
                (root / filename).write_text(transport)
                (root / filename).chmod(0o700)
            (root / 'kubectl').write_text('#!' + sys.executable + '\nimport json\nprint(' + repr(json.dumps(queue())) + ')\n')
            (root / 'kubectl').chmod(0o700)
            result = subprocess.run(['bash', str(root / 'fleet-build'), '--class', 'test', '--src', str(root),
                                     '--wait', '0', *options, '--', *command], cwd=root,
                                    env={**os.environ, 'PATH':str(root)+os.pathsep+os.environ['PATH']},
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_default_and_auto_overflow_before_submission_without_phone_caps(self):
        for options in ([], ['--node', 'auto'], ['--mem', '512M', '--cpus', '1']):
            result = self.dispatch(options)
            self.assertEqual(result['transport'], 'fleet')
            self.assertIn('--guest', result['argv'])
            self.assertIn('--python-venv', result['argv'])
            self.assertIn('test', result['argv'])
            self.assertNotIn('--mem', result['argv'])
            self.assertNotIn('--cpus', result['argv'])
            self.assertEqual(result['placement']['selected_lane'], 'phones')

    def test_explicit_source_includes_survive_both_dispatch_paths(self):
        for node in ([], ['--node', 'mbp']):
            result = self.dispatch([*node, '--src-include', 'scripts/', '--src-include', 'tests/test_x.py'])
            values = [result['argv'][index + 1] for index, value in enumerate(result['argv'])
                      if value == '--src-include']
            self.assertEqual(values, ['scripts/', 'tests/test_x.py'])

    def test_explicit_mbp_and_large_memory_requests_are_honored(self):
        for options in (['--node', 'mbp'], ['--mem', '2G']):
            result = self.dispatch(options)
            self.assertEqual(result['transport'], 'fleet-kueue')
        self.assertEqual(self.dispatch([], ('cargo', 'test'))['transport'], 'fleet-kueue')


if __name__ == '__main__':
    unittest.main()
