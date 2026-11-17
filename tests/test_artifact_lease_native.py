import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('lease_native', Path(__file__).resolve().parents[1] / 'scripts/artifact_lease_native.py')
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.node = {'name': 's22', 'serial': 'SERIAL', 'model': 'MODEL'}
        self.lease = {'schema': 'z0.artifact-lease.v1', 'path': '/data/local/tmp/fleet-jobs/test',
                      'node': 's22', 'owner': 'fixture', 'kind': 'spool',
                      'created_at': 1, 'ttl': 1, 'keep_receipts': []}
        self.item = {'path': self.lease['path'], 'bytes': 4096, 'identity': '1:2:3:4',
                     'safe_ancestors': True, 'terminal': True, 'lease': self.lease,
                     'lease_sha256': 'abcd', 'fingerprint': 'fingerprint'}
        self.evidence = {'items': [self.item], 'references': [], 'unknown': []}

    def reasons(self, item=None, evidence=None):
        return n.classify(item or self.item, evidence or self.evidence, 's22', 100, n.core().validate)

    def test_expired_known_nonlive_is_eligible(self):
        self.assertEqual(self.reasons(), [])

    def test_unknown_proc_keeps(self):
        self.evidence['unknown'] = ['/proc/1/maps']
        self.assertIn('incomplete native process/config visibility', self.reasons())

    def test_reference_keeps(self):
        self.evidence['references'] = [self.item['path'] + '/model.gguf']
        self.assertIn('live process/config reference', self.reasons())

    def test_symlink_and_queued_spool_keep(self):
        self.item['safe_ancestors'] = False
        self.item['terminal'] = False
        self.assertIn('symlink ancestor', self.reasons())
        self.assertIn('spool completion unknown', self.reasons())

    def test_unknown_and_unexpired_never_delete(self):
        self.item['lease'] = None
        self.assertIn('missing or invalid lease', self.reasons())
        self.item['lease'] = {**self.lease, 'ttl': 1000}
        self.assertIn('unexpired', self.reasons())

    def test_native_model_is_protected(self):
        self.item['lease']['kind'] = 'model'
        self.assertIn('native model/runtime/worktree protected', self.reasons())

    def test_actor_uses_pinned_cwd_and_rechecks_visibility(self):
        calls = []
        def run(argv, source):
            calls.append(source)
            return 'REMOVED\n'
        action = n.delete('adb', 'transport', self.node, self.item, run)
        self.assertEqual(action['bytes'], 4096)
        self.assertIn('find . -xdev -depth ! -name . -delete', calls[0])
        self.assertIn('UNKNOWN', calls[0])
        self.assertIn('sha256sum', calls[0])
        self.assertNotIn('rm -rf', calls[0])

    def test_identity_mismatch_fails_closed(self):
        with self.assertRaises(RuntimeError):
            n.snapshot('adb', 'transport', self.node, lambda *_: 'IDENTITY\tOTHER\tMODEL\n')

    def test_snapshot_parses_real_lease_and_denial(self):
        encode = lambda value: base64.b64encode(value.encode()).decode()
        raw = '\n'.join(['IDENTITY\tSERIAL\tMODEL', 'UNKNOWN\t/proc/1/maps',
                         'ITEM\t' + encode(self.item['path']) + '\t4\t1:2:3:4\tyes\tfingerprint',
                         'LEASE\t' + encode(self.item['path']) + '\t' + encode(json.dumps(self.lease))])
        snapshot = n.snapshot('adb', 'transport', self.node, lambda *_: raw)
        self.assertEqual(snapshot['items'][0]['bytes'], 4096)
        self.assertEqual(snapshot['items'][0]['lease'], self.lease)
        self.assertEqual(snapshot['unknown'], ['/proc/1/maps'])

    def test_unknown_inventory_apply_does_not_call_actor(self):
        self.evidence['unknown'] = ['/proc/1/fd']
        with patch.object(n, 'snapshot', return_value=self.evidence), patch.object(n, 'host_references', return_value=([], [])), patch.object(n, 'delete') as actor:
            report = n.inventory('adb', 'transport', self.node, True, lambda *_: '')
        self.assertEqual(report['would_reap_bytes'], 0)
        self.assertEqual(report['removed_bytes'], 0)
        actor.assert_not_called()

    def test_known_apply_preserves_receipts_then_deletes(self):
        fresh = copy.deepcopy(self.evidence)
        with tempfile.TemporaryDirectory() as tmp, patch.object(n.Path, 'home', return_value=Path(tmp)), patch.object(n, 'snapshot', side_effect=[self.evidence, fresh]), patch.object(n, 'host_references', return_value=([], [])), patch.object(n, 'receipts', return_value='digest') as receipts, patch.object(n, 'delete', return_value={'event': 'removed', 'bytes': 4096}) as actor:
            report = n.inventory('adb', 'transport', self.node, True, lambda *_: '')
            self.assertEqual(report['removed_bytes'], 4096)
            receipts.assert_called_once()
            actor.assert_called_once()
            self.assertEqual(len(list(Path(tmp).rglob('*.intent.json'))), 1)


if __name__ == '__main__':
    unittest.main()
