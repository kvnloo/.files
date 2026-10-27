"""scripts/github-dev-tracks-default: dev always contains the default branch; default is never written."""
import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'github-dev-tracks-default'
loader = importlib.machinery.SourceFileLoader('github_dev_tracks_default', str(SCRIPT))
spec = importlib.util.spec_from_loader('github_dev_tracks_default', loader)
gdt = importlib.util.module_from_spec(spec)
loader.exec_module(gdt)


class Decide(unittest.TestCase):
    def test_contained(self):
        self.assertEqual(gdt.decide(0, 5), 'ok')

    def test_strictly_behind_fast_forwards(self):
        self.assertEqual(gdt.decide(3, 0), 'fast-forward')

    def test_diverged_opens_pr(self):
        self.assertEqual(gdt.decide(3, 4), 'sync-pr')


class SyncRepo(unittest.TestCase):
    def run_with(self, responses, dry_run=False):
        calls = []

        def fake(*args, check=True):
            calls.append(args)
            for key, value in responses:
                if key in ' '.join(args):
                    return value
            return ''

        with mock.patch.object(gdt, 'gh', side_effect=fake):
            rec = gdt.sync_repo('o', 'r', 'main', dry_run)
        return rec, calls

    def test_fast_forward_never_forces_and_never_touches_default(self):
        rec, calls = self.run_with([
            ('compare/dev...main', json.dumps({'ahead_by': 2, 'behind_by': 0, 'status': 'ahead'})),
            ('commits/main', 'a' * 40),
        ])
        self.assertEqual(rec['action'], 'fast-forward')
        patch = [c for c in calls if 'PATCH' in c]
        self.assertEqual(len(patch), 1)
        self.assertIn('repos/o/r/git/refs/heads/dev', patch[0])
        self.assertIn('force=false', patch[0])
        self.assertFalse(any('heads/main' in ' '.join(c) for c in calls))

    def test_diverged_reuses_open_pr_and_merges_only_when_clean(self):
        rec, calls = self.run_with([
            ('compare/dev...main', json.dumps({'ahead_by': 2, 'behind_by': 3, 'status': 'diverged'})),
            ('pr list', json.dumps([{'number': 7}])),
            ('pr view', json.dumps({'mergeable': 'MERGEABLE', 'mergeStateStatus': 'UNSTABLE'})),
        ])
        self.assertEqual(rec['pr'], 7)
        self.assertFalse(any(c[:2] == ('pr', 'merge') for c in calls))
        self.assertFalse(any(c[:2] == ('pr', 'create') for c in calls))

    def test_diverged_clean_pr_is_merged(self):
        rec, calls = self.run_with([
            ('compare/dev...main', json.dumps({'ahead_by': 2, 'behind_by': 3, 'status': 'diverged'})),
            ('pr list', '[]'),
            ('pr create', 'https://github.com/o/r/pull/9\n'),
            ('pr view', json.dumps({'mergeable': 'MERGEABLE', 'mergeStateStatus': 'CLEAN'})),
        ])
        self.assertEqual(rec['result'], 'merged')
        create = [c for c in calls if c[:2] == ('pr', 'create')][0]
        self.assertEqual(create[create.index('--base') + 1], 'dev')
        self.assertTrue(any(c[:3] == ('pr', 'merge', '9') for c in calls))

    def test_dry_run_writes_nothing(self):
        rec, calls = self.run_with([
            ('compare/dev...main', json.dumps({'ahead_by': 2, 'behind_by': 0, 'status': 'ahead'})),
        ], dry_run=True)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
