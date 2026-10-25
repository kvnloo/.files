import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('tern_hosts_sync', str(ROOT / 'scripts/tern-hosts-sync'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sync = importlib.util.module_from_spec(spec)
loader.exec_module(sync)


def peer(ip, dns, os_='linux', online=True):
    return {'TailscaleIPs': [ip], 'DNSName': dns + '.taila30dc.ts.net.', 'HostName': dns,
            'OS': os_, 'Online': online}


STATUS = {
    'Self': {'TailscaleIPs': ['100.113.138.100', 'fd7a::1']},
    'Peer': {
        'a': peer('100.113.138.100', '0'),            # this machine seen again: never listed
        'b': peer('100.78.215.21', 'mbp'),
        'c': peer('100.97.11.22', 'localhost-0'),      # S22 Omarchy guest
        'd': peer('100.104.42.85', 'omarchy-phone'),
        'e': peer('100.72.191.23', 'galaxy-s22', 'android'),
        'f': peer('100.65.79.99', 'cos', online=False),
        'g': peer('100.1.2.3', 'stranger'),            # online, but its key was never pinned
    },
}
NAMES = {'100.97.11.22': ('s22', 'root'), '100.104.42.85': ('s25', 'root')}


class RenderTests(unittest.TestCase):
    def test_lists_pinned_online_linux_peers_and_never_this_machine(self):
        trusted = {'100.113.138.100', '100.78.215.21', '100.97.11.22', 'omarchy-phone'}
        body, lines, skipped = sync.render(STATUS, NAMES, trusted)
        self.assertEqual(lines, ['root@100.97.11.22:8376\ts22',
                                 'kvn@100.78.215.21:8376\tmbp',
                                 'root@100.104.42.85:8376\ts25'])
        self.assertNotIn('100.113.138.100', body.split('\n', 2)[2])
        self.assertTrue(any('stranger' in s for s in skipped))
        self.assertFalse(any('galaxy-s22' in l or 'cos' in l for l in lines))

    def test_unpinned_peer_is_skipped_not_listed(self):
        _, lines, skipped = sync.render(STATUS, NAMES, {'100.78.215.21'})
        self.assertEqual(lines, ['kvn@100.78.215.21:8376\tmbp'])
        self.assertEqual(len(skipped), 3)


if __name__ == '__main__':
    unittest.main()
