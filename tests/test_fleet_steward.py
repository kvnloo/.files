"""Offline steward regressions: synthetic logs only, no builds or SSH execution."""
import contextlib
import fcntl
import importlib.machinery
import io
import json
import os
from pathlib import Path
import pwd
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
steward = importlib.machinery.SourceFileLoader('fleet_steward_tested', str(ROOT / 'scripts/fleet-steward')).load_module()


class Steward(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        (self.state / 'runs').mkdir()
        (self.state / 'health').mkdir()
        self.registry = {'defaults': {'health': {'min_mem_available_mb': 1024, 'min_disk_free_gb': 15}},
                         'nodes': {'mbp': {'tailnet_ip': '100.78.215.21', 'ssh_port': 2222}}}
        self.errors = []

    def job(self, job='job-a', node='mbp', command='bun test', code=0, metadata=None, body='', filename=None):
        path = self.state / 'runs' / (filename or f'{job}-{node}.log')
        text = f'# fleet job {job} node={node} cmd={command}\n'
        if metadata is not None:
            text += '# steward ' + json.dumps(metadata) + '\n'
        text += body
        if code is not None:
            text += f'# exit {code}\n'
        path.write_text(text)
        return path

    def health(self, samples):
        (self.state / 'health/history.jsonl').write_text(''.join(json.dumps(s) + '\n' for s in samples))

    def row(self, **kwargs):
        return steward.parse_log(self.job(**kwargs), self.errors)

    def test_historical_unknowns_are_not_mtime_durations(self):
        path = self.job(job='20261022-120000-abcd', code=137)
        os.utime(path, (999999999, 999999999))
        row = steward.parse_log(path, self.errors)
        self.assertIsNone(row['runtime_s'])
        self.assertIsNone(row['queue_wait_s'])
        self.assertIsNone(row['peak_memory_bytes'])
        self.assertIsNone(row['started_ts'])
        self.assertEqual(row['provenance']['id_ts']['status'], 'derived_id_local_timezone')
        self.assertEqual(row['provenance']['runtime_s']['status'], 'unknown')

    def test_metadata_timestamps_and_peak_marker_survive_null_trailer(self):
        meta = {'repo': 'kvnloo/sample', 'queued_ts': 100, 'started_ts': 110,
                'finished_ts': 140, 'attempt_id': 'batch-a', 'memory_limit_mb': 512,
                'runtime_scope': 'remote_ssh_execution', 'queue_wait_scope': 'admission_probe_source_staging'}
        row = self.row(metadata=meta, body='# fleet_peak_memory_bytes 12345\n# steward {"peak_memory_bytes":null,"runtime_s":null}\n')
        self.assertEqual(row['runtime_s'], 30)
        self.assertEqual(row['queue_wait_s'], 10)
        self.assertEqual(row['peak_memory_bytes'], 12345)
        self.assertEqual(row['repo'], 'kvnloo/sample')
        self.assertEqual(row['runtime_scope'], 'remote_ssh_execution')
        self.assertEqual(row['queue_wait_scope'], 'admission_probe_source_staging')
        self.assertEqual(row['provenance']['runtime_scope']['status'], 'observed')
        self.assertEqual(row['provenance']['queue_wait_s']['status'], 'derived_explicit_timestamps')
        self.assertEqual(row['sources'][0]['sha256'], steward.hashlib.sha256((self.state / 'runs/job-a-mbp.log').read_bytes()).hexdigest())

    def test_nearest_prior_health_not_future_or_stale(self):
        self.job(metadata={'started_ts': 1000})
        self.health([{'node': 'mbp', 'ts': 699, 'probe': {'max_temp_c': 40}},
                     {'node': 'mbp', 'ts': 900, 'probe': {'max_temp_c': 70, 'mem_available_mb': 4000}},
                     {'node': 'mbp', 'ts': 1001, 'probe': {'max_temp_c': 99}}])
        row = steward.ledger(self.state, self.errors)[0]
        self.assertEqual(row['probe_temp_c'], 70)
        self.assertEqual(row['probe_mem_available_mb'], 4000)
        self.assertEqual(row['provenance']['health']['age_s'], 100)
        self.health([{'node': 'mbp', 'ts': 699, 'probe': {'max_temp_c': 40}}, {'node': 'mbp', 'ts': 1001}])
        self.assertIsNone(steward.ledger(self.state, self.errors)[0]['health'])

    def test_health_boundary_and_launch_probe_precedence(self):
        self.job(metadata={'queued_ts': 1000, 'probe': {'max_temp_c': 80}})
        self.health([{'node': 'mbp', 'ts': 700, 'probe': {'max_temp_c': 40}, 'k8s': {'conditions': {'DiskPressure': 'True'}}}])
        row = steward.ledger(self.state, self.errors)[0]
        self.assertEqual(row['probe_temp_c'], 80)
        self.assertEqual(row['k8s']['conditions']['DiskPressure'], 'True')
        self.assertEqual(row['provenance']['health']['age_s'], 300)

    def test_full_snapshot_wins_over_legacy_history(self):
        self.job(metadata={'started_ts': 1000})
        self.health([{'node': 'mbp', 'ts': 950, 'healthy': True}])
        (self.state / 'health/mbp.json').write_text(json.dumps({'node': 'mbp', 'ts': 950, 'healthy': True, 'probe': {'max_temp_c': 55}}))
        self.assertEqual(steward.ledger(self.state, self.errors)[0]['probe_temp_c'], 55)

    def test_missing_health_not_fabricated_from_state_counter(self):
        self.job(metadata={'started_ts': 1000})
        (self.state / 'health/state.json').write_text('{"mbp":{"bad":4,"paused":true}}')
        row = steward.ledger(self.state, self.errors)[0]
        self.assertIsNone(row['health'])
        self.assertIsNone(row['k8s'])

    def test_all_logs_and_duplicate_job_are_one_row(self):
        self.job(job='same', metadata={'started_ts': 100})
        self.job(job='same', filename='duplicate.log', metadata={'finished_ts': 130})
        (self.state / 'runs/no-header.log').write_text('incomplete output\n')
        rows = steward.ledger(self.state, self.errors)
        self.assertEqual(len(rows), 2)
        duplicate = next(r for r in rows if r['job_id'] == 'same')
        self.assertEqual(len(duplicate['sources']), 2)
        self.assertEqual(duplicate['runtime_s'], 30)
        self.assertIn('duplicate job_id merged', '\n'.join(self.errors))

    def test_repo_class_and_untrusted_command_are_data(self):
        for command, cls in [('cd /work/project && bun test', 'bun'), ('pnpm test', 'pnpm'),
                             ('python -m pytest -q', 'pytest'), ('./gradlew assembleDebug', 'gradle'), ('echo hello', 'other')]:
            row = self.row(command=command)
            self.assertEqual(row['cmd_class'], cls)
        self.assertEqual(steward.command_repo('git clone git@github.com:kvnloo/example.git'), 'kvnloo/example')
        self.assertEqual(steward.command_repo('cd /work/project && bun test'), '/work/project')
        with patch.object(steward.subprocess, 'run', side_effect=AssertionError('log executed')):
            self.row(command='$(touch /tmp/never) && echo hostile', body='# steward {bad json}\n', code=None)
        self.assertTrue(self.errors)

    def test_malformed_metadata_and_nonfinite_values_remain_unknown(self):
        row = self.row(metadata={'runtime_s': -3, 'queue_wait_s': float('nan'), 'node': [], 'probe': 'bad', 'exit': True})
        self.assertIsNone(row['runtime_s'])
        self.assertIsNone(row['queue_wait_s'])
        self.assertIsNone(row['node'])
        self.assertIsNone(row['probe'])
        self.assertIsNone(row['exit'])

    def test_repeated_127_grouped_by_node_and_observed_tool(self):
        rows = [self.row(job=f'a{i}', code=127, command=command, body='bash: line 1: pnpm: command not found\n')
                for i, command in enumerate(('bash check.sh', 'bun run check'))]
        rows.append(self.row(job='b', node='phone', code=127, command='bash check.sh', body='bash: bun: command not found\n'))
        findings, _ = steward.analyze(rows, self.registry)
        tools = [f for f in findings if f['kind'] == 'toolchain']
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['sample_ids'], ['a0', 'a1'])
        self.assertIn('mbp/pnpm', tools[0]['claim'])

    def test_137_never_asserts_oom_or_production_floor_for_synthetic_probe(self):
        row = self.row(command='python3 -c "a=bytearray(1500*1024*1024)"', code=137)
        findings, _ = steward.analyze([row], self.registry)
        finding = next(f for f in findings if f['kind'] == 'memory_floor')
        self.assertTrue(finding['details']['synthetic_probe_only'])
        self.assertIsNone(finding['details']['recommended_change'])
        self.assertIn('no production memory floor', finding['claim'])
        normal = self.row(command='pnpm test', code=137)
        findings, _ = steward.analyze([normal], self.registry)
        self.assertIn('not definite OOM', findings[0]['claim'])

    def test_source_integrity_detection_requires_native_error_evidence(self):
        row = self.row(job='archive-error', body='tar: src/moving.ts: Cannot stat: No such file or directory\n')
        findings, _ = steward.analyze([row], self.registry)
        finding = next(f for f in findings if f['kind'] == 'source_integrity')
        self.assertEqual(finding['sample_ids'], ['archive-error'])
        self.assertIn('Cannot stat', finding['details']['errors'][0]['observation'])
        clean = self.row(job='20261022-224002-24a1')
        findings, _ = steward.analyze([clean], self.registry)
        self.assertFalse(any(f['kind'] == 'source_integrity' for f in findings))

    def test_multiline_quoted_header_reconstructed_before_metadata(self):
        for tool in ('bun', 'pnpm', 'pytest'):
            command = steward.shlex.join(['bash', '-lc', 'set -eu\n# exit 127\nexec \"$@\"\n', 'fleet-build', '.', tool, 'test'])
            row = self.row(command=command, metadata={'repo': 'kvnloo/example', 'queued_ts': 100,
                                                      'started_ts': 110, 'finished_ts': 130},
                           body='# fleet_peak_memory_bytes 1234\n')
            self.assertEqual(row['command'], command)
            self.assertEqual(row['cmd_class'], tool)
            self.assertEqual(row['repo'], 'kvnloo/example')
            self.assertEqual(row['exit'], 0)
            self.assertEqual(row['runtime_s'], 20)
            self.assertEqual(row['peak_memory_bytes'], 1234)

    def test_unfinished_header_and_oversize_continuation_are_bounded_diagnostics(self):
        path = self.job(command="bash -lc 'unfinished", code=None)
        row = steward.parse_log(path, self.errors)
        self.assertEqual(row['provenance']['command']['status'], 'incomplete_header')
        self.assertTrue(any('unfinished command header quote' in e for e in self.errors))
        path = self.job(command="bash -lc 'unfinished", body='x' * (1024 * 1024) + '\n', code=None)
        row = steward.parse_log(path, self.errors)
        self.assertLess(len(row['command']), 1024 * 1024)
        self.assertTrue(any('exceeds 1MiB' in e for e in self.errors))

    def test_75_unknown_reason_burst_including_equal_timestamps(self):
        rows = [self.row(job=f'hold{i}', code=75, metadata={'queued_ts': 100}) for i in range(2)]
        findings, _ = steward.analyze(rows, self.registry)
        burst = next(f for f in findings if f['kind'] == 'gate_burst')
        self.assertIn('unknown', burst['claim'])
        self.assertEqual(burst['sample_count'], 2)
        rows[1]['queued_ts'] = 2000
        findings, _ = steward.analyze(rows, self.registry)
        self.assertFalse(any(f['kind'] == 'gate_burst' for f in findings))

    def test_queue_contention_requires_measured_wait_or_explicit_lane_hold(self):
        unrelated = self.row(job='unknown', metadata={'queued_ts': 100}, code=75)
        findings, _ = steward.analyze([unrelated], self.registry)
        self.assertFalse(any(f['kind'] == 'queue_contention' for f in findings))
        held = self.row(job='lane', code=75, body='fleet: lane has 200MiB left for a 500MiB job (other jobs running)\n')
        findings, _ = steward.analyze([held], self.registry)
        self.assertTrue(any(f['kind'] == 'queue_contention' for f in findings))

    def test_pressure_joins_prior_events_only_and_preserves_headroom(self):
        self.job(metadata={'started_ts': 1000})
        self.health([{'node': 'mbp', 'ts': 990, 'probe': {'mem_available_mb': 5000, 'disk_lane': {'free_gb': 40}},
                      'k8s': {'conditions': {'DiskPressure': 'True'}}}])
        events = {'observed_ts': 995, 'events': [{'node': 'mbp', 'reason': 'Evicted', 'lastTimestamp': 990},
                                              {'node': 'mbp', 'reason': 'Future', 'lastTimestamp': 1001}]}
        (self.state / 'health/k8s-events.json').write_text(json.dumps(events))
        rows = steward.ledger(self.state, self.errors)
        self.assertEqual(len(rows[0]['events']), 1)
        findings, _ = steward.analyze(rows, self.registry)
        details = next(f for f in findings if f['kind'] == 'pressure_headroom')['details']['samples'][0]
        self.assertTrue(details['memory_above_health_floor'])
        self.assertTrue(details['all_observed_disks_above_health_floor'])
        events['observed_ts'] = 1001
        (self.state / 'health/k8s-events.json').write_text(json.dumps(events))
        self.assertEqual(steward.ledger(self.state, self.errors)[0]['events'], [])

    def test_legacy_health_reason_retains_pressure_without_k8s_snapshot(self):
        self.job(metadata={'started_ts': 1000})
        self.health([{'node': 'mbp', 'ts': 990, 'healthy': False, 'reasons': ['k8s DiskPressure']}])
        rows = steward.ledger(self.state, self.errors)
        self.assertIsNone(rows[0]['k8s'])
        findings, _ = steward.analyze(rows, self.registry)
        pressure = next(f for f in findings if f['kind'] == 'pressure_headroom')
        sample = pressure['details']['samples'][0]
        self.assertEqual(sample['conditions'], ['DiskPressure'])
        self.assertEqual(sample['legacy_health_reason_conditions'], ['DiskPressure'])
        self.assertEqual(sample['condition_provenance']['status'], 'observed_prior')
        self.assertIsNone(sample['all_observed_disks_above_health_floor'])

    def test_learned_parameters_exclude_synthetic_peaks_and_carry_tool_evidence(self):
        synthetic = self.row(job='synthetic', command='python3 -c "bytearray(100)"',
                             metadata={'repo': 'kvnloo/example', 'peak_memory_bytes': 99 * 2**20})
        successful = self.row(job='production', command='pnpm test',
                              metadata={'repo': 'kvnloo/example', 'peak_memory_bytes': 3 * 2**20 + 1, 'runtime_s': 20})
        missing = self.row(job='missing', command='bun run check', code=127,
                           metadata={'repo': 'kvnloo/example'}, body='bash: cargo: command not found\n')
        _, parameters = steward.analyze([synthetic, successful, missing], self.registry)
        learned = parameters['per_repo_node'][0]['learned_parameters']
        self.assertEqual(learned['memory_floor_mb'], 4)
        self.assertEqual(learned['memory_floor_sample_ids'], ['production'])
        self.assertEqual(learned['typical_successful_runtime_s'], 20)
        self.assertEqual(learned['successful_runtime_coverage'], 0.5)
        tools = {tool['tool']: tool for tool in learned['required_toolchains']}
        self.assertEqual(tools['cargo']['sample_ids'], ['missing'])
        self.assertEqual(tools['cargo']['evidence'][0]['status'], 'observed_missing')
        self.assertEqual(tools['pnpm']['installation_status'], 'unknown')
        self.assertIsNone(steward.learned_parameters([synthetic])['memory_floor_mb'])

    def test_exit_buckets_include_missing_exit_coverage(self):
        rows = [self.row(job='success'), self.row(job='held', code=75),
                self.row(job='failed', code=127), self.row(job='partial', code=None)]
        metrics = steward.baseline(rows)
        self.assertEqual(metrics['exit_counts'], {'0': 1, '75': 1, '127': 1})
        self.assertEqual(metrics['missing_exit_jobs'], 1)
        self.assertEqual(sum(metrics['exit_counts'].values()) + metrics['missing_exit_jobs'], metrics['jobs'])

    def test_thermal_match_requires_repo_class_node_and_three_per_cohort(self):
        rows = []
        for i, (temp, duration) in enumerate([(40, 10), (41, 11), (42, 12), (80, 25), (81, 26), (82, 27)]):
            row = self.row(job=f't{i}', metadata={'repo': 'kvnloo/example', 'runtime_s': duration, 'probe': {'max_temp_c': temp}})
            steward.attach_health(row, {}, [])
            rows.append(row)
        findings, _ = steward.analyze(rows, self.registry)
        self.assertTrue(any(f['kind'] == 'thermal_runtime' for f in findings))
        findings, _ = steward.analyze(rows[:-1], self.registry)
        self.assertFalse(any(f['kind'] == 'thermal_runtime' for f in findings))
        rows[-1]['node'] = 'phone'
        findings, _ = steward.analyze(rows, self.registry)
        self.assertFalse(any(f['kind'] == 'thermal_runtime' for f in findings))

    def test_attempt_metrics_known_groups_and_coverage_not_adjacency(self):
        rows = [self.row(job='a', code=75, metadata={'repo': 'kvnloo/example', 'attempt_id': 'one', 'queued_ts': 100}),
                self.row(job='b', metadata={'repo': 'kvnloo/example', 'attempt_id': 'one', 'queued_ts': 100, 'started_ts': 120, 'finished_ts': 150}),
                self.row(job='c', metadata={'attempt_id': 'unresolved', 'queued_ts': 200}, code=1),
                self.row(job='d', metadata={'queued_ts': 210})]
        metrics = steward.baseline(rows)
        self.assertEqual(metrics['retry_attempts'], 1)
        self.assertAlmostEqual(metrics['retry_rate'], 1 / 3)
        self.assertEqual(metrics['median_time_to_green_s'], 50)
        self.assertEqual(metrics['time_to_green_group_coverage'], 0.5)
        self.assertEqual(metrics['attempt_id_coverage'], 0.75)
        self.assertEqual(metrics['median_queue_wait_s'], 20)
        self.assertEqual(metrics['queue_wait_coverage'], 0.25)
        self.assertIsNone(steward.baseline([rows[-1]])['retry_rate'])

    def test_lessons_full_z0learn_envelope_and_source_hash(self):
        rows = [self.row(job=f'a{i}', code=127, metadata={'repo': 'kvnloo/example'}) for i in range(2)]
        findings, _ = steward.analyze(rows, self.registry)
        lessons = steward.lesson_envelope(findings, rows)
        self.assertEqual(lessons['schema_version'], 1)
        self.assertEqual(lessons['kind'], 'curated_observational_hypotheses')
        self.assertEqual(lessons['project_signals'], [])
        item = lessons['cross_cutting'][0]
        self.assertEqual(item['authority'], 'historical observation; current goal_lock overrides')
        self.assertEqual(item['review_status'], 'candidate')
        self.assertIsNone(item['reviewed_by'])
        self.assertEqual(item['repos'], ['kvnloo/example'])
        self.assertEqual(len(item['evidence'][0]['sha256']), 64)
        self.assertIn('job_id', item['evidence'][0])

    def test_cli_outputs_atomic_and_default_never_probes(self):
        self.job(metadata={'repo': 'kvnloo/example'})
        (self.state / 'registry.json').write_text(json.dumps(self.registry))
        capacity = types.SimpleNamespace(export_capacity=lambda state, output: steward.atomic_write(output / 'capacity.json', '{}\n'))
        with patch.dict(sys.modules, {'fleet_steward_capacity': capacity}), \
             patch.object(steward.subprocess, 'run', side_effect=AssertionError('dry run SSH')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(steward.main(['--state', str(self.state), '--dry-run']), 0)
        output = self.state / 'steward'
        for name in ('ledger.jsonl', 'findings.json', 'parameters.json', 'lessons.json', 'lessons.jsonl', 'report.md', 'capacity.json'):
            self.assertTrue((output / name).exists(), name)
        self.assertEqual(len((output / 'ledger.jsonl').read_text().splitlines()), 1)
        self.assertEqual(list(output.glob('.*-*')), [])

    def test_state_lock_serializes_distinct_output_paths(self):
        with (self.state / '.steward.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(steward.main(['--state', str(self.state), '--output', str(self.state / 'elsewhere')]), 75)

    def test_prune_fails_closed_without_registry_or_wrong_user(self):
        with patch.object(steward.subprocess, 'run', side_effect=AssertionError('must not SSH')):
            self.assertEqual(steward.cache_action({}, True)['status'], 'held')
            self.registry['nodes']['mbp']['ssh_user'] = 'root'
            self.assertEqual(steward.cache_action(self.registry, True)['status'], 'held')

    def test_prune_targets_only_fixed_mbp_agentjob_paths(self):
        completed = types.SimpleNamespace(returncode=0, stdout='{"status":"held","reason":"disk sufficient"}')
        with patch.object(steward.subprocess, 'run', return_value=completed) as run:
            result = steward.cache_action(self.registry, True)
        self.assertEqual(result['status'], 'held')
        args = run.call_args.args[0]
        self.assertIn('agentjob@100.78.215.21', args)
        self.assertIn('2222', args)
        self.assertIn('/usr/local/bin/fleet-node-probe', args[-1])
        for path in steward.CACHE_PATHS:
            self.assertIn(path, args[-1])
        self.assertNotIn('sudo', args)

    def execute_prune_program(self, probe, symlink=False):
        class FakePath:
            def __init__(self, raw):
                self.raw = raw
            def resolve(self):
                return self
            def is_symlink(self):
                return symlink
            def is_dir(self):
                return True
        with patch.object(steward.subprocess, 'check_output', return_value=json.dumps(probe).encode()), \
             patch('time.time', return_value=1000), patch('pathlib.Path', FakePath), \
             patch('shutil.rmtree') as remove, patch('os.getuid', return_value=2000), \
             patch.object(pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=2000)), \
             patch('shutil.disk_usage', return_value=types.SimpleNamespace(free=1024)), \
             patch.object(sys, 'argv', ['prune', '15']), contextlib.redirect_stdout(io.StringIO()):
            try:
                exec(steward.PRUNE_PROGRAM, {})
            except SystemExit:
                pass
            return [call.args[0].raw for call in remove.call_args_list]

    def test_fixed_remote_prune_checks_actual_probe_age_and_low_disk(self):
        for probe in ({'ts': 900, 'disk_lane': {'free_gb': 1}}, {'ts': 1000, 'disk_lane': {'free_gb': 20}},
                      {'ts': 1000}, {'ts': 1000, 'disk_lane': {'free_gb': float('nan')}}):
            self.assertEqual(self.execute_prune_program(probe), [])
        self.assertEqual(self.execute_prune_program({'ts': 1000, 'disk_lane': {'free_gb': 1}}), list(steward.CACHE_PATHS))
        self.assertEqual(self.execute_prune_program({'ts': 1000, 'disk_lane': {'free_gb': 1}}, symlink=True), [])


if __name__ == '__main__':
    unittest.main()
