import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/release-live'


class ReleaseLiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / 'repo'
        self.home = base / 'home'
        self.repo.mkdir()
        self.home.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.sources = {'config/unit.service': b'live unit\n', 'scripts/helper': b'live helper\n'}
        self.paths = ['.config/systemd/user/unit.service', '.local/bin/helper']
        for source, data in self.sources.items():
            path = self.repo / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.repo / 'fleet.toml').write_text(
            '[hosts.fixture]\nmatch_hostnames=[' + json.dumps(socket.gethostname()) +
            ']\nmanifest="config/host/fixture.toml"\n'
            '[hosts.fixture.storage]\nrelease_root="/must-not-use-fixture-storage"\n')
        self.manifest = self.repo / 'config/host/fixture.toml'
        self.manifest.parent.mkdir()
        self.manifest.write_text(''.join(
            f'[[user]]\nlive="~/{live}"\nsource="{source}"\n'
            f'install="symlink-stamped"\nowner="owner-{i}"\n'
            for i, (live, source) in enumerate(zip(self.paths, self.sources))) +
            '[[user]]\nlive="~/.ignored"\nsource="missing-copy"\ninstall="copy"\n'
            '[[system]]\nlive="/ignored"\nsource="missing-system"\ninstall="symlink-stamped"\n')
        self.sha = self.commit()
        self.git('update-ref', 'refs/heads/live', self.sha)
        for live, source in zip(self.paths, self.sources):
            path = self.home / live
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.sources[source])
        self.library = self.home / '.local/lib/files-live'
        self.receipt = self.home / '.local/state/files-live/releases.jsonl'
        self.bin = base / 'bin'
        self.bin.mkdir()
        systemctl = self.bin / 'systemctl'
        systemctl.write_text('#!/bin/sh\necho "fixture must not call systemctl" >&2\nexit 99\n')
        systemctl.chmod(0o755)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def run_cli(self, *args, code=0):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--repo', str(self.repo),
                                 '--home', str(self.home), *args], capture_output=True, text=True,
                                env={**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH']})
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def snapshot(self):
        return {str(path.relative_to(self.home)):
                ('link', os.readlink(path)) if path.is_symlink() else
                ('dir',) if path.is_dir() else ('file', path.read_bytes())
                for path in self.home.rglob('*')}

    def advance(self):
        (self.repo / 'config/unit.service').write_bytes(b'second release\n')
        sha = self.commit()
        self.git('update-ref', 'refs/heads/live', sha)
        return sha

    def test_live_archive_ignores_head_worktree_and_uses_all_manifest_owners(self):
        (self.repo / 'config/unit.service').write_bytes(b'HEAD bytes\n')
        self.manifest.write_text('invalid HEAD manifest')
        self.commit()
        (self.repo / 'config/unit.service').write_bytes(b'working tree bytes\n')
        (self.repo / 'fleet.toml').write_text('invalid working tree fleet')
        result = self.run_cli('--apply', '--ref', 'HEAD')
        self.assertEqual(result['sha'], self.sha)
        self.assertEqual(result['links'], 2)
        self.assertEqual(result['relinked'], 2)
        release = self.library / self.sha
        self.assertEqual((self.library / 'current').resolve(), release)
        for live, source in zip(self.paths, self.sources):
            path = self.home / live
            self.assertEqual(os.readlink(path), str(self.library / 'current' / source))
            self.assertEqual(path.resolve(), release / source)
            self.assertEqual(path.read_bytes(), self.sources[source])
        self.assertEqual(json.loads((release / '.deployment-stamp.json').read_text()), {
            'name': 'files-live', 'source_sha': self.sha,
            'source_ref': 'refs/heads/live', 'source_repo': str(self.repo)})
        self.assertEqual(json.loads((release / 'tracked-files.json').read_text()),
                         self.git('ls-tree', '-r', '--name-only', self.sha).splitlines())
        backups = list((self.home / '.local/state/files-live/backups').iterdir())
        self.assertEqual(len(backups), 1)
        for live, source in zip(self.paths, self.sources):
            self.assertEqual((backups[0] / live).read_bytes(), self.sources[source])

    def test_plan_is_read_only_and_honors_ref(self):
        before = self.snapshot()
        result = self.run_cli('--plan')
        self.assertEqual(result['content_changes'], [])
        self.assertEqual(self.snapshot(), before)
        (self.repo / 'config/unit.service').write_bytes(b'candidate\n')
        candidate = self.commit()
        # Changed symlinks can be migrated; changed regular files cannot.
        live = self.home / self.paths[0]
        live.unlink()
        live.symlink_to(self.home / self.paths[1])
        before = self.snapshot()
        result = self.run_cli('--plan', '--ref', 'HEAD', code=5)
        self.assertEqual(result['sha'], candidate)
        self.assertEqual(result['content_changes'], [str(live)])
        self.assertEqual(self.snapshot(), before)

    def test_second_release_keeps_links_and_rollback_restores_bytes(self):
        self.run_cli('--apply')
        inodes = [(self.home / path).lstat().st_ino for path in self.paths]
        second = self.advance()
        result = self.run_cli('--apply')
        self.assertEqual(result['sha'], second)
        self.assertEqual(result['relinked'], 0)
        self.assertEqual(result['content_changes'], 1)
        self.assertEqual((self.library / 'previous').resolve(), self.library / self.sha)
        self.assertEqual(inodes, [(self.home / path).lstat().st_ino for path in self.paths])
        receipts = [json.loads(line) for line in self.receipt.read_text().splitlines()]
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[-1], result)
        result = self.run_cli('--rollback', '--ref', 'does-not-exist')
        self.assertEqual(result['status'], 'rollback')
        self.assertEqual(result['sha'], self.sha)
        self.assertEqual((self.library / 'current').resolve(), self.library / self.sha)
        self.assertEqual((self.library / 'previous').resolve(), self.library / second)
        self.assertEqual((self.home / self.paths[0]).read_bytes(), self.sources['config/unit.service'])
        self.assertEqual(len(self.receipt.read_text().splitlines()), 3)

    def test_missing_live_ignores_apply_ref(self):
        self.git('update-ref', '-d', 'refs/heads/live')
        before = self.snapshot()
        result = self.run_cli('--apply', '--ref', 'HEAD', '--accept-changes', code=3)
        self.assertEqual(result['status'], 'missing_live')
        self.assertEqual(self.snapshot(), before)
        self.run_cli('--plan', '--ref', 'HEAD')

    def test_first_cut_changed_symlink_requires_acceptance_and_is_backed_up(self):
        live = self.home / self.paths[0]
        live.unlink()
        live.symlink_to(self.home / self.paths[1])
        old_target = os.readlink(live)
        before = self.snapshot()
        self.run_cli('--apply', code=5)
        self.assertEqual(self.snapshot(), before)
        result = self.run_cli('--apply', '--accept-changes')
        self.assertEqual(result['content_changes'], 1)
        backup = next((self.home / '.local/state/files-live/backups').iterdir()) / self.paths[0]
        self.assertTrue(backup.is_symlink())
        self.assertEqual(os.readlink(backup), old_target)

    def test_missing_live_path_counts_as_content_change(self):
        (self.home / self.paths[0]).unlink()
        self.run_cli('--plan', code=5)
        self.run_cli('--apply', code=5)
        self.run_cli('--apply', '--accept-changes')

    def test_missing_source_writes_nothing(self):
        (self.repo / 'scripts/helper').unlink()
        self.git('update-ref', 'refs/heads/live', self.commit())
        before = self.snapshot()
        for mode in ('--plan', '--apply'):
            self.run_cli(mode, '--accept-changes', code=4)
            self.assertEqual(self.snapshot(), before)

    def test_changed_regular_file_refuses_even_with_acceptance(self):
        (self.home / self.paths[1]).write_bytes(b'local edits\n')
        before = self.snapshot()
        for mode in ('--plan', '--apply'):
            self.run_cli(mode, '--accept-changes', code=4)
            self.assertEqual(self.snapshot(), before)

    def test_repeat_apply_has_one_receipt_and_no_link_rewrites(self):
        self.run_cli('--apply')
        result = self.run_cli('--apply')
        self.assertEqual(result['relinked'], 0)
        self.assertEqual(result['content_changes'], 0)
        self.assertEqual(len(self.receipt.read_text().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
