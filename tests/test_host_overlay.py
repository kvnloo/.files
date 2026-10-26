"""scripts/host_overlay.py: a fixture z0-hosts instance (template layout) and an absent one.

All values are fake. Leak samples are assembled at runtime so this file scans clean.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import host_overlay  # noqa: E402

FLEET = '''
[hosts.desktop]
match_hostnames = ["box"]
manifest = "config/host/box.toml"

[hosts.laptop]
match_hostnames = ["lap"]
manifest = "config/host/lap.toml"
'''
TS_IP = '.'.join(['100', '101', '2', '3'])


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / 'dotfiles'
        self.root.mkdir()
        (self.root / 'fleet.toml').write_text(FLEET)
        self.instance = self.tmp / 'z0-hosts'
        self.env = {'Z0_HOSTS_DIR': str(self.instance)}
        self.home = self.tmp / 'home'

    def host(self, name, host_toml, files_toml=None):
        d = self.instance / 'hosts' / name
        d.mkdir(parents=True)
        (d / 'host.toml').write_text(host_toml)
        if files_toml is not None:
            (d / 'files.toml').write_text(files_toml)
        return d

    def resolve(self, hostname='box', env=None):
        return host_overlay.resolve(self.root, hostname=hostname, home=self.home,
                                    env=self.env if env is None else env)


class AbsentInstance(Fixture):
    def test_no_instance_gives_neutral_defaults(self):
        overlay = self.resolve()
        self.assertEqual(overlay.fleet_host, 'desktop')
        self.assertIsNone(overlay.overlay_id)
        self.assertIsNone(overlay.source)
        self.assertEqual(overlay.storage, host_overlay.DEFAULTS['storage'])
        self.assertEqual(overlay.services, {})
        self.assertEqual(overlay.path('workspace_root', self.home), self.home / 'workspace')
        self.assertIsNone(overlay.path('release_root', self.home))
        self.assertIsNone(overlay.port('dash', 'bridge_port'))

    def test_default_dir_is_config_z0_hosts(self):
        self.assertEqual(host_overlay.hosts_dir({}), Path('~/.config/z0-hosts').expanduser())

    def test_instance_without_this_host_gives_defaults(self):
        self.host('other', 'match_hostnames = ["elsewhere"]\n', '[storage]\nmodel_root = "/srv/x"\n')
        overlay = self.resolve()
        self.assertIsNone(overlay.overlay_id)
        self.assertEqual(overlay.storage['model_root'], '~/.local/share/z0')

    def test_host_dir_without_files_toml_gives_defaults(self):
        self.host('desktop', 'match_hostnames = ["box"]\n')
        overlay = self.resolve()
        self.assertEqual(overlay.overlay_id, 'desktop')
        self.assertIsNone(overlay.source)
        self.assertEqual(overlay.storage, host_overlay.DEFAULTS['storage'])

    def test_unknown_fleet_host_still_fails_closed(self):
        with self.assertRaises(ValueError):
            self.resolve(hostname='stranger')


class TemplateInstance(Fixture):
    FILES = '''
[storage]
model_root = "/srv/models"
workspace_root = "~/work"
release_root = "/srv/models/releases"

[services.dash]
bridge_port = 4747
metro_port = 0

[services.ollama]
port = 11434

[k3s]
control_plane = "desktop"
'''

    def test_reads_files_toml_by_fleet_host_key(self):
        self.host('workstation', 'match_hostnames = ["nope"]\nfleet_host = "desktop"\n', self.FILES)
        overlay = self.resolve()
        self.assertEqual(overlay.overlay_id, 'workstation')
        self.assertEqual(overlay.path('model_root'), Path('/srv/models'))
        self.assertEqual(overlay.path('workspace_root', self.home), self.home / 'work')
        self.assertEqual(overlay.storage['offload_root'], '')  # untouched default
        self.assertEqual(overlay.port('dash', 'bridge_port'), 4747)
        self.assertIsNone(overlay.port('dash', 'metro_port'))  # 0 = not installed
        self.assertEqual(overlay.port('ollama'), 11434)
        self.assertEqual(overlay.k3s['control_plane'], 'desktop')
        self.assertEqual(overlay.ignored, ())

    def test_reads_by_directory_name_and_by_hostname(self):
        self.host('desktop', '', self.FILES)
        self.assertEqual(self.resolve().overlay_id, 'desktop')

    def test_match_hostnames(self):
        self.host('lap-dir', 'match_hostnames = ["lap"]\n', '[storage]\nmodel_root = "/data"\n')
        overlay = self.resolve(hostname='lap')
        self.assertEqual((overlay.fleet_host, overlay.overlay_id), ('laptop', 'lap-dir'))
        self.assertEqual(overlay.storage['model_root'], '/data')

    def test_z0_host_id_overrides(self):
        self.host('desktop', '', self.FILES)
        self.host('spare', '', '[storage]\nmodel_root = "/spare"\n')
        overlay = self.resolve(env={**self.env, 'Z0_HOST_ID': 'spare'})
        self.assertEqual(overlay.storage['model_root'], '/spare')

    def test_z0_host_id_cannot_leave_hosts_dir(self):
        self.host('desktop', '', self.FILES)
        for bad in ('../desktop', '/etc', 'a/b', '.'):
            with self.assertRaisesRegex(ValueError, 'Z0_HOST_ID'):
                self.resolve(env={**self.env, 'Z0_HOST_ID': bad})

    def test_ambiguous_match_fails_closed(self):
        self.host('desktop', '', self.FILES)
        self.host('twin', 'fleet_host = "desktop"\n', self.FILES)
        with self.assertRaisesRegex(ValueError, 'more than one'):
            self.resolve()

    def test_address_keys_are_never_read(self):
        self.host('desktop', '', '[storage]\nmodel_root = "/srv/m"\nnas_ip = "x"\n'
                                 '[services.dash]\nbridge_port = 4747\nbind_addr = 1\n'
                                 '[services.tailnet_proxy]\nport = 1\n')
        overlay = self.resolve()
        self.assertNotIn('nas_ip', overlay.storage)
        self.assertEqual(overlay.services, {'dash': {'bridge_port': 4747}})
        self.assertEqual(set(overlay.ignored),
                         {'storage.nas_ip', 'services.dash.bind_addr', 'services.tailnet_proxy'})

    def test_tailnet_value_is_refused(self):
        self.host('desktop', '', f'[storage]\nmodel_root = "/x/{TS_IP}"\n')
        with self.assertRaisesRegex(ValueError, 'tailnet'):
            self.resolve()

    def test_bad_ports_and_unknown_keys_ignored(self):
        self.host('desktop', '', '[storage]\nmystery = "/x"\n[services.a]\nport = 70000\nweb = true\n'
                                 '[extra]\nk = 1\n')
        overlay = self.resolve()
        self.assertEqual(overlay.services, {})
        self.assertEqual(set(overlay.ignored),
                         {'storage.mystery', 'services.a.port', 'services.a.web', '<top>.extra'})


class Cli(Fixture):
    def run_cli(self, *args, env):
        # The CLI resolves the real fleet.toml; pin the host with a fleet hostname.
        code = ('import sys, host_overlay, host_layout\n'
                'real = host_layout.resolve\n'
                'host_layout.resolve = lambda root, hostname=None, home=None: real(root, "mbp", home)\n'
                'sys.exit(host_overlay.main(sys.argv[1:]))\n')
        return subprocess.run([sys.executable, '-c', code, *args], cwd=ROOT / 'scripts',
                              capture_output=True, text=True, env={'PATH': '/usr/bin:/bin', **env})

    def test_get_and_defaults(self):
        self.host('mbp', '', '[storage]\nmodel_root = "/srv/models"\n[services.dash]\nbridge_port = 4747\n')
        self.assertEqual(self.run_cli('get', 'storage.model_root', env=self.env).stdout.strip(), '/srv/models')
        self.assertEqual(self.run_cli('get', 'services.dash.bridge_port', env=self.env).stdout.strip(), '4747')
        unset = self.run_cli('get', 'storage.swapfile', env=self.env)
        self.assertEqual((unset.returncode, unset.stdout), (1, ''))
        dump = json.loads(self.run_cli(env=self.env).stdout)
        self.assertEqual((dump['fleet_host'], dump['overlay_id']), ('mbp', 'mbp'))


if __name__ == '__main__':
    unittest.main()
