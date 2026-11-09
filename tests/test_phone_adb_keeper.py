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


if __name__ == '__main__':
    unittest.main()
