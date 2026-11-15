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

    def run_keep(self, connected, serial, learned):
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
