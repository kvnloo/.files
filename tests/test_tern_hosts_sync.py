import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/tern-hosts-sync'
loader = importlib.machinery.SourceFileLoader('tern_hosts_sync', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
sync = importlib.util.module_from_spec(spec)
loader.exec_module(sync)

# Documentation addresses (RFC 5737) and an example tailnet: no real fleet values in this public repo.
SELF, MBP, S22, S25, PHONE_APP, OFF, STRANGER = (f'192.0.2.{n}' for n in (1, 2, 3, 4, 5, 6, 7))


def peer(ip, dns, os_='linux', online=True, host=None):
    return {'TailscaleIPs': [ip], 'DNSName': dns + '.tailnet.example.', 'HostName': host or dns,
            'OS': os_, 'Online': online}


STATUS = {
    'Self': {'TailscaleIPs': [SELF, 'fd7a::1']},
    'Peer': {
        'a': peer(SELF, '0', host='groot'),            # this machine seen again: never listed
        'b': peer(MBP, 'mbp'),
        'c': peer(S22, 'localhost-0', host='localhost'),  # S22 Omarchy guest
        'd': peer(S25, 'omarchy-phone'),
        'e': peer(PHONE_APP, 'galaxy-s22', 'android'),
        'f': peer(OFF, 'cos', online=False),
        'g': peer(STRANGER, 'stranger'),               # online, but its key was never pinned
    },
}
NAMES = {S22: ('s22', 'root'), S25: ('s25', 'root')}

DEVICES_TOML = '''
[groot]
kind = "node"
peer_hostname = "groot"
aliases = ["0"]

[mbp]
kind = "node"
peer_hostname = "mbp"

[omarchy-phone]
kind = "phone"
peer_hostname = "omarchy-phone"
aliases = ["s25"]

[galaxy-s22plus]
kind = "phone"
peer_hostname = "localhost"
aliases = ["s22", "localhost-0"]
'''


class RenderTests(unittest.TestCase):
    def test_lists_pinned_online_linux_peers_and_never_this_machine(self):
        trusted = {SELF, MBP, S22, 'omarchy-phone'}
        body, lines, skipped = sync.render(STATUS, NAMES, trusted)
        self.assertEqual(lines, [f'root@{S22}:8376\ts22', f'kvn@{MBP}:8376\tmbp', f'root@{S25}:8376\ts25'])
        self.assertNotIn(SELF, body.split('\n', 2)[2])
        self.assertTrue(any('stranger' in s for s in skipped))
        self.assertFalse(any('galaxy-s22' in l or 'cos' in l for l in lines))

    def test_unpinned_peer_is_skipped_not_listed(self):
        _, lines, skipped = sync.render(STATUS, NAMES, {MBP})
        self.assertEqual(lines, [f'kvn@{MBP}:8376\tmbp'])
        self.assertEqual(len(skipped), 3)


class DevicesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name) / 'hosts/groot'
        d.mkdir(parents=True)
        (d / 'devices.toml').write_text(DEVICES_TOML)
        self.devs = sync.devices(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_names_come_from_private_devices_without_any_address(self):
        self.assertEqual(self.devs['0'], ('groot', 'kvn'))
        self.assertEqual(self.devs['localhost-0'], ('s22', 'root'))
        self.assertEqual(self.devs['omarchy-phone'], ('s25', 'root'))

    def test_render_uses_devices_when_no_local_names_file(self):
        status = {'Self': {'TailscaleIPs': [MBP]}, 'Peer': dict(STATUS['Peer'])}
        status['Peer']['b'] = peer(MBP, 'mbp')
        _, lines, _ = sync.render(status, {}, {SELF, S22, S25}, self.devs)
        self.assertEqual(lines, [f'kvn@{SELF}:8376\tgroot', f'root@{S22}:8376\ts22', f'root@{S25}:8376\ts25'])

    def test_missing_instance_is_empty(self):
        self.assertEqual(sync.devices(Path(self.tmp.name) / 'absent'), {})


class CliTests(unittest.TestCase):
    def test_unknown_argument_never_syncs(self):
        r = subprocess.run([sys.executable, str(SCRIPT), '--bogus'], capture_output=True, text=True,
                           env={'PATH': '/nonexistent', 'HOME': '/nonexistent'})
        self.assertEqual(r.returncode, 2)
        self.assertIn('tern-hosts-sync --dry-run', r.stderr)

    def test_help_exits_zero_without_tailscale(self):
        r = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True,
                           env={'PATH': '/nonexistent', 'HOME': '/nonexistent'})
        self.assertEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
