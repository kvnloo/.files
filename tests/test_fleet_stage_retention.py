"""Worker stage retention safety regressions; no cluster or SSH required."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/fleet-stage-retention.py'
spec = importlib.util.spec_from_file_location('stage_retention', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'fleet-mbp-0123456789abcdef'
        self.path.mkdir()
        self.leases = m.load_leases()
        self.lease = dict(schema=self.leases.SCHEMA, owner=self.path.name, node='mbp',
                          path=str(self.path), kind='spool', created_at=1, ttl=1,
                          keep_receipts=[])
        (self.path / self.leases.SIDECAR).write_text(json.dumps(self.lease))
        self.receipt = {'job_id': self.path.name, 'keep': False, 'fetch': [],
                        'terminal': {'job': {'metadata': {'name': self.path.name},
                          'status': {'conditions': [{'type': 'Complete', 'status': 'True'}]}}}}
        self.snapshot = dict(jobs=[], pods=[], workloads=[])

    def reason(self):
        return m.eligible(self.path, self.receipt, self.snapshot, self.leases, 100, os.getuid())

    def test_completed_expired_owned(self):
        self.assertIsNone(self.reason())

    def test_service_process_exception_is_exact(self):
        root = Path(self.tmp.name) / 'proc'
        manager = root / '10'
        helper = root / '11'
        manager.mkdir(parents=True)
        helper.mkdir()
        (manager / 'stat').write_text('10 (systemd) S 1 0 0')
        (manager / 'cmdline').write_bytes(b'/usr/lib/systemd/systemd\x00--user\x00')
        (helper / 'stat').write_text('11 ((sd-pam)) S 10 0 0')
        (helper / 'cmdline').write_bytes(b'(sd-pam)\x00')
        self.assertTrue(m.service_process(manager, os.getuid()))
        self.assertTrue(m.service_process(helper, os.getuid()))
        (manager / 'stat').write_text('10 (systemd) S 9 0 0')
        self.assertFalse(m.service_process(manager, os.getuid()))
        self.assertFalse(m.service_process(helper, os.getuid()))
        (manager / 'stat').write_text('10 (systemd) S 1 0 0')
        (manager / 'cmdline').write_bytes(b'arbitrary-worker\x00')
        self.assertFalse(m.service_process(manager, os.getuid()))
        self.assertFalse(m.service_process(helper, os.getuid()))
        (manager / 'cmdline').unlink()
        self.assertFalse(m.service_process(manager, os.getuid()))

    def test_arbitrary_opaque_process_keeps_stage(self):
        payload = {'receipts': {self.path.name: self.receipt}, 'snapshot': self.snapshot}
        with patch.object(m.Path, 'home', return_value=Path('/home/agentjob')), \
             patch.object(m.os, 'getuid', return_value=123), \
             patch.object(m, 'maintenance_ancestors', return_value={999}), \
             patch.object(m.Path, 'iterdir', return_value=iter([Path('/proc/123')])), \
             patch.object(m.Path, 'stat') as st, \
             patch.object(m, 'service_process', return_value=False), \
             patch.object(m.os, 'readlink', side_effect=PermissionError('opaque')):
            st.return_value.st_uid = 123
            rows = m.worker(payload, self.leases, root=self.path.parent)
        self.assertEqual(rows[0]['action'], 'keep')
        self.assertEqual(rows[0]['reason'], 'local reference or visibility unknown')

    def test_only_observed_maintenance_ancestor_chain(self):
        root = Path(self.tmp.name) / 'ancestry'
        for pid, parent in ((30, 20), (20, 1), (1, 0), (40, 1)):
            directory = root / str(pid)
            directory.mkdir(parents=True)
            (directory / 'status').write_text(f'Name: sshd-session\nPPid:\t{parent}\n')
        self.assertEqual(m.maintenance_ancestors(30, root), {30, 20, 1})
        self.assertNotIn(40, m.maintenance_ancestors(30, root))
        (root / '20/status').write_text('Name: opaque\n')
        with self.assertRaises(ValueError):
            m.maintenance_ancestors(30, root)

    def test_queued_active_and_referenced(self):
        for spec in ({'suspend': True}, {'template': {'spec': {'containers': [
                {'env': [{'name': 'CACHE', 'value': str(self.path / 'src/target')}]}]}}}):
            self.snapshot['jobs'] = [{'metadata': {'name': 'other-job'}, 'spec': spec}]
            if 'suspend' in spec:
                self.snapshot['jobs'][0]['metadata']['name'] = self.path.name
            self.assertEqual(self.reason(), 'live or referenced')

    def test_missing_fetch_proof(self):
        (self.path / 'export').write_text('result')
        self.receipt['fetch'] = ['export']
        self.assertEqual(self.reason(), 'missing fetch proof')
        self.receipt['_fetch_proof'] = {'export': m.digest(self.path / 'export')}
        self.assertIsNone(self.reason())

    def test_attempt_exit_not_terminal(self):
        (self.path / 'exit').write_text('0')
        self.receipt['terminal'] = {}
        self.assertEqual(self.reason(), 'missing terminal Job evidence')

    def test_keep_and_unexpired(self):
        self.receipt['keep'] = True
        self.assertIsNotNone(self.reason())
        self.receipt['keep'] = False
        self.lease['ttl'] = 1000
        (self.path / self.leases.SIDECAR).write_text(json.dumps(self.lease))
        self.assertEqual(self.reason(), 'unexpired')

    def test_keep_expiry_and_retention_window(self):
        self.receipt.update(keep=True, keep_until=200, retention_until=200)
        self.assertIsNotNone(self.reason())
        self.receipt['keep_until'] = 50
        self.assertEqual(self.reason(), 'retention window not elapsed')
        self.receipt['retention_until'] = 50
        self.assertIsNone(self.reason())
        for invalid in (None, True, '50', float('nan'), float('inf')):
            self.receipt['keep_until'] = invalid
            self.assertIsNotNone(self.reason())

    def test_incomplete_fetch_preserved(self):
        self.receipt['fetch_completed'] = False
        self.assertEqual(self.reason(), 'fetch not completed')
        self.receipt['fetch_completed'] = True
        self.assertIsNone(self.reason())

    def test_symlink_and_path_escape(self):
        (self.path / 'escape').symlink_to('/tmp')
        with self.assertRaises(ValueError):
            self.reason()
        with self.assertRaises(ValueError):
            m.identity(self.path / '..', os.getuid())

    def test_dryrun_apply_and_changed_plan(self):
        payload = {'receipts': {self.path.name: self.receipt}, 'snapshot': self.snapshot}
        with patch.object(m.Path, 'home', return_value=Path('/home/agentjob')), \
             patch.object(m.os, 'getuid', return_value=123), \
             patch.object(m, 'identity', return_value='stable'), \
             patch.object(m, 'eligible', return_value=None), \
             patch.object(self.leases, 'receipt_copy') as archive, \
             patch.object(m.shutil, 'rmtree') as remove:
            remove.avoids_symlink_attacks = True
            rows = m.worker(payload, self.leases, root=self.path.parent)
            self.assertEqual(rows[0]['action'], 'would-delete')
            remove.assert_not_called()
            rows = m.worker(payload, self.leases, True, root=self.path.parent)
            self.assertEqual(rows[0]['action'], 'keep')
            payload['plan'] = {str(self.path): 'stable'}
            rows = m.worker(payload, self.leases, True, root=self.path.parent)
            self.assertEqual(rows[0]['action'], 'deleted')
            archive.assert_called_once()
            remove.assert_called_once_with(self.path)


class ReattachTests(unittest.TestCase):
    name = 'fleet-mbp-0123456789abcdef'

    def job(self, condition='Complete', **annotations):
        return {'metadata': {'name': self.name, 'namespace': 'fleet-mbp', 'annotations': annotations},
                'status': {'conditions': [{'type': condition, 'status': 'True'}]}}

    def test_detached_terminal_job_is_reattached(self):
        receipts = {self.name: {'job_id': self.name, 'host': False}}
        self.assertEqual(m.reattach_candidates([self.job()], receipts), [self.name])
        self.assertEqual(m.reattach_candidates([self.job('Failed')], receipts), [self.name])

    def test_recorded_terminal_with_failed_fetch_is_reattached(self):
        receipts = {self.name: {'terminal': {'job': self.job()}, 'fetch_completed': False}}
        self.assertEqual(m.reattach_candidates([self.job()], receipts), [self.name])
        receipts[self.name]['fetch_completed'] = True
        self.assertEqual(m.reattach_candidates([self.job()], receipts), [])

    def test_live_host_foreign_or_unreceipted_jobs_are_left_alone(self):
        receipts = {self.name: {'job_id': self.name}}
        running = self.job()
        running['status'] = {'active': 1}
        self.assertEqual(m.reattach_candidates([running], receipts), [])
        self.assertEqual(m.reattach_candidates([self.job(**{'fleet.z0.dev/host': 'true'})], receipts), [])
        self.assertEqual(m.reattach_candidates([self.job()], {self.name: {'host': True}}), [])
        self.assertEqual(m.reattach_candidates([self.job()], {}), [])
        foreign = self.job()
        foreign['metadata']['namespace'] = 'default'
        self.assertEqual(m.reattach_candidates([foreign], receipts), [])
        odd = self.job()
        odd['metadata']['name'] = 'fleet-mbp-../x'
        self.assertEqual(m.reattach_candidates([odd], {'fleet-mbp-../x': {}}), [])

    def test_reattach_uses_producer_attach_without_waiting(self):
        runs = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(runs))
        (runs / f'{self.name}.json').write_text(json.dumps({'job_id': self.name}))
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            if 'get' in argv:
                return m.subprocess.CompletedProcess(argv, 0, json.dumps({'items': [self.job()]}), '')
            return m.subprocess.CompletedProcess(argv, 0, None, 'fleet: job exited 0')
        fake_paths = type(sys)('fleet_paths')
        fake_paths.runs_dir = lambda: runs
        with patch.dict(sys.modules, {'fleet_paths': fake_paths}), patch.object(m.subprocess, 'run', fake_run):
            rows = m.reattach_detached()
        self.assertEqual(rows[0]['job'], self.name)
        self.assertEqual(rows[0]['rc'], 0)
        self.assertEqual(calls[-1][-4:], ['--attach', self.name, '--wait', '0'])
        self.assertTrue(calls[-1][1].endswith('scripts/fleet-kueue'))


if __name__ == '__main__':
    unittest.main()
