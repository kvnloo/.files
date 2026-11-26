"""The untracked private overlay: parsing, ${KEY} filling, registry merge, loud failures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/private-overlay'
sys.path.insert(0, str(ROOT / 'scripts'))
import private_overlay as po  # noqa: E402
import yaml  # noqa: E402


class Overlay(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {'DOTFILES_PRIVATE_DIR': str(FIXTURE)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in po.parse_env((ROOT / po.EXAMPLE_ENV).read_text()):
            os.environ.pop(key, None)

    def test_parse_env_accepts_export_quotes_and_comments(self):
        self.assertEqual(po.parse_env('# c\n\nexport A=1\nB="x y"\nC=\'z\'\n'), {'A': '1', 'B': 'x y', 'C': 'z'})
        with self.assertRaises(po.PrivateOverlayError):
            po.parse_env('not a pair\n')

    def test_example_and_fixture_name_the_same_keys(self):
        example = po.parse_env((ROOT / po.EXAMPLE_ENV).read_text())
        self.assertEqual(set(example), set(po.load_env()))
        self.assertEqual(example, po.load_env())

    def test_expand_fills_and_fails_loudly_on_unset_key(self):
        self.assertEqual(po.expand('http://${GROOT_TAILNET_IP}:8212'), 'http://100.64.0.10:8212')
        with self.assertRaisesRegex(po.PrivateOverlayError, 'NOT_A_KEY.*private.env'):
            po.expand('${NOT_A_KEY}')
        self.assertEqual(po.expand('$1 $fail "$KUBERNETES_SERVICE_HOST"'), '$1 $fail "$KUBERNETES_SERVICE_HOST"')

    def test_process_environment_overrides_file(self):
        with patch.dict(os.environ, {'GROOT_TAILNET_IP': '100.64.0.99'}):
            self.assertEqual(po.require('GROOT_TAILNET_IP'), '100.64.0.99')

    def test_missing_overlay_directory_is_an_error_not_a_default(self):
        with tempfile.TemporaryDirectory() as empty, patch.dict(os.environ, {'DOTFILES_PRIVATE_DIR': empty}):
            self.assertEqual(po.load_env(), {})
            with self.assertRaisesRegex(po.PrivateOverlayError, 'GROOT_TAILNET_IP'):
                po.require('GROOT_TAILNET_IP')

    def test_registry_merge_adds_private_addresses(self):
        public = yaml.safe_load((ROOT / 'config/fleet/nodes.yaml').read_text())
        self.assertFalse(any('tailnet_ip' in n for n in public['nodes'].values()))
        merged = po.merge_registry(public)
        self.assertEqual(merged['nodes']['mbp']['tailnet_ip'], '100.64.0.11')
        self.assertEqual(merged['nodes']['mbp']['ssh_port'], 2222)
        self.assertEqual(merged['nodes']['omarchy-phone']['android'],
                         {**public['nodes']['omarchy-phone']['android'], 'adb_host': '100.64.0.13'})
        self.assertEqual(po.missing_node_keys(merged['nodes'], {'groot': ['tailnet_ip']}), [])

    def test_registry_merge_refuses_unknown_node(self):
        with self.assertRaisesRegex(po.PrivateOverlayError, 'phantom'):
            po.merge_registry({'nodes': {'mbp': {}}}, {'nodes': {'phantom': {'tailnet_ip': '100.64.0.1'}}})

    def test_cli_check_get_and_render(self):
        tool = [sys.executable, str(ROOT / 'scripts/private-overlay')]
        env = {**os.environ, 'DOTFILES_PRIVATE_DIR': str(FIXTURE)}
        self.assertEqual(subprocess.run(tool + ['check'], env=env, capture_output=True).returncode, 0)
        got = subprocess.run(tool + ['get', 'MBP_TAILNET_IP'], env=env, capture_output=True, text=True)
        self.assertEqual(got.stdout.strip(), '100.64.0.11')
        with tempfile.TemporaryDirectory() as empty:
            env['DOTFILES_PRIVATE_DIR'] = empty
            failed = subprocess.run(tool + ['render', str(ROOT / 'config/tern/hosts.names')],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1)
            self.assertIn('GROOT_TAILNET_IP', failed.stderr)
            self.assertEqual(failed.stdout, '')
            self.assertEqual(subprocess.run(tool + ['check'], env=env, capture_output=True).returncode, 1)


if __name__ == '__main__':
    unittest.main()
