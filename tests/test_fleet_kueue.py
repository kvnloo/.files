import contextlib
import io
import json
import os
import pathlib
import runpy
import unittest
import tempfile
from types import SimpleNamespace
from unittest import mock


class WorkloadClassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classify = staticmethod(runpy.run_path(str(pathlib.Path(__file__).parents[1] / 'scripts/fleet-kueue'))['workload_class'])

    def test_pytest_before_exclusive(self):
        self.assertEqual(self.classify(None, ['python3', '-m', 'pytest'], '4', 4), 'test')
        self.assertEqual(self.classify(None, ['/opt/venv/bin/pytest'], '2', 4), 'test')

    def test_explicit_override(self):
        self.assertEqual(self.classify('build', ['pytest'], '4', 4), 'build')

    def test_full_quota_benchmark(self):
        self.assertEqual(self.classify(None, ['python3', 'measure.py'], '4', 4), 'bench')
        self.assertEqual(self.classify(None, ['make'], '2', 4), 'build')

    def test_no_substring_false_positive(self):
        self.assertEqual(self.classify(None, ['cat', 'pytest-results.json'], '2', 4), 'build')


class PreemptionLifecycleTests(unittest.TestCase):
    def exercise(self, jobs, *, checkpoint=True, interrupt_after=None, clock=(0,),
                 job_class='bench', workloads=(), pods=()):
        """Drive the real submitter with only external transports replaced."""
        namespace = runpy.run_path(str(pathlib.Path(__file__).parents[1] / 'scripts/fleet-kueue'))
        main = namespace['main']
        requests = []
        self.last_requests = requests
        states = iter(jobs)
        workload_states = iter(workloads)
        pod_states = iter(pods)
        if workloads:
            for job in jobs:
                job['spec'].setdefault('template', {}).setdefault('metadata', {})['annotations'] = {
                    'kueue.x-k8s.io/workload': 'owned-workload'}
        self.manifests = []
        sleeps = 0

        def checked(argv, **kwargs):
            requests.append(argv)
            if 'get' in argv and 'clusterqueue' in argv:
                value = {'spec': {'resourceGroups': [{'flavors': [{
                    'name': 'node-mbp', 'resources': [
                        {'name': 'cpu', 'nominalQuota': '4'},
                        {'name': 'memory', 'nominalQuota': '10441814016'}]}]}]}}
            elif 'get' in argv and 'job' in argv:
                value = next(states)
            elif 'get' in argv and 'workload' in argv:
                value = next(workload_states)
            elif 'get' in argv and 'pods' in argv:
                value = {'items': next(pod_states, [])}
            elif 'create' in argv:
                self.manifests.append(json.loads(kwargs['input']))
                return SimpleNamespace(stdout='')
            elif 'id -u' in argv[-1]:
                return SimpleNamespace(stdout='/home/agentjob\n1001\n1001\n')
            else:
                return SimpleNamespace(stdout='')
            return SimpleNamespace(stdout=json.dumps(value))

        def sleep(seconds):
            nonlocal sleeps
            sleeps += 1
            if sleeps == interrupt_after:
                raise KeyboardInterrupt

        monotonic = mock.Mock(side_effect=clock)
        fleet = {'registry': lambda: (None, {'mbp': {'ssh_user': 'agentjob'}}),
                 'ssh_cmd': lambda node: ['ssh', 'mbp']}
        stderr = io.StringIO()
        self.last_stderr = stderr
        with tempfile.TemporaryDirectory() as state:
            argv = ['fleet-kueue', '--src', state, '--no-src', '--keep',
                    '--priority-class', job_class, '--cpus', '4', '--wait', '2']
            if checkpoint:
                argv += ['--checkpoint-safe']
            argv += ['--', 'python3', 'benchmark.py']
            process = SimpleNamespace(stdout=io.BytesIO(), returncode=0,
                                      wait=mock.Mock(return_value=0), terminate=mock.Mock(),
                                      poll=mock.Mock(return_value=0))
            replacements = {
                'checked': checked,
                'runpy': SimpleNamespace(run_path=lambda path: fleet),
                'time': SimpleNamespace(monotonic=monotonic, sleep=sleep),
                'signal': SimpleNamespace(SIGTERM=15, signal=lambda *args: None),
                'subprocess': SimpleNamespace(Popen=lambda *args, **kwargs: process,
                                              PIPE=-1, STDOUT=-2,
                                              TimeoutExpired=TimeoutError),
            }
            with mock.patch.dict(main.__globals__, replacements), \
                    mock.patch.dict(os.environ, {'FLEET_STATE': state}), \
                    mock.patch('sys.argv', argv), contextlib.redirect_stderr(stderr):
                result = main()
            receipts = [json.loads(path.read_text()) for path in pathlib.Path(state, 'runs').glob('*.json')]
        return result, requests, stderr.getvalue(), receipts, monotonic

    def test_deadline_only_limits_initial_admission(self):
        # Even a clock far past --wait cannot expire an already-admitted job
        # when Kueue subsequently evicts it. No new clock read is permitted.
        failed = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Failed', 'status': 'True', 'reason': 'DeadlineExceeded'}]}}
        result, _, _, _, clock = self.exercise([
            {'spec': {'suspend': True}},
            {'spec': {'suspend': False}},
            {'spec': {'suspend': True}},
            failed,
        ], clock=(0, 1))
        self.assertEqual(result, 124)
        self.assertEqual(clock.call_count, 2)

    def test_initial_admission_can_still_expire(self):
        result, _, stderr, _, clock = self.exercise(
            [{'spec': {'suspend': True}}], clock=(0, 3))
        self.assertEqual(result, 75)
        self.assertIn('admission wait expired', stderr)
        self.assertEqual(clock.call_count, 2)

    def test_preempted_checkpoint_survives_client_exit(self):
        result, requests, stderr, receipts, clock = self.exercise([
            {'spec': {'suspend': False}},
            {'spec': {'suspend': True}},
        ], interrupt_after=2, workloads=[
            {'status': {'admission': {'clusterQueue': 'bench-lanes'}}},
            {'status': {'conditions': [{'type': 'Evicted', 'status': 'True'}]}},
        ])
        self.assertEqual(result, 130)
        self.assertEqual(clock.call_count, 1)
        self.assertEqual(len(receipts), 1)
        self.assertTrue(receipts[0]['checkpoint_safe'])
        self.assertIn('retained checkpoint stage ' + receipts[0]['stage'], stderr)
        self.assertIn('receipt ', stderr)
        self.assertIn(receipts[0]['job_id'] + '.json', stderr)
        self.assertFalse(any('rm -rf' in str(argv) for argv in requests))
        self.assertFalse(any('delete' in argv and 'job' in argv for argv in requests))

    def test_unsafe_bench_is_rejected_before_job_creation(self):
        with self.assertRaises(SystemExit) as error:
            self.exercise([], checkpoint=False)
        self.assertEqual(error.exception.code, 2)
        self.assertIn('bench requires --checkpoint-safe', self.last_stderr.getvalue())
        self.assertFalse(any('create' in argv for argv in self.last_requests))

    def test_eviction_wins_over_stale_failed_job_condition(self):
        stale_failed = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Failed', 'status': 'True', 'reason': 'BackoffLimitExceeded'}]}}
        complete = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Complete', 'status': 'True'}]}}
        result, requests, _, receipts, _ = self.exercise([
            {'spec': {'suspend': False}}, stale_failed, complete,
        ], workloads=[
            {'status': {'admission': {'clusterQueue': 'bench-lanes'}}},
            {'status': {'conditions': [{'type': 'Evicted', 'status': 'True'},
                                       {'type': 'Requeued', 'status': 'True'}]}},
            {'status': {'admission': {'clusterQueue': 'bench-lanes'},
                        'conditions': [{'type': 'Evicted', 'status': 'False'},
                                       {'type': 'Requeued', 'status': 'True'},
                                       {'type': 'Finished', 'status': 'True'}]}},
        ])
        self.assertEqual(result, 0)
        self.assertEqual(receipts[0]['queue'], 'bench-lanes')
        self.assertFalse(any('delete' in argv for argv in requests))

    def test_exit_137_without_job_terminal_condition_waits_for_controller(self):
        terminated = {'metadata': {'name': 'owned-pod'}, 'status': {
            'phase': 'Failed', 'containerStatuses': [
                {'state': {'terminated': {'exitCode': 137}}}]}}
        complete = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Complete', 'status': 'True'}]}}
        result, _, _, _, _ = self.exercise([
            {'spec': {'suspend': False}}, complete,
        ], pods=[[terminated], []])
        self.assertEqual(result, 0)

    def test_unsafe_build_remains_in_protected_queue(self):
        complete = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Complete', 'status': 'True'}]}}
        result, _, _, receipts, _ = self.exercise([complete], checkpoint=False, job_class='build')
        self.assertEqual(result, 0)
        self.assertEqual(receipts[0]['queue'], 'lanes')
        self.assertEqual(self.manifests[0]['metadata']['labels']['kueue.x-k8s.io/queue-name'], 'lanes')

    def test_checkpoint_safe_bench_uses_borrowing_queue(self):
        complete = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Complete', 'status': 'True'}]}}
        self.exercise([complete])
        self.assertEqual(self.manifests[0]['metadata']['labels']['kueue.x-k8s.io/queue-name'], 'bench-lanes')

    def test_legacy_unsafe_build_eviction_preserves_job_and_stage(self):
        result, requests, stderr, _, _ = self.exercise([
            {'spec': {'suspend': False}}, {'spec': {'suspend': False}},
        ], checkpoint=False, job_class='build', interrupt_after=2, workloads=[
            {'status': {'admission': {'clusterQueue': 'lanes'}}},
            {'status': {'conditions': [{'type': 'Evicted', 'status': 'True'}]}},
        ])
        self.assertEqual(result, 130)
        self.assertIn('retained checkpoint stage', stderr)
        self.assertFalse(any('delete' in argv or 'rm -rf' in str(argv) for argv in requests))

    def test_stale_job_failure_after_readmission_is_not_terminal(self):
        failed = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Failed', 'status': 'True', 'reason': 'BackoffLimitExceeded'}]}}
        complete = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Complete', 'status': 'True'}]}}
        result, _, _, _, _ = self.exercise([failed, complete], workloads=[
            {'status': {'admission': {'clusterQueue': 'bench-lanes'},
                        'conditions': [{'type': 'Requeued', 'status': 'True'}]}},
            {'status': {'conditions': [{'type': 'Finished', 'status': 'True'}]}},
        ])
        self.assertEqual(result, 0)


class ProtectedCohortPolicyTests(unittest.TestCase):
    def test_only_zero_quota_benchmarks_are_reclaimable(self):
        manifest = (pathlib.Path(__file__).parents[1] / 'config/k3s/kueue/queues.yaml').read_text()
        documents = manifest.split('---')
        queues = {name: next(document for document in documents
                             if 'kind: ClusterQueue' in document and f'  name: {name}' in document.splitlines())
                  for name in ('lanes', 'bench-lanes')}
        self.assertIn('cohortName: mbp-lanes', queues['lanes'])
        self.assertIn('cohortName: mbp-lanes', queues['bench-lanes'])
        self.assertIn('withinClusterQueue: Never', queues['lanes'])
        self.assertIn('reclaimWithinCohort: Any', queues['lanes'])
        self.assertIn('withinClusterQueue: Never', queues['bench-lanes'])
        self.assertIn('reclaimWithinCohort: Never', queues['bench-lanes'])
        self.assertIn('cpu, nominalQuota: "0", borrowingLimit: "4"', queues['bench-lanes'])
        self.assertIn('memory, nominalQuota: "0", borrowingLimit: "10441814016"', queues['bench-lanes'])
        self.assertNotIn('LowerPriority', queues['lanes'])
