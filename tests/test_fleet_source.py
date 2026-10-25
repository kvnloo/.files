import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fleet_source
from fleet_source import source_files, source_snapshot
from fleet_phone_python import staging_bytes


class SourceTransferTests(unittest.TestCase):
    def git(self, source, *args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE)

    def repo(self, source):
        self.git(source, 'init', '--quiet')
        self.git(source, 'config', 'user.email', 'fixture@example.invalid')
        self.git(source, 'config', 'user.name', 'Fixture')

    def archive(self, source, includes=()):
        with source_snapshot(source, includes, directory=source.parent / 'snapshots') as (captured, metadata):
            with captured.open('rb') as stream:
                self.assertEqual(metadata['sha256'], hashlib.file_digest(stream, 'sha256').hexdigest())
            self.assertEqual(metadata['includes'], list(includes))
            with tarfile.open(captured, mode='r:gz') as archive:
                names = archive.getnames()
                self.assertTrue(all('.git' not in Path(name).parts for name in names))
                return {name: archive.extractfile(name).read() if archive.getmember(name).isfile()
                        else archive.getmember(name).linkname for name in names}

    def test_sparse_checkout_excludes_absent_and_materialized_skip_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repo(root)
            for folder in ('included', 'excluded'):
                (root / folder).mkdir()
                (root / folder / 'file').write_text(folder)
            self.git(root, 'add', '.')
            self.git(root, 'commit', '--quiet', '-m', 'fixture')
            self.git(root, 'sparse-checkout', 'init', '--cone')
            self.git(root, 'sparse-checkout', 'set', 'included')
            self.assertFalse((root / 'excluded/file').exists())
            self.assertEqual(self.archive(root), {'included/file': b'included'})
            # A populated assume-sparse entry must not leak into the snapshot.
            (root / 'manual-skip').write_text('skip')
            self.git(root, 'add', 'manual-skip')
            self.git(root, 'update-index', '--skip-worktree', 'manual-skip')
            self.assertNotIn(b'manual-skip', list(source_files(root)))

    def test_staged_and_unstaged_deletions_untracked_ignored_and_literal_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repo(root)
            for name in ('staged', 'unstaged', 'kept'):
                (root / name).write_text(name)
            (root / '.gitignore').write_text('ignored\n')
            self.git(root, 'add', '.')
            self.git(root, 'commit', '--quiet', '-m', 'fixture')
            self.git(root, 'rm', '--quiet', 'staged')
            (root / 'unstaged').unlink()
            for name in ('untracked', '-literal', 'line\nbreak', 'ignored'):
                (root / name).write_text(name)
            result = self.archive(root)
            self.assertEqual(set(result), {'.gitignore', 'kept', 'untracked', '-literal', 'line\nbreak'})
            self.assertEqual(result['line\nbreak'], b'line\nbreak')
            self.assertEqual(staging_bytes(root), sum(len(value) for value in result.values()))
            # A source subdirectory is still part of its enclosing repository.
            (root / 'nested').mkdir()
            (root / 'nested/file').write_text('nested')
            self.assertEqual(self.archive(root / 'nested'), {'file': b'nested'})

    def test_non_git_tree_honors_nested_ignore_negation_symlinks_and_git_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.gitignore').write_text('*.tmp\n!keep.tmp\n/root-only\n')
            (root / '.git').mkdir()
            (root / '.git/config').write_text('not a repository')
            (root / 'nested').mkdir()
            (root / 'nested/.gitignore').write_text('secret\n')
            for name in ('omit.tmp', 'keep.tmp', 'root-only', 'nested/root-only', 'nested/secret', 'nested/ok'):
                (root / name).write_text(name)
            (root / 'link').symlink_to('nested', target_is_directory=True)
            result = self.archive(root)
            self.assertEqual(set(result), {'.gitignore', 'keep.tmp', 'nested/.gitignore', 'nested/root-only', 'nested/ok', 'link'})
            self.assertEqual(result['link'], 'nested')
            self.assertEqual(staging_bytes(root), sum((root / os.fsdecode(name)).lstat().st_size
                                                    for name in source_files(root)))

    def test_uninitialized_gitlink_does_not_recurse_into_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repo(root)
            (root / 'kept').write_text('kept')
            self.git(root, 'add', '.')
            self.git(root, 'commit', '--quiet', '-m', 'fixture')
            commit = self.git(root, 'rev-parse', 'HEAD').decode().strip()
            self.git(root, 'update-index', '--add', '--cacheinfo', f'160000,{commit},submodule')
            (root / 'submodule').mkdir()
            self.assertEqual(self.archive(root), {'kept': b'kept'})

    def test_explicit_includes_select_paths_and_globs_and_reject_typos(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('scripts/a.py', 'scripts/nested/b.py', 'tests/test_x.py', 'tests/test_y.py', 'asset.bin'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(name)
            includes = ['scripts/', 'tests/test_x.*']
            self.assertEqual(set(self.archive(root, includes)),
                             {'scripts/a.py', 'scripts/nested/b.py', 'tests/test_x.py'})
            for invalid in ('../escape', '/absolute', 'missing*'):
                with self.subTest(pattern=invalid), self.assertRaises(ValueError):
                    self.archive(root, [invalid])

    def test_mutation_during_enumeration_cannot_ship_a_mixed_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repo(root)
            (root / 'a.py').write_text('old')
            selected = fleet_source._source_files
            changed = False
            def mutate(source):
                nonlocal changed
                for name in selected(source):
                    yield name
                    if not changed:
                        changed = True
                        (root / 'a.py').write_text('new')
                        (root / 'added.py').write_text('new import')
            with patch.object(fleet_source, '_source_files', side_effect=mutate):
                result = self.archive(root)
            self.assertEqual(result, {'a.py': b'new', 'added.py': b'new import'})

    def test_snapshot_stays_immutable_and_records_git_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repo(root)
            (root / 'a.py').write_text('committed')
            self.git(root, 'add', '.')
            self.git(root, 'commit', '--quiet', '-m', 'fixture')
            head = self.git(root, 'rev-parse', 'HEAD').decode().strip()
            (root / 'a.py').write_text('captured dirty')
            with source_snapshot(root, directory=root.parent / 'snapshots') as (archive, metadata):
                self.assertEqual(metadata['git_head'], head)
                self.assertTrue(metadata['dirty'])
                (root / 'a.py').write_text('later edit')
                with tarfile.open(archive, 'r:gz') as captured:
                    self.assertEqual(captured.extractfile('a.py').read(), b'captured dirty')

    def test_empty_non_git_tree_produces_valid_empty_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.archive(Path(directory)), {})


if __name__ == '__main__':
    unittest.main()
