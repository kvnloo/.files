import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/private-overlay'
loader = importlib.machinery.SourceFileLoader('tern_hosts_sync', str(ROOT / 'scripts/tern-hosts-sync'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sync = importlib.util.module_from_spec(spec)
loader.exec_module(sync)

# Reserved example values only (the overlay fixture): 100.64.0.x and example.ts.net.
GROOT, MBP, S25, S22, S22_APP, COS = ('100.64.0.10', '100.64.0.11', '100.64.0.12',
                                      '100.64.0.14', '100.64.0.15', '100.64.0.20')


def peer(ip, dns, os_='linux', online=True):
    return {'TailscaleIPs': [ip], 'DNSName': dns + '.example.ts.net.', 'HostName': dns,
            'OS': os_, 'Online': online}


STATUS = {
    'Self': {'TailscaleIPs': [GROOT, 'fd7a::1']},
    'Peer': {
        'a': peer(GROOT, '0'),                        # this machine seen again: never listed
        'b': peer(MBP, 'mbp'),
        'c': peer(S22, 'localhost-0'),                 # S22 Omarchy guest
        'd': peer(S25, 'omarchy-phone'),
        'e': peer(S22_APP, 'galaxy-s22', 'android'),
        'f': peer(COS, 'cos', online=False),
        'g': peer('100.1.2.3', 'stranger'),            # online, but its key was never pinned
    },
}
NAMES = {S22: ('s22', 'root'), S25: ('s25', 'root')}


class RenderTests(unittest.TestCase):
    def test_lists_pinned_online_linux_peers_and_never_this_machine(self):
        trusted = {GROOT, MBP, S22, 'omarchy-phone'}
        body, lines, skipped = sync.render(STATUS, NAMES, trusted)
        self.assertEqual(lines, [f'root@{S22}:8376\ts22',
                                 f'kvn@{MBP}:8376\tmbp',
                                 f'root@{S25}:8376\ts25'])
        self.assertNotIn(GROOT, body.split('\n', 2)[2])
        self.assertTrue(any('stranger' in s for s in skipped))
        self.assertFalse(any('galaxy-s22' in l or 'cos' in l for l in lines))

    def test_unpinned_peer_is_skipped_not_listed(self):
        _, lines, skipped = sync.render(STATUS, NAMES, {MBP})
        self.assertEqual(lines, [f'kvn@{MBP}:8376\tmbp'])
        self.assertEqual(len(skipped), 3)


class PrivateOverlayNames(unittest.TestCase):
    def test_tracked_names_resolve_from_private_overlay(self):
        with patch.dict(os.environ, {'DOTFILES_PRIVATE_DIR': str(FIXTURE)}):
            named = sync.names(ROOT / 'config/tern/hosts.names')
        self.assertEqual(named, {GROOT: ('groot', 'kvn'), MBP: ('mbp', 'kvn'),
                                 S25: ('s25', 'root'), S22: ('s22', 'root')})
        _, lines, _ = sync.render(STATUS, named, {MBP, S22, S25})
        self.assertEqual(lines, [f'root@{S22}:8376\ts22', f'kvn@{MBP}:8376\tmbp', f'root@{S25}:8376\ts25'])

    def test_tracked_names_hold_no_literal_address(self):
        text = (ROOT / 'config/tern/hosts.names').read_text()
        for line in text.splitlines():
            if line.strip() and not line.startswith('#'):
                self.assertRegex(line.split()[0], r'^\$\{[A-Z0-9_]+\}$')

    def test_missing_private_key_fails_loudly(self):
        with tempfile.TemporaryDirectory() as empty, \
             patch.dict(os.environ, {'DOTFILES_PRIVATE_DIR': empty}):
            os.environ.pop('GROOT_TAILNET_IP', None)
            with self.assertRaises(SystemExit) as failed:
                sync.names(ROOT / 'config/tern/hosts.names')
        self.assertIn('GROOT_TAILNET_IP', str(failed.exception))

    def test_literal_names_need_no_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'hosts.names'
            path.write_text(f'{S22} s22 root\n')
            with patch.dict(os.environ, {'DOTFILES_PRIVATE_DIR': tmp}):
                self.assertEqual(sync.names(path), {S22: ('s22', 'root')})


if __name__ == '__main__':
    unittest.main()
