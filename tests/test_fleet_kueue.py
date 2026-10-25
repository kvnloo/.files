import contextlib
import io
import json
import os
import pathlib
import runpy
import subprocess
import tarfile
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
                 job_class='bench', workloads=(), pods=(), detach_signal=None, attach=False, host=False):
        """Drive the real submitter with only external transports replaced."""
        namespace = runpy.run_path(str(pathlib.Path(__file__).parents[1] / 'scripts/fleet-kueue'))
        main = namespace['main']
        requests = []
        self.last_requests = requests
        states = iter(jobs)
        workload_states = iter(workloads)
        pod_states = iter(pods)
        handlers = {}
        attached_id = 'fleet-mbp-0123456789abcdef'
        first_attach_read = attach
        existing = {'metadata': {'name': attached_id, 'labels': {
            'app.kubernetes.io/managed-by': 'fleet-build',
            'kueue.x-k8s.io/priority-class': job_class}}, 'spec': {'template': {'spec': {
                'containers': [{'command': ['python3', 'benchmark.py'],
                                'resources': {'requests': {'cpu': '4', 'memory': '134217728'}}}]}}}}
        if workloads:
            for job in jobs:
                job['spec'].setdefault('template', {}).setdefault('metadata', {})['annotations'] = {
                    'kueue.x-k8s.io/workload': 'owned-workload'}
        self.manifests = []
        sleeps = 0

        def checked(argv, **kwargs):
            nonlocal first_attach_read
            requests.append(argv)
            if 'get' in argv and 'clusterqueue' in argv:
                value = {'spec': {'resourceGroups': [{'flavors': [{
                    'name': 'node-mbp', 'resources': [
                        {'name': 'cpu', 'nominalQuota': '4'},
                        {'name': 'memory', 'nominalQuota': '10441814016'}]}]}]}}
            elif 'get' in argv and 'job' in argv:
                if first_attach_read:
                    first_attach_read = False
                    value = existing
                else:
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
            elif '-p ActiveState -p ExecMainStatus' in argv[-1]:
                return SimpleNamespace(stdout='ActiveState=active\nExecMainStatus=0\n')
            else:
                return SimpleNamespace(stdout='')
            return SimpleNamespace(stdout=json.dumps(value))

        def sleep(seconds):
            nonlocal sleeps
            sleeps += 1
            if sleeps == interrupt_after:
                if detach_signal is not None:
                    handlers[detach_signal](detach_signal, None)
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
            if host:
                argv.insert(1, '--host')
            if attach:
                argv = ['fleet-kueue', '--attach', attached_id, '--keep', '--wait', '2']
                run_dir = pathlib.Path(state, 'runs')
                run_dir.mkdir()
                (run_dir / f'{attached_id}.json').write_text(json.dumps({
                    'checkpoint_safe': checkpoint, 'host': host, 'class': job_class,
                    'command': ['python3', 'benchmark.py'], 'timeout': 60, 'keep': True,
                    'job_id': attached_id, 'queue': 'bench-lanes' if job_class == 'bench' else 'lanes',
                }))
                (run_dir / f'{attached_id}-mbp.log').write_text('ORIGINAL_LOG\n')
            process = SimpleNamespace(stdout=io.BytesIO(), returncode=0,
                                      wait=mock.Mock(return_value=0), terminate=mock.Mock(),
                                      poll=mock.Mock(return_value=0))
            replacements = {
                'checked': checked,
                'runpy': SimpleNamespace(run_path=lambda path: fleet),
                'time': SimpleNamespace(monotonic=monotonic, sleep=sleep),
                'signal': SimpleNamespace(SIGTERM=15, SIGHUP=1,
                                          signal=lambda signum, fn: handlers.__setitem__(signum, fn)),
                'subprocess': SimpleNamespace(Popen=lambda *args, **kwargs: process,
                                              PIPE=-1, STDOUT=-2,
                                              TimeoutExpired=TimeoutError),
            }
            with mock.patch.dict(main.__globals__, replacements), \
                    mock.patch.dict(os.environ, {'FLEET_STATE': state}), \
                    mock.patch('sys.argv', argv), contextlib.redirect_stderr(stderr):
                result = main()
            receipts = [json.loads(path.read_text()) for path in pathlib.Path(state, 'runs').glob('*.json')]
            self.logs = [path.read_text() for path in pathlib.Path(state, 'runs').glob('*-mbp.log')]
        return result, requests, stderr.getvalue(), receipts, monotonic

    def test_sigterm_detaches_without_cancelling_unsafe_build(self):
        result, requests, stderr, receipts, _ = self.exercise(
            [{'spec': {'suspend': False}}], checkpoint=False, job_class='build',
            interrupt_after=1, detach_signal=15)
        self.assertEqual(result, 143)
        self.assertIn('detached job ' + receipts[0]['job_id'], stderr)
        self.assertIn('fleet-build --attach ' + receipts[0]['job_id'], stderr)
        self.assertFalse(any('delete' in argv or 'rm -rf' in str(argv) for argv in requests))

    def test_sighup_detaches_without_deleting_pending_job(self):
        result, requests, _, _, _ = self.exercise(
            [{'spec': {'suspend': True}}], interrupt_after=1, detach_signal=1, clock=(0, 1))
        self.assertEqual(result, 129)
        self.assertFalse(any('delete' in argv or 'rm -rf' in str(argv) for argv in requests))

    def test_attach_observes_existing_job_without_replaying_submission(self):
        complete = {'spec': {'suspend': False}, 'status': {'conditions': [
            {'type': 'Complete', 'status': 'True'}]}}
        result, requests, stderr, _, _ = self.exercise(
            [{'spec': {'suspend': False}}, complete], attach=True)
        self.assertEqual(result, 0)
        self.assertIn('attached fleet-mbp-0123456789abcdef', stderr)
        self.assertFalse(any('create' in argv or 'mkdir -p' in str(argv) or 'tar ' in str(argv)
                             for argv in requests))
        self.assertIn('ORIGINAL_LOG', self.logs[0])

    def test_host_service_survives_observer_sigterm(self):
        running = {'metadata': {'name': 'owned-host-reservation'}, 'status': {
            'containerStatuses': [{'state': {'running': {}}}]}}
        result, requests, _, _, _ = self.exercise(
            [{'spec': {'suspend': False}}], checkpoint=False, host=True, job_class='build',
            pods=[[running]], interrupt_after=1, detach_signal=15)
        self.assertEqual(result, 143)
        launch = next(str(argv) for argv in requests if 'systemd-run --user --quiet' in str(argv))
        self.assertIn('.service', launch)
        self.assertNotIn('--scope', launch)
        self.assertIn('host.exit', launch)
        self.assertFalse(any('delete' in argv or 'systemctl --user stop' in str(argv) for argv in requests))

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
        import yaml
        manifest = pathlib.Path(__file__).parents[1] / 'config/k3s/kueue/queues.yaml'
        queues = {document['metadata']['name']: document['spec']
                  for document in yaml.safe_load_all(manifest.read_text())
                  if document and document['kind'] == 'ClusterQueue'}
        for name in ('lanes', 'bench-lanes'):
            self.assertEqual(queues[name]['cohortName'], 'mbp-lanes')
            self.assertEqual(queues[name]['preemption']['withinClusterQueue'], 'Never')
        self.assertEqual(queues['lanes']['preemption']['reclaimWithinCohort'], 'Any')
        self.assertEqual(queues['bench-lanes']['preemption']['reclaimWithinCohort'], 'Never')
        resources = queues['bench-lanes']['resourceGroups'][0]['flavors'][0]['resources']
        self.assertEqual({r['name']: (r['nominalQuota'], r['borrowingLimit']) for r in resources},
                         {'cpu': ('0', '4'), 'memory': ('0', '10441814016')})


