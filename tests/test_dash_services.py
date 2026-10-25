"""Executable installer and parsed systemd/environment contracts."""
import configparser
import importlib.machinery
import importlib.util
from pathlib import Path
import shlex
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('dash_install', str(ROOT / 'scripts/install-dash-services'))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

def unit(name):
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / f'config/systemd/user/dash-{name}.service')
    return config

def environment(name):
    return dict(line.split('=', 1) for line in shlex.split((ROOT / f'config/dash-services/{name}.env').read_text()))

class DashServices(unittest.TestCase):
    def test_atomic_link_replaces_previous_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, new = root / 'old', root / 'new'
            old.mkdir()
            new.mkdir()
            target = root / 'nested/current'
            module.link(old, target)
            module.link(new, target)
            self.assertEqual(target.resolve(), new)
            self.assertFalse(target.with_name('current.dash-new').exists())

    def test_unit_semantics(self):
        for name in ('bridge', 'metro', 'metro-relay'):
            config = unit(name)
            self.assertEqual(config['Install']['WantedBy'], 'default.target')
            self.assertEqual(config['Service']['Restart'], 'on-failure')
            self.assertEqual(config['Service']['RestartSec'], '10')
            self.assertEqual(config['Unit']['StartLimitIntervalSec'], '0')
            self.assertTrue(config['Service']['ExecStartPre'].endswith('/dash-wait-tailnet'))
            self.assertNotIn('MemoryHigh', config['Service'])
            self.assertIn('MemoryMax', config['Service'])
        self.assertEqual(unit('bridge')['Service']['OOMPolicy'], 'continue')
        self.assertEqual(unit('metro')['Service']['OOMPolicy'], 'continue')

    def test_environment_is_explicit_nonsecret_configuration(self):
        self.assertEqual(set(environment('bridge')), {'DASH_HOST','DASH_PORT','DASH_CWD','DASH_EXPO_GO_URL','HERMES_HOME','PATH'})
        self.assertEqual(set(environment('metro')), {'CI','EXPO_PUBLIC_DASH_TURBO','REACT_NATIVE_PACKAGER_HOSTNAME','EXPO_NO_TELEMETRY','EXPO_PACKAGER_PROXY_URL','PATH'})
        self.assertEqual(environment('bridge')['DASH_HOST'], '100.113.138.100')

    def test_metro_loopback_and_tailnet_manifest_contract(self):
        command = shlex.split(unit('metro')['Service']['ExecStart'])
        self.assertIn('--localhost', command)
        self.assertEqual(command[command.index('--port') + 1], '18212')
        self.assertEqual(environment('metro')['EXPO_PACKAGER_PROXY_URL'], 'http://100.113.138.100:8212')

if __name__ == '__main__':
    unittest.main()
