import importlib.machinery, importlib.util, pathlib, unittest

path = pathlib.Path(__file__).resolve().parents[1] / 'scripts/phone-adb-keeper'
loader = importlib.machinery.SourceFileLoader('phone_adb_keeper', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
keeper = importlib.util.module_from_spec(spec)
loader.exec_module(keeper)


class AttributeTests(unittest.TestCase):
    base = {'uptime_s': 1000.0, 'adb_wifi_enabled': '1', 'bssid': 'aa', 'tcp_port': '5555'}

    def test_uptime_reset_is_reboot(self):
        self.assertEqual(keeper.attribute(self.base, {**self.base, 'uptime_s': 50.0}), 'reboot')

    def test_bssid_change_is_roam(self):
        self.assertEqual(keeper.attribute(self.base, {**self.base, 'uptime_s': 2000.0, 'bssid': 'bb'}), 'wifi-roam')

    def test_wireless_debugging_off(self):
        self.assertEqual(keeper.attribute(self.base, {**self.base, 'uptime_s': 2000.0, 'adb_wifi_enabled': '0'}),
                         'wireless-debugging-turned-off')

    def test_unknown_without_history(self):
        self.assertIsNone(keeper.attribute({}, self.base))


class EndpointTests(unittest.TestCase):
    phone = {'serial': 'X', 'hosts': ['100.72.191.23', '192.168.1.31']}

    def test_learned_lan_ip_tried_first(self):
        self.assertEqual(keeper.hosts(self.phone, {'lan_ip': '192.168.1.8'}),
                         ['192.168.1.8', '100.72.191.23', '192.168.1.31'])

    def test_no_learned_ip_keeps_fixed_hosts(self):
        self.assertEqual(keeper.hosts(self.phone, None), self.phone['hosts'])
        self.assertEqual(keeper.hosts(self.phone, {'lan_ip': '100.72.191.23'}), self.phone['hosts'])

    def test_usb_and_tls_are_not_wireless_5555(self):
        self.assertTrue(keeper.is_wireless_5555('192.168.1.8:5555'))
        for t in ('RFCTA1RZAQY', '100.117.226.39:39419', 'adb-X-a._adb-tls-connect._tcp', None):
            self.assertFalse(keeper.is_wireless_5555(t))



class RediscoveryTests(unittest.TestCase):
    """DHCP moved the S22 .8 -> .18 on 11-13; the keeper retried .8 for two days."""

    def test_stale_learned_ip_finds_phone_by_lan_sweep(self):
        connected = set()
        t, diag, actions, wireless = self.run_keep(connected, 'S22', {'lan_ip': '192.168.1.8'})
        self.assertEqual(t, '192.168.1.18:5555', actions)
        self.assertEqual(wireless, '192.168.1.18:5555')
        self.assertTrue(any(a.get('lan_sweep') for a in actions))
        self.assertEqual(connected, {'192.168.1.18:5555'})  # still attached, router dropped

    def test_other_phones_sweep_leaves_attached_s22_alone(self):
        # 11-15 08:00:24: the CAROL tablet's sweep connected .18, saw a foreign serial and
        # disconnected it, kicking the S22 the same run had just repaired.
        connected = {'192.168.1.18:5555'}
        t, diag, actions, wireless = self.run_keep(connected, 'TABLET', {'lan_ip': '192.168.1.65'})
        self.assertIsNone(t)
        self.assertIn('192.168.1.18:5555', connected)

    def test_tailnet_down_is_raised_with_connect_vpn(self):
        shell = []
        t, diag, actions, wireless = self.run_keep({'192.168.1.18:5555'}, 'S22', {'lan_ip': '192.168.1.18'}, shell)
        self.assertTrue(any('CONNECT_VPN' in c for c in shell), shell)
        self.assertTrue(any('tailscale_connect' in a for a in actions))

    def test_tailnet_up_sends_nothing(self):
        shell = []
        self.run_keep({'192.168.1.18:5555'}, 'S22', {'lan_ip': '192.168.1.18'}, shell, tun='inet 100.72.191.23/32')
        self.assertFalse(any('CONNECT_VPN' in c for c in shell), shell)

    def run_keep(self, connected, serial, learned, shell=None, tun=''):
        import subprocess
        state = {}

        def adb(*args, timeout=20):
            if args[0] == 'connect':
                host = args[1].split(':')[0]
                if host == '192.168.1.18':
                    connected.add(args[1])
                    return subprocess.CompletedProcess(args, 0, f'connected to {args[1]}', '')
                if host == '192.168.1.1':  # router: TCP 5555 open, not adb
                    connected.add(args[1])
                    return subprocess.CompletedProcess(args, 0, f'connected to {args[1]}', '')
                return subprocess.CompletedProcess(args, 1, f"failed to connect to '{args[1]}': Connection refused", '')
            if args[0] == 'disconnect':
                connected.discard(args[1])
            if 'shell' in args and shell is not None:
                shell.append(args[-1])
                return subprocess.CompletedProcess(args, 0, tun if 'addr' in args[-1] else '', '')
            return subprocess.CompletedProcess(args, 0, '', '')

        patches = {
            'adb': adb,
            'transports': lambda: {c: 'device' for c in connected},
            'serial_of': lambda t: 'S22' if t == '192.168.1.18:5555' else 'OTHER',
            'mdns_endpoints': lambda phone: [],
            'open_5555': lambda prefix: ['192.168.1.1', '192.168.1.8', '192.168.1.18'] if prefix == '192.168.1.' else [],
            'diagnostics': lambda t: {'tcp_port': '5555', 'lan_ip': t.split(':')[0]},
        }
        saved = {k: getattr(keeper, k, None) for k in patches}
        orig_sleep = keeper.time.sleep
        try:
            for k, v in patches.items():
                setattr(keeper, k, v)
            keeper.time.sleep = lambda s: None
            phone = {'serial': serial, 'hosts': ['100.72.191.23'], 'ui_lock': pathlib.Path('/dev/null')}
            return keeper.keep(serial.lower(), phone, learned)
        finally:
            for k, v in saved.items():
                setattr(keeper, k, v)
            keeper.time.sleep = orig_sleep


if __name__ == '__main__':
    unittest.main()


class WatchTests(unittest.TestCase):
    """Event-driven mode (11-18): react to `adb track-devices`, no timer."""

    def test_parse_track_block(self):
        self.assertEqual(keeper.parse_track('100.72.191.23:5555\tdevice\nX\toffline\n'),
                         {'100.72.191.23:5555': 'device', 'X': 'offline'})

    def test_drop_and_offline_are_detected_unattached_ignored(self):
        owned = {'s22': '100.72.191.23:5555', 'carol-tablet': '100.94.207.126:5555', 's25': None}
        current = {'100.72.191.23:5555': 'offline'}
        self.assertEqual(sorted(keeper.dropped(owned, current)), ['carol-tablet', 's22'])
        self.assertEqual(keeper.dropped(owned, {'100.72.191.23:5555': 'device',
                                                '100.94.207.126:5555': 'device'}), [])

    def test_backoff_caps_at_ten_minutes(self):
        self.assertEqual([keeper.next_delay(n) for n in range(6)], [5, 30, 120, 600, 600, 600])

    def test_track_wire_format_split_reads(self):
        import io

        class Trickle(io.RawIOBase):  # pipe that returns one byte per read, like a slow socket
            def __init__(self, data):
                self.data = data
            def readable(self):
                return True
            def readinto(self, b):
                if not self.data:
                    return 0
                b[0], self.data = self.data[0], self.data[1:]
                return 1
        body = b'S\tdevice\n'
        blocks = list(keeper.read_track_blocks(Trickle(b'%04x' % len(body) + body + b'0000')))
        self.assertEqual(blocks, ['S\tdevice\n', ''])

    def test_s25_is_kept_but_never_required(self):
        # Kevin turns S25 debugging off for banking apps; that must not alarm.
        self.assertEqual(keeper.PHONES['s25']['serial'], 'R5CY93G2WNH')
        self.assertFalse(keeper.PHONES['s25']['required'])
        self.assertTrue(keeper.PHONES['s22'].get('required', True))
