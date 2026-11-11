"""No host, Kubernetes or provider mutation in these fixtures."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import host_optimizer as host
import host_experiments as experiments


def snapshot():
    return {'ts': 200., 'monotonic': 200., 'boot_id': 'boot', 'cpus': 20,
            'mem_available_bytes': 8*2**30,
            'disks': {'root': {'free_bytes': 20*2**30}},
            'pressure': {k: {r: {'avg10': 0, 'avg60': 0}}
                         for k, r in [('cpu', 'some'), ('memory', 'full'), ('io', 'full')]},
            'cgroups': {'agent.slice': {'cpu_stat': {'usage_usec': 4_000_000,
                'nr_periods': 20, 'nr_throttled': 2}, 'memory_events': {'oom_kill': 1}}}}


class HostOptimizerTests(unittest.TestCase):
    def test_counter_delta_and_boot_or_stale_guards(self):
        now = snapshot()
        prior = copy.deepcopy(now)
        prior['monotonic'] = 198
        prior['cgroups']['agent.slice']['cpu_stat']['usage_usec'] = 0
        prior['cgroups']['agent.slice']['cpu_stat']['nr_periods'] = 10
        prior['cgroups']['agent.slice']['cpu_stat']['nr_throttled'] = 1
        result = host.deltas(now, prior)
        self.assertEqual(result['cgroups']['agent.slice']['cpu_cores_used'], 2.)
        self.assertEqual(result['cgroups']['agent.slice']['throttled_period_fraction'], .1)
        prior['boot_id'] = 'old'
        self.assertEqual(host.deltas(now, prior)['status'], 'baseline_needed')
        prior['boot_id'] = 'boot'
        prior['monotonic'] = -1000
        self.assertEqual(host.deltas(now, prior)['status'], 'stale_or_invalid_interval')

    def test_recreated_cgroup_is_not_negative_load(self):
        now = snapshot()
        prior = copy.deepcopy(now)
        prior['monotonic'] -= 2
        prior['cgroups']['agent.slice']['cpu_stat']['usage_usec'] += 1
        self.assertEqual(host.deltas(now, prior)['cgroups'], {})

    def test_only_known_cpu_ceilings_are_repaired_with_readback(self):
        calls = []
        quotas = {'agent.slice': '2s', 'hermes-worker-test.scope': '1s',
                  'hermes-worker-other.scope': '500ms'}
        def runner(argv, **kwargs):
            calls.append(argv)
            if 'list-units' in argv:
                return json.dumps([{'unit': x} for x in ('hermes-worker-test.scope',
                    'hermes-worker-other.scope', 'app-owner.scope', 'hermes-worker-;bad.scope')])
            if 'show' in argv:
                return quotas[argv[3]]
            quotas[argv[4]] = 'infinity'
            return ''
        result = host.cpu_repair(True, False, runner)
        self.assertEqual(result['repaired'], ['agent.slice', 'hermes-worker-test.scope'])
        changes = [x for x in calls if 'set-property' in x]
        self.assertEqual(len(changes), 2)
        self.assertTrue(all(x[-1] == 'CPUQuota=' for x in changes))
        calls.clear()
        self.assertEqual(host.cpu_repair(True, True, runner)['status'], 'disabled')
        self.assertEqual(calls, [])

    def test_pause_stops_before_mount_probe_or_observation(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            (state/'paused').touch()
            with patch.object(host, 'sample_host') as sample, patch.object(host.os.path, 'ismount') as mount:
                self.assertEqual(host.tick(state, state, state/'missing'), 0)
            sample.assert_not_called()
            mount.assert_not_called()

    def test_mount_absence_never_creates_state(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)/'must-not-create'
            with patch.object(host.os.path, 'ismount', return_value=False):
                with self.assertRaises(RuntimeError):
                    host.tick(state, state, state/'missing')
            self.assertFalse(state.exists())

    def test_harness_projection_never_reads_message_content(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root)/'source.sqlite'
            c = sqlite3.connect(db)
            c.execute('''create table sessions(agent,machine,tool_failure_signal_count,tool_retry_count,
                consecutive_failure_max,runaway_tool_loop_count,missing_verification_count,
                local_modified_at,is_automated,relationship_type,deleted_at)''')
            c.execute('create table messages(content)')
            c.execute('insert into messages values (?)', ('PRIVATE_SOURCE_MUST_NOT_LEAK',))
            c.execute('insert into sessions values (?,?,?,?,?,?,?,?,?,?,?)',
                ('omp', 'groot', 4, 3, 2, 1, 5, '2026-11-03T23:00:00Z', 0, '', None))
            c.commit()
            c.close()
            result = host.harness_summary(db, datetime(2026, 11, 4, tzinfo=timezone.utc))
            self.assertEqual(result['groups'][0]['failure_signals'], 4)
            self.assertNotIn('PRIVATE_SOURCE', json.dumps(result))
            check = sqlite3.connect(db)
            self.assertEqual(check.execute('select count(*) from messages').fetchone()[0], 1)
            check.close()

    def test_findings_use_actual_pressure_and_expose_coverage_limits(self):
        now = snapshot()
        now['disks']['root']['free_bytes'] = 10*2**30
        now['pressure']['memory']['full']['avg60'] = 2
        rows = host.rank_findings(now, {'groups': [{'agent': 'hermes', 'machine': 'groot',
            'failure_signals': 3}]}, {}, {}, {'fleet-health.service': {'ActiveState': 'failed'}})
        self.assertEqual(rows[0]['key'], 'root-disk-pressure')
        self.assertIn('memory-pressure', [r['key'] for r in rows])
        self.assertTrue(all('paired' in r['promotion'] for r in rows))

    def test_historical_analysis_coalesces_and_never_hides_age_or_absence(self):
        cached = {'status': 'observed', 'fingerprint': 'old', 'analyzed_at': 1000}
        self.assertTrue(host.steward_cache_reusable(cached, 'new', 1200, True))
        self.assertFalse(host.steward_cache_reusable(cached, 'new', 1300, True))
        self.assertTrue(host.steward_cache_reusable(cached, 'old', 2700, True))
        self.assertFalse(host.steward_cache_reusable(cached, 'old', 2800, True))
        self.assertFalse(host.steward_cache_reusable(cached, 'old', 900, True))
        self.assertFalse(host.steward_cache_reusable(cached, 'old', 1100, False))

    def test_proc_fields_normalize_meminfo_colon(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"meminfo"
            path.write_text("MemAvailable: 123 kB\nusage_usec 20\n")
            self.assertEqual(host.fields(path), {"MemAvailable": "123 kB", "usage_usec": "20"})

    def test_atomic_private_complete_json(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'latest.json'
            host.atomic(path, {'value': 1})
            self.assertEqual(json.loads(path.read_text()), {'value': 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ExperimentTests(unittest.TestCase):
    def test_busy_or_unknown_host_never_launches_probe(self):
        now = snapshot()
        self.assertTrue(experiments.eligible(now))
        now['pressure']['cpu']['some']['avg10'] = 11
        self.assertFalse(experiments.eligible(now))
        now['pressure'] = {}
        self.assertFalse(experiments.eligible(now))

    def test_failed_incomplete_and_slow_results_never_win(self):
        self.assertEqual(experiments.summarize([])['decision'], 'reject')
        rows = [{'arm': arm, 'wall_s': 1. if arm == 'one_core' else .7, 'correct': True}
                for _ in range(6) for arm in ('one_core', 'unlimited')]
        self.assertEqual(experiments.summarize(rows)['decision'], 'supported_fixture_only')
        rows[1]['correct'] = False
        self.assertEqual(experiments.summarize(rows)['decision'], 'reject')
        rows[1]['correct'] = True
        rows[1]['wall_s'] = 2.
        self.assertEqual(experiments.summarize(rows)['decision'], 'inconclusive')

    def test_crashed_attempt_backoff_and_pause_are_durable(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            host.atomic(state/'cpu-experiment.json', {'attempted_at': host.time.time(), 'status': 'started'})
            with patch.object(experiments, 'hash_work') as work:
                result = experiments.measure_cpu(state, snapshot(), lambda *_: self.fail('launch'), host.atomic)
            self.assertEqual(result['status'], 'not_due')
            work.assert_not_called()

    def test_units_do_not_schedule_second_polling_timer_or_restart_forever(self):
        service = (ROOT/'config/systemd/user/host-optimizer.service').read_text()
        path = (ROOT/'config/systemd/user/host-optimizer.path').read_text()
        self.assertNotIn('Restart=always', service)
        self.assertIn('Type=oneshot', service)
        self.assertIn('PathChanged=', path)
        self.assertIn('--repair-cpu --experiments', service)

    def test_harness_timeout_keeps_last_observation_labelled_stale_until_too_old(self):
        failed = {'status': 'unavailable', 'reason': 'OperationalError'}
        seen = {'status': 'observed', 'sampled_sessions': 9, 'groups': []}
        stale = host.carry_forward(failed, seen, now=1000., previous_ts=900.)
        self.assertEqual((stale['status'], stale['age_s'], stale['sampled_sessions']), ('stale', 100., 9))
        again = host.carry_forward(failed, stale, now=1200., previous_ts=1000.)
        self.assertEqual(again['age_s'], 300.)  # aged from the real observation, not the stale copy
        self.assertEqual(host.carry_forward(failed, seen, now=9000., previous_ts=900.), failed)
        self.assertEqual(host.carry_forward(seen, stale, now=1000., previous_ts=900.), seen)


if __name__ == '__main__':
    unittest.main()
