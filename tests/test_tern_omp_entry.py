import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('tern_omp_entry', str(ROOT / 'scripts/install-tern-omp'))
spec = importlib.util.spec_from_loader(loader.name, loader)
entry = importlib.util.module_from_spec(spec)
loader.exec_module(entry)


class TernOmpEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.tern = self.home / '.local/share/tern'
        self.wrapper = ROOT / 'scripts/omp'
        self.payload = self.stage(self.tern, '1.0.0', b'#!/bin/sh\nprintf old\n')
        live = self.tern / 'omp/bin/omp'
        live.parent.mkdir(parents=True)
        live.symlink_to(self.payload)
        settings = self.home / '.config/tern/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{"font_size":17}\n')

    def stage(self, tern, version, data):
        payload = tern / 'omp/versions' / version
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(data)
        payload.chmod(0o755)
        (tern / 'omp/state.json').write_text(json.dumps({
            'managed': True, 'checked': 42,
            'installed': {'version': version, 'sha256': hashlib.sha256(data).hexdigest(), 'via': {'how': 'build'}}}))
        return payload

    def install(self, tern=None):
        return entry.import_release(self.home, tern or self.tern, self.wrapper, True)

    def test_host_drift_manifest_owns_both_entry_points(self):
        manifest = tomllib.loads((ROOT / 'config/host/groot.toml').read_text())
        rows = {row['live']: row for row in manifest['user']}
        for live, source in {
            '~/.local/bin/omp': 'scripts/omp',
            '~/.local/share/tern/omp/bin/omp': 'scripts/omp',
            '~/.local/bin/install-tern-omp': 'scripts/install-tern-omp',
        }.items():
            self.assertEqual(rows[live]['source'], source)
            self.assertEqual(rows[live]['install'], 'symlink-stamped')


    def test_legacy_absolute_and_shell_entries_share_scoped_wrapper(self):
        original_inode = self.payload.stat().st_ino
        release = self.install()
        for path in (self.home / '.local/bin/omp', self.tern / 'omp/bin/omp'):
            self.assertEqual(path.resolve(), self.wrapper.resolve())
        self.assertEqual((release / 'omp').read_bytes(), self.payload.read_bytes())
        self.assertEqual(self.payload.stat().st_ino, original_inode)
        state = json.loads((self.tern / 'omp/state.json').read_text())
        self.assertFalse(state['managed'])
        self.assertEqual(state['checked'], 42)
        settings = json.loads((self.home / '.config/tern/settings.json').read_text())
        self.assertEqual(settings['font_size'], 17)
        self.assertEqual(settings['agent_command'], str(self.home / '.local/bin/omp'))
        self.assertEqual(json.loads((release.parent / 'manager.json').read_text())['manager'], 'files')

    def test_upgrade_import_never_exposes_raw_binary_at_live_entry(self):
        old = self.install()
        staging = Path(self.tmp.name) / 'staging'
        payload = self.stage(staging, '2.0.0', b'#!/bin/sh\nprintf upgraded\n')
        new = self.install(staging)
        self.assertNotEqual(old, new)
        self.assertEqual((old / 'omp').read_bytes(), self.payload.read_bytes())
        self.assertEqual((new / 'omp').read_bytes(), payload.read_bytes())
        self.assertEqual((self.tern / 'omp/bin/omp').resolve(), self.wrapper.resolve())
        self.assertEqual((self.home / '.local/lib/files-tern-omp/current').resolve(), new)
        self.assertEqual(self.install(), new)

    def test_checksum_rejection_leaves_live_entries_unchanged(self):
        self.payload.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.install()
        self.assertEqual((self.tern / 'omp/bin/omp').resolve(), self.payload)
        self.assertFalse((self.home / '.local/lib/files-tern-omp/current').exists())

    def test_dry_run_and_exact_one_command_rollback(self):
        state = (self.tern / 'omp/state.json').read_bytes()
        entry.import_release(self.home, self.tern, self.wrapper, False)
        self.assertFalse((self.home / '.local/lib/files-tern-omp/current').exists())
        self.install()
        subprocess.run(['python3', str(ROOT / 'scripts/install-tern-omp'), '--home', str(self.home), '--rollback'], check=True)
        self.assertEqual((self.tern / 'omp/bin/omp').resolve(), self.payload)
        self.assertEqual((self.tern / 'omp/state.json').read_bytes(), state)
        self.assertEqual((self.home / '.config/tern/settings.json').read_text(), '{"font_size":17}\n')
        self.assertFalse(os.path.lexists(self.home / '.local/bin/omp'))

    def test_wrapper_passes_restore_arguments_to_agent_launch(self):
        self.install()
        launcher = self.home / '.local/bin/agent-launch'
        launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        launcher.chmod(0o755)
        result = subprocess.check_output([str(self.tern / 'omp/bin/omp'), '--restore', '/session with spaces.jsonl'], env={**os.environ, 'HOME': str(self.home)}, text=True)
        self.assertEqual(result.splitlines(), ['omp', str(self.home / '.local/lib/files-tern-omp/current/omp'), '--restore', '/session with spaces.jsonl'])

    def test_update_command_explains_supported_staging_import_without_replacing_entry(self):
        self.install()
        legacy = self.tern / 'omp/bin/omp'
        before = os.readlink(legacy)
        result = subprocess.check_output([str(legacy), 'update'], env={**os.environ, 'HOME': str(self.home)}, text=True)
        self.assertIn('install-tern-omp --apply --from-tern', result)
        self.assertEqual(os.readlink(legacy), before)


if __name__ == '__main__':
    unittest.main()
