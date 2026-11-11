"""install-host-storage.sh refuses to replace a release the new commit does not contain
(2026-11-09: a dev release silently dropped a hot-fix copy of fleet with three unmerged fixes)."""
import os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = Path('/mnt/zer0models/releases')
PASSED = 99  # the stubbed mkdir: the script got past the guard and would start staging


@unittest.skipUnless(RELEASES.is_dir(), 'needs the release root the script checks for')
class ReplaceGuard(unittest.TestCase):
    def activate(self, release=None, **env):
        with tempfile.TemporaryDirectory() as tmp:
            home, stubs = Path(tmp, 'home'), Path(tmp, 'stubs')
            (home / '.local/bin').mkdir(parents=True); stubs.mkdir()
            for name, body in (('hostname', 'echo groot'), ('id', 'echo kvn'), ('mountpoint', 'exit 0'),
                               ('flock', 'exit 0'), ('mkdir', f'exit {PASSED}')):
                (stubs / name).write_text('#!/bin/sh\n' + body + '\n'); (stubs / name).chmod(0o755)
            if release:
                (home / '.local/bin/fleet').symlink_to(RELEASES / release / 'scripts/fleet')
            return subprocess.run(['bash', str(ROOT / 'scripts/install-host-storage.sh'), '--activate'], capture_output=True, text=True,
                                  env={'HOME': str(home), 'PATH': f"{stubs}:{os.environ['PATH']}", **env})

    def test_first_install_and_contained_release_pass(self):
        parent = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD~1'], capture_output=True, text=True).stdout.strip()
        self.assertEqual(self.activate().returncode, PASSED)
        self.assertEqual(self.activate('host-storage/' + parent).returncode, PASSED)

    def test_uncontained_release_is_refused_until_named(self):
        hotfix = 'fh-3e38061a-cc6b00ff-38918116-on-1611c2a1'
        refused = self.activate('files-live/' + hotfix)
        self.assertEqual(refused.returncode, 1)
        self.assertIn('HOST_STORAGE_REPLACES=' + hotfix, refused.stderr)
        self.assertEqual(self.activate('files-live/' + hotfix, HOST_STORAGE_REPLACES=hotfix).returncode, PASSED)


if __name__ == '__main__':
    unittest.main()
