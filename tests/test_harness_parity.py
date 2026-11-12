"""Offline checks for the read-only parity inventory. Run through fleet-build."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/harness-parity-snapshot.py'
spec = importlib.util.spec_from_file_location('parity', SCRIPT)
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)
BLOCK = '<!-- owner-canon:start -->\nfixture rule\n<!-- owner-canon:end -->'


class SnapshotTests(unittest.TestCase):
    def snapshot(self, instructions, canon=BLOCK):
        with tempfile.TemporaryDirectory(prefix='parity home ') as temp:
            home = Path(temp)
            (home / 'AGENTS.md').write_text(instructions)
            if canon is not None:
                path = home / parity.CANON
                path.parent.mkdir(parents=True)
                path.write_text(canon + '\n')
            with patch.object(parity.Path, 'home', return_value=home), \
                 patch.object(parity.shutil, 'which', return_value=None), \
                 patch.object(parity, 'command', return_value={'exit': 0, 'stdout': 'fixture'}):
                return parity.snapshot()['values']

    def test_exact_canon_inside_other_instructions(self):
        values = self.snapshot('Other instructions\n' + BLOCK + '\n')
        self.assertEqual(values['AGENTS.md:canon_blocks'], 1)
        self.assertTrue(values['AGENTS.md:canon_matches_generated'])

    def test_changed_canon_does_not_match(self):
        values = self.snapshot(BLOCK.replace('fixture rule', 'stale rule'))
        self.assertFalse(values['AGENTS.md:canon_matches_generated'])

    def test_duplicate_blocks_do_not_match(self):
        values = self.snapshot(BLOCK + '\n' + BLOCK)
        self.assertEqual(values['AGENTS.md:canon_blocks'], 2)
        self.assertFalse(values['AGENTS.md:canon_matches_generated'])

    def test_absent_canon_does_not_match(self):
        values = self.snapshot('Other instructions')
        self.assertEqual(values['AGENTS.md:canon_blocks'], 0)
        self.assertFalse(values['AGENTS.md:canon_matches_generated'])

    def test_missing_generated_file_does_not_match(self):
        values = self.snapshot(BLOCK, canon=None)
        self.assertFalse(values[parity.CANON + ':exists'])
        self.assertFalse(values['AGENTS.md:canon_matches_generated'])

    def test_redacts_nested_credentials(self):
        value = {'model': 'fixture', 'api_key': 'not-a-real-key', 'nested': [{'token': 'fixture', 'provider': 'test'}]}
        self.assertEqual(parity.safe(value), {'model': 'fixture', 'nested': [{'provider': 'test'}]})

    def test_opencode_json_and_jsonc_are_both_collected(self):
        self.assertEqual(parity.CONFIGS['.config/opencode/opencode.json'],
                         parity.CONFIGS['.config/opencode/opencode.jsonc'])
        self.assertIn('model', parity.CONFIGS['.config/opencode/opencode.json'])

    def test_config_fields_are_allowlisted(self):
        self.assertNotIn('env', parity.CONFIGS['.claude/settings.json'])
        self.assertNotIn('credential_source', parity.CONFIGS['.fx/settings.json'])
        self.assertEqual(parity.field({'model': {'default': 'fixture', 'token': 'test'}}, 'model'), {'default': 'fixture'})
        self.assertEqual(parity.field({}, 'context.engine'), '<unset>')


if __name__ == '__main__':
    unittest.main()