class AttachWrapperTests(unittest.TestCase):
    def test_fleet_build_attach_dispatches_without_command_or_source(self):
        script = pathlib.Path(__file__).parents[1] / 'scripts/fleet-build'
        with tempfile.TemporaryDirectory() as directory:
            python = pathlib.Path(directory, 'python3')
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            environment = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['bash', str(script), '--attach', 'fleet-mbp-0123456789abcdef'],
                                    env=environment, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--attach\nfleet-mbp-0123456789abcdef\n', result.stdout)
            self.assertIn('/fleet-kueue\n', result.stdout)
            self.assertNotIn('--src', result.stdout)

    def test_attach_rejects_replaying_a_command(self):
        script = pathlib.Path(__file__).parents[1] / 'scripts/fleet-build'
        result = subprocess.run(['bash', str(script), '--attach', 'fleet-mbp-0123456789abcdef',
                                 '--', 'python3', 'benchmark.py'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('submission options/commands are not allowed', result.stderr)


class BendToolsWrapperTests(unittest.TestCase):
    def test_bend_snapshot_excludes_check_json_and_exports_executable(self):
        script = pathlib.Path(__file__).parents[1] / 'scripts/fleet-build'
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for part in ('bin', 'bend2', 'bendtt'):
                (root / '.bend' / part).mkdir(parents=True)
                (root / '.bend' / part / 'check.json').write_text('NEVER_SHIP')
            bend = root / '.bend/bin/bend'
            bend.write_text('#!/bin/sh\nexit 0\n')
            bend.chmod(0o755)
            (root / '.bend/bend2/base.bend').write_text('base')
            (root / '.bend/bendtt/proof.stub').write_text('proof')
            (root / '.bend/check.json').write_text('NEVER_SHIP')
            tools = root / 'fake-bin'
            tools.mkdir()
            python = tools / 'python3'
            python.write_text(
                '#!/bin/sh\ncopy=0\nfor arg; do\n'
                '  if [ "$copy" = 1 ]; then cp "${arg%:*}" "$BEND_CAPTURE"; copy=0; fi\n'
                '  if [ "$arg" = --input ]; then copy=1; fi\n'
                'done\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            captured = root / 'captured.tar.gz'
            environment = dict(os.environ, HOME=directory, BEND_CAPTURE=str(captured),
                               PATH=str(tools) + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['bash', str(script), '--node', 'mbp', '--src', directory,
                                     '--bend-tools', '--', 'python3', '-m', 'pytest'],
                                    env=environment, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with tarfile.open(captured) as archive:
                names = archive.getnames()
                self.assertIn('bin/bend', names)
                self.assertIn('bend2/base.bend', names)
                self.assertIn('bendtt/proof.stub', names)
                self.assertFalse(any(pathlib.PurePosixPath(name).name == 'check.json' for name in names))
            self.assertIn('FLEET_BUILD_BEND_TOOLS=1', result.stdout)
            self.assertIn('export BEND="$HOME/.bend/bin/bend"', result.stdout)
            self.assertIn('export PATH="$HOME/.bend/bin:$PATH"', result.stdout)
            arguments = result.stdout.splitlines()
            package = pathlib.Path(arguments[arguments.index('--input') + 1].rsplit(':', 1)[0])
            self.assertFalse(package.parent.exists())
