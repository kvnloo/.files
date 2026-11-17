"""hermes-keyring-bootstrap must not open a Secret Service client on every call.

Short-lived clients racing a property Get abort gnome-keyring-daemon (2026-11-16, 2026-11-17),
so the sealed TPM copy serves normal calls and the keyring is read at most once per refresh.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts/hermes-keyring-bootstrap.sh'
STUBS = {
    'busctl': 'echo busctl >> "$LOG"; echo "b $LOCKED"',
    'secret-tool': 'echo secret-tool >> "$LOG"; echo keyring-fixture',
    # encrypt: copy stdin to the output file; decrypt: print the file.
    'systemd-creds': 'echo "systemd-creds $2" >> "$LOG"; '
                     'if [ "$2" = encrypt ]; then cat > "$5"; else cat "$4"; fi',
}


class KeyringBootstrap(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / 'bin').mkdir()
        for name, body in STUBS.items():
            path = self.dir / 'bin' / name
            path.write_text('#!/bin/sh\n' + body + '\n')
            path.chmod(0o755)
        self.log = self.dir / 'log'
        self.cred = self.dir / 'cfg/bws.cred'

    def run_once(self, locked='false', **extra):
        env = dict(os.environ, PATH=f"{self.dir / 'bin'}:{os.environ['PATH']}", LOG=str(self.log),
                   LOCKED=locked, HERMES_BWS_CRED=str(self.cred), XDG_RUNTIME_DIR=str(self.dir), **extra)
        out = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, check=True)
        return out.stdout

    def keyring_calls(self):
        return sum(line in ('busctl', 'secret-tool') for line in self.log.read_text().splitlines())

    def test_keyring_read_once_then_sealed_copy(self):
        self.assertIn('BWS_ACCESS_TOKEN=', self.run_once())
        self.assertEqual(self.keyring_calls(), 2)
        for _ in range(5):
            self.assertIn("BWS_ACCESS_TOKEN='keyring-fixture'", self.run_once())
        self.assertEqual(self.keyring_calls(), 2)

    def test_refresh_after_interval(self):
        self.run_once()
        os.utime(str(self.cred) + '.keyring-checked', (0, 0))
        self.run_once()
        self.assertEqual(self.keyring_calls(), 4)

    def test_locked_keyring_is_not_reprobed_every_call(self):
        self.cred.parent.mkdir()
        self.cred.write_text('sealed-fixture')
        self.assertIn('sealed-fixture', self.run_once(locked='true'))
        self.assertIn('sealed-fixture', self.run_once(locked='true'))
        self.assertEqual(self.keyring_calls(), 1)

    def test_missing_sealed_copy_falls_back_to_keyring(self):
        (self.dir / 'cfg').mkdir()
        Path(str(self.cred) + '.keyring-checked').touch()
        self.assertIn('keyring-fixture', self.run_once())
        self.assertTrue(self.cred.exists())


if __name__ == '__main__':
    unittest.main()
