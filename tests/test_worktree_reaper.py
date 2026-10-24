"""Behavioral coverage for preservation and the shared reaper classifier."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('worktree_reaper_tests_target', Path(__file__).resolve().parents[1] / 'scripts/worktree-reaper.py')
reaper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reaper
SPEC.loader.exec_module(reaper)


class ReaperBehavior(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'checkouts'
        self.root.mkdir()
        self.repo = self.root / 'example'
        self.repo.mkdir()
        self.git(self.repo, 'init', '-b', 'main')
        self.git(self.repo, 'config', 'user.name', 'Test')
        self.git(self.repo, 'config', 'user.email', 'test@example.invalid')
        (self.repo / 'file.txt').write_text('original\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-m', 'Initial')
        self.out = self.base / 'receipts'
        self.out.mkdir()
        self.archive = self.base / 'archives'
        self.archive.mkdir()

    def git(self, path, *args):
        result = subprocess.run(['git', '-C', str(path), *args], text=True, capture_output=True, check=True)
        return result.stdout.strip()

    def age(self, path, days=2):
        old = time.time() - days * reaper.DAY
        for base, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d != '.git']
            for name in files:
                if name != '.git':
                    os.utime(Path(base) / name, (old, old), follow_symlinks=False)
            os.utime(base, (old, old), follow_symlinks=False)

    def inspect(self, refs=None):
        return reaper.inspect(str(self.repo), [str(self.root)], refs or {}, time.time())

    def test_discovery_finds_clones_and_registered_linked_worktrees(self):
        linked = self.root / 'linked'
        self.git(self.repo, 'worktree', 'add', '-b', 'feature', str(linked))
        self.assertEqual(set(reaper.discover([str(self.root)])), {str(self.repo), str(linked)})

    def test_discovery_excludes_generated_fixture_worktrees(self):
        for index, name in enumerate(('runs', 'artifacts', 'wiring', 'tmp', '_check', 'pytest-of-test')):
            container = self.root / name
            container.mkdir()
            linked = container / 'fixture'
            self.git(self.repo, 'worktree', 'add', '-b', f'fixture-{index}', str(linked))
        self.assertEqual(reaper.discover([str(self.root)]), [str(self.repo)])

    def test_recent_files_are_live(self):
        self.assertEqual(self.inspect()['class'], 'LIVE')

    def test_live_reference_is_specific(self):
        self.age(self.repo)
        row = self.inspect({str(self.repo / 'file.txt'): {'process:123:fd:4'}})
        self.assertEqual(row['class'], 'LIVE')
        self.assertTrue(any('process:123:fd:4' in x for x in row['live_reasons']))

    def test_active_guard_source_is_live_without_recent_files_or_processes(self):
        self.age(self.repo)
        for reason in ('active-guard-stack:PR192-stack-ancestor', 'active-guard-stack:PR212-deployed-backend'):
            with self.subTest(reason=reason), patch.object(reaper, 'ACTIVE_GUARD_SOURCES', {str(self.repo): reason}):
                refs = reaper.active_guard_references()
                row = self.inspect(refs)
                self.assertEqual(row['class'], 'LIVE')
                self.assertTrue(any(reason in evidence for evidence in row['live_reasons']))

    def test_clean_local_only_clone_is_wip_not_discardable(self):
        self.age(self.repo)
        row = self.inspect()
        self.assertEqual(row['class'], 'WIP')
        self.assertGreater(row['unpublished_commit_count'], 0)

    def test_unpublished_other_branch_makes_plain_clone_wip(self):
        remote = self.base / 'remote.git'
        self.git(self.repo, 'clone', '--bare', str(self.repo), str(remote))
        self.git(self.repo, 'remote', 'add', 'origin', str(remote))
        self.git(self.repo, 'fetch', 'origin')
        self.git(self.repo, 'checkout', '-b', 'hidden')
        (self.repo / 'private.txt').write_text('unpublished branch\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-m', 'Local branch')
        self.git(self.repo, 'checkout', 'main')
        self.age(self.repo)
        row = self.inspect()
        self.assertTrue(row['head_in_remote_tracking'])
        self.assertEqual(row['class'], 'WIP')
        self.assertGreater(row['unpublished_commit_count'], 0)

    def test_bundle_preserves_staged_and_unstaged_versions(self):
        (self.repo / 'file.txt').write_text('staged\n')
        self.git(self.repo, 'add', 'file.txt')
        (self.repo / 'file.txt').write_text('working\n')
        (self.repo / 'untracked.txt').write_text('untracked\n')
        self.age(self.repo)
        before_head = self.git(self.repo, 'rev-parse', 'HEAD')
        record = reaper.preserve(self.inspect(), self.out, self.archive)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), before_head)
        self.assertEqual(self.git(self.repo, 'show', ':file.txt'), 'staged')
        restored = self.base / 'restored'
        self.git(self.repo, 'clone', record['bundle'], str(restored))
        self.git(restored, 'checkout', record['archive_branch'])
        self.assertEqual((restored / 'file.txt').read_text(), 'working\n')
        self.assertEqual((restored / 'untracked.txt').read_text(), 'untracked\n')
        self.assertEqual(self.git(restored, 'show', record['staged_commit'] + ':file.txt'), 'staged')

    def test_bundle_preserves_non_head_branch(self):
        self.git(self.repo, 'checkout', '-b', 'hidden')
        (self.repo / 'hidden.txt').write_text('valuable\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-m', 'Hidden')
        self.git(self.repo, 'checkout', 'main')
        self.age(self.repo)
        record = reaper.preserve(self.inspect(), self.out, self.archive)
        restored = self.base / 'restored'
        self.git(self.repo, 'clone', '--mirror', record['bundle'], str(restored))
        self.assertEqual(self.git(restored, 'show', 'refs/heads/hidden:hidden.txt'), 'valuable')

    def test_apply_removes_old_standalone_after_bundle(self):
        self.age(self.repo)
        argv = ['worktree-reaper', '--apply', '--root', str(self.root), '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), patch.object(reaper, 'references', return_value=({}, [])), patch.object(reaper.os, 'nice'):
            self.assertEqual(reaper.main(), 0)
        self.assertFalse(self.repo.exists())
        self.assertEqual(len(list(self.archive.glob('*.bundle'))), 1)
        self.assertTrue((self.out / 'REPORT.md').is_file())


if __name__ == '__main__':
    unittest.main()
