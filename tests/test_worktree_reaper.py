"""Behavioral coverage for preservation and the shared reaper classifier."""
import importlib.util
import json
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
        # These regressions exercise archival/liveness mechanics independently
        # of the lease gate, whose real policy has dedicated coverage below.
        lease_gate = patch.object(reaper, 'lease_allows_reaping', return_value=True)
        lease_gate.start()
        self.addCleanup(lease_gate.stop)

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

    def test_installed_skill_link_under_home_keeps_old_checkout_live(self):
        self.age(self.repo)
        home = self.base / 'home'
        links = home / '.agents/skills'
        links.mkdir(parents=True)
        target = self.repo / 'skills/abab-meta-research'
        (links / 'abab-meta-research').symlink_to(target, target_is_directory=True)
        refs, errors = reaper.symlink_references(home=home, extra_roots=[])
        self.assertEqual(errors, [])
        row = self.inspect(refs)
        self.assertEqual(row['class'], 'LIVE')
        self.assertTrue(any('home-symlink:' in reason for reason in row['live_reasons']))
        self.assertIn(str(target), refs)
        argv = ['worktree-reaper', '--apply', '--root', str(self.root),
                '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), \
                patch.object(reaper, 'references', return_value=(refs, errors)), \
                patch.object(reaper.os, 'nice'):
            self.assertEqual(reaper.main(), 0)
        self.assertTrue(self.repo.exists())
        self.assertEqual(list(self.archive.glob('*.bundle')), [])

    def test_arbitrary_home_link_and_external_profile_link_are_live(self):
        self.age(self.repo)
        home = self.base / 'home'
        outside = self.base / 'hermes-home'
        for root, relative in ((home, 'custom/deep/active'),
                               (outside, 'profiles/clean/skills/active')):
            link = root / relative
            link.parent.mkdir(parents=True)
            link.symlink_to(self.repo / 'missing-after-removal', target_is_directory=True)
        refs, errors = reaper.symlink_references(home=home, extra_roots=[outside])
        self.assertEqual(errors, [])
        self.assertEqual(len(refs[str(self.repo / 'missing-after-removal')]), 2)
        self.assertEqual(self.inspect(refs)['class'], 'LIVE')

    def test_installed_plugin_checkout_is_live_without_symlinks(self):
        home = self.base / 'home'
        plugins = home / '.omp/agent/extensions'
        plugins.mkdir(parents=True)
        child = plugins / 'owned'
        self.git(self.repo, 'clone', str(self.repo), str(child))
        self.age(child)
        refs, errors = reaper.symlink_references(home=home, extra_roots=[])
        self.assertEqual(errors, [])
        row = reaper.inspect(str(child), [str(home)], refs, time.time())
        self.assertEqual(row['class'], 'LIVE')
        self.assertTrue(any('installed-code-directory:' in reason for reason in row['live_reasons']))

    @unittest.skipIf(os.geteuid() == 0, 'requires ordinary-user directory permissions')
    def test_unreadable_link_inventory_blocks_all_removals(self):
        self.age(self.repo)
        home = self.base / 'home'
        blocked = home / '.hermes/private'
        blocked.mkdir(parents=True)
        blocked.chmod(0)
        try:
            refs, errors = reaper.symlink_references(home=home, extra_roots=[])
        finally:
            blocked.chmod(0o700)
        self.assertTrue(errors)
        argv = ['worktree-reaper', '--apply', '--root', str(self.root),
                '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), \
                patch.object(reaper, 'references', return_value=(refs, errors)), \
                patch.object(reaper.os, 'nice'):
            self.assertEqual(reaper.main(), 1)
        self.assertTrue(self.repo.exists())
        self.assertEqual(list(self.archive.glob('*.bundle')), [])

    @unittest.skipIf(os.geteuid() == 0, 'requires ordinary-user directory permissions')
    def test_foreign_owner_private_directory_is_recorded_not_failed(self):
        self.check_foreign_directory_scan(0o700, ignored=True)

    @unittest.skipIf(os.geteuid() == 0, 'requires ordinary-user directory permissions')
    def test_foreign_owner_traversable_directory_still_fails_closed(self):
        self.check_foreign_directory_scan(0o711, ignored=False)

    def check_foreign_directory_scan(self, mode, ignored):
        home = self.base / 'home'
        blocked = home / 'foreign'
        blocked.mkdir(parents=True)
        blocked.chmod(0)
        actual_stat = os.stat
        def foreign_stat(path, *args, **kwargs):
            result = actual_stat(path, *args, **kwargs)
            if os.fspath(path) == str(blocked):
                values = list(result)
                values[0] = (result.st_mode & ~0o777) | mode
                values[4] = os.geteuid() + 1
                return os.stat_result(values)
            return result
        try:
            with patch.object(reaper.os, 'stat', foreign_stat):
                _, errors = reaper.symlink_references(home=home, extra_roots=[], out=self.out)
        finally:
            blocked.chmod(0o700)
        receipt = json.loads((self.out / 'manifest.jsonl').read_text().splitlines()[-1])
        self.assertEqual(receipt['event'], 'installed_link_scan')
        if ignored:
            self.assertEqual(errors, [])
            self.assertEqual(receipt['unreadable_foreign_owner'],
                             [{'path': str(blocked), 'reason': 'unreadable_foreign_owner',
                               'uid': os.geteuid() + 1, 'mode': '0o700'}])
        else:
            self.assertTrue(errors)
            self.assertEqual(receipt['unreadable_foreign_owner'], [])

    def test_link_index_refreshes_added_nested_links_and_retargets(self):
        home = self.base / 'home'
        home.mkdir()
        index = reaper.LinkIndex()
        with patch.object(reaper, 'LINK_INDEX', index):
            self.assertEqual(reaper.symlink_references(home, [])[0], {})
            nested = home / 'new/deep'
            nested.mkdir(parents=True)
            link = nested / 'active'
            link.symlink_to(self.repo / 'first')
            refs, errors = reaper.symlink_references(home, [])
            self.assertEqual(errors, [])
            self.assertIn(str(self.repo / 'first'), refs)
            link.unlink()
            link.symlink_to(self.repo / 'second')
            refs, errors = reaper.symlink_references(home, [])
            self.assertEqual(errors, [])
            self.assertNotIn(str(self.repo / 'first'), refs)
            self.assertIn(str(self.repo / 'second'), refs)
            link.unlink()
            self.assertEqual(reaper.symlink_references(home, [])[0], {})

    def test_link_index_does_not_enumerate_unchanged_directories(self):
        home = self.base / 'home'
        home.mkdir()
        (home / 'active').symlink_to(self.repo)
        (home / 'ordinary-file').write_text('not link metadata')
        index = reaper.LinkIndex()
        with patch.object(reaper, 'LINK_INDEX', index):
            initial = reaper.symlink_references(home, [])
            cached = index.directories[str(home)]
            self.assertNotIn(('ordinary-file', False), cached[1])
            with patch.object(reaper.os, 'scandir', side_effect=AssertionError('rescanned unchanged directory')):
                self.assertEqual(reaper.symlink_references(home, []), initial)
            self.assertIs(index.directories[str(home)], cached)

    def test_explicit_symlink_root_scans_external_installed_links(self):
        home = self.base / 'home'
        home.mkdir()
        external = self.base / 'external'
        external.mkdir()
        (external / 'active').symlink_to(self.repo)
        alias = home / '.config'
        alias.symlink_to(external, target_is_directory=True)
        refs, errors = reaper.symlink_references(home, [alias])
        self.assertEqual(errors, [])
        self.assertIn('home-symlink:' + str(external / 'active'),
                      refs[str(self.repo)])

    def test_pause_during_archive_prevents_current_removal(self):
        self.age(self.repo)
        preserve = reaper.preserve
        def archive_then_pause(*args):
            result = preserve(*args)
            (self.out / 'PAUSED').write_text('incident pause\n')
            return result
        argv = ['worktree-reaper', '--apply', '--root', str(self.root),
                '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), \
                patch.object(reaper, 'references', return_value=({}, [])), \
                patch.object(reaper, 'preserve', archive_then_pause), \
                patch.object(reaper.os, 'nice'):
            self.assertEqual(reaper.main(), 0)
        self.assertTrue(self.repo.exists())
        self.assertEqual(len(list(self.archive.glob('*.bundle'))), 1)
        rows = [json.loads(line) for line in (self.out / 'manifest.jsonl').read_text().splitlines()]
        self.assertTrue(any(row['event'] == 'removals_paused' for row in rows))
        self.assertFalse(any(row['event'] == 'removed' for row in rows))

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

    def test_shared_base_and_wip_delta_restore_from_emitted_command(self):
        import shlex
        first = self.root / 'linked-a'
        second = self.root / 'linked-b'
        self.git(self.repo, 'worktree', 'add', '-b', 'a', str(first))
        self.git(self.repo, 'worktree', 'add', '-b', 'b', str(second))
        self.age(first)
        first_row = reaper.inspect(str(first), [str(self.root)], {}, time.time())
        base_record = reaper.preserve(first_row, self.out, self.archive)
        (second / 'file.txt').write_text('delta working tree\\n')
        self.age(second)
        second_row = reaper.inspect(str(second), [str(self.root)], {}, time.time())
        delta_record = reaper.preserve(second_row, self.out, self.archive)
        self.assertEqual(delta_record['base_bundle'], base_record['bundle'])
        self.assertNotEqual(delta_record['bundle'], base_record['bundle'])
        restored = self.base / 'restored-delta'
        restore_command = delta_record['restore_command'].replace(shlex.quote(str(second)), shlex.quote(str(restored)))
        subprocess.run(['bash', '-c', restore_command], text=True, capture_output=True, check=True)
        self.assertEqual((restored / 'file.txt').read_text(), 'delta working tree\\n')

    def test_operator_pause_prevents_inventory_and_removal(self):
        (self.out / 'PAUSED').write_text('operator pause\\n')
        argv = ['worktree-reaper', '--apply', '--root', str(self.root), '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), patch.object(reaper.os, 'nice'), patch.object(reaper, 'discover') as discover:
            self.assertEqual(reaper.main(), 0)
        discover.assert_not_called()
        self.assertTrue(self.repo.is_dir())
        self.assertEqual(list(self.archive.glob('*.bundle')), [])

    def test_apply_removes_old_standalone_after_bundle(self):
        self.age(self.repo)
        argv = ['worktree-reaper', '--apply', '--root', str(self.root), '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), patch.object(reaper, 'references', return_value=({}, [])), patch.object(reaper.os, 'nice'):
            self.assertEqual(reaper.main(), 0)
        self.assertFalse(self.repo.exists())
        self.assertEqual(len(list(self.archive.glob('*.bundle'))), 1)
        self.assertTrue((self.out / 'REPORT.md').is_file())

    def test_apply_archives_absorbed_submodule_before_removing_directory(self):
        source = self.base / 'submodule-source'
        self.git(self.repo, 'clone', str(self.repo), str(source))
        self.git(self.repo, '-c', 'protocol.file.allow=always', 'submodule',
                 'add', str(source), 'dependency')
        child = self.repo / 'dependency'
        self.age(child)
        argv = ['worktree-reaper', '--apply', '--root', str(child),
                '--output', str(self.out), '--archive', str(self.archive)]
        with patch.object(sys, 'argv', argv), \
                patch.object(reaper, 'references', return_value=({}, [])), \
                patch.object(reaper.os, 'nice'):
            self.assertEqual(reaper.main(), 0)
        self.assertFalse(child.exists())
        self.assertTrue(self.repo.exists())
        rows = [json.loads(line) for line in (self.out / 'manifest.jsonl').read_text().splitlines()]
        archived = next(row for row in rows if row['event'] == 'archived')
        self.assertLess(next(i for i, row in enumerate(rows) if row['event'] == 'archived'),
                        next(i for i, row in enumerate(rows) if row['event'] == 'removed'))
        restored = self.base / 'restored-submodule'
        self.git(self.repo, 'clone', archived['bundle'], str(restored))
        self.git(restored, 'checkout', archived['archive_branch'])
        self.assertEqual((restored / 'file.txt').read_text(), 'original\n')


if __name__ == '__main__':
    unittest.main()
