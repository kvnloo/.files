"""scripts/cos-rule-sync: managed CoS block in Codex, OMP and every Hermes profile; idempotent with backups."""
import importlib.machinery
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'cos-rule-sync'
loader = importlib.machinery.SourceFileLoader('cos_rule_sync', str(SCRIPT))
spec = importlib.util.spec_from_loader('cos_rule_sync', loader)
crs = importlib.util.module_from_spec(spec)
loader.exec_module(crs)

RULE = '<!-- canonical header -->\n\n# Chief of Staff rule\n\nYou are the CoS.\n'


class CosRuleSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / '.config/cos').mkdir(parents=True)
        self.rule = self.home / '.config/cos/COS-RULE.md'
        self.rule.write_text(RULE)
        (self.home / '.codex').mkdir()
        (self.home / '.omp/agent').mkdir(parents=True)
        (self.home / '.omp/agent/APPEND_SYSTEM.md').write_text('mirror\n')
        (self.home / '.omp/profiles/stable/agent').mkdir(parents=True)
        hh = self.home / '.hermes'
        (hh / 'profiles/clean').mkdir(parents=True)
        (hh / 'profiles/intake').mkdir(parents=True)
        (hh / 'profiles/empty').mkdir(parents=True)
        (hh / 'config.yaml').write_text('x: 1\n')
        (hh / 'SOUL.md').write_text('Default soul.\n')
        (hh / 'profiles/clean/config.yaml').write_text('x: 1\n')
        (hh / 'profiles/intake/SOUL.md').write_text('Intake: brainstorm and delegate.\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, **kw):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = crs.sync(self.rule, self.home, {}, dry_run=kw.get('dry_run', False),
                          check=kw.get('check', False), stamp=kw.get('stamp', 'T1'))
        return rc, out.getvalue()

    def test_targets_cover_every_harness_and_profile(self):
        names = [t[0] for t in crs.targets(self.home, {})]
        self.assertEqual(names, ['codex', 'omp', 'omp:stable', 'hermes:<home>', 'hermes:clean', 'hermes:intake'])
        paths = [str(t[1]) for t in crs.targets(self.home, {})]
        self.assertFalse(any('APPEND_SYSTEM' in p for p in paths))

    def test_hermes_home_pointing_at_a_profile_still_covers_every_profile(self):
        env = {'HERMES_HOME': str(self.home / '.hermes/profiles/clean')}
        names = [t[0] for t in crs.targets(self.home, env)]
        self.assertIn('hermes:intake', names)
        self.assertEqual(names.count('hermes:clean'), 1)

    def test_writes_block_keeps_text_and_backup(self):
        rc, _ = self.run_sync()
        self.assertEqual(rc, 0)
        sha = crs.rule_sha(RULE)
        soul = (self.home / '.hermes/profiles/intake/SOUL.md').read_text()
        self.assertTrue(soul.startswith('Intake: brainstorm and delegate.\n\n'))
        self.assertIn(f'<!-- COS-RULE:BEGIN sha={sha} -->', soul)
        self.assertIn(f'CoS rule sha: {sha}', soul)
        self.assertNotIn('canonical header', soul)
        self.assertTrue((self.home / '.hermes/profiles/intake/SOUL.md.bak-cos-T1').exists())
        self.assertTrue((self.home / '.codex/AGENTS.md').read_text().startswith('<!-- COS-RULE:BEGIN'))
        self.assertEqual((self.home / '.omp/agent/APPEND_SYSTEM.md').read_text(), 'mirror\n')

    def test_idempotent_and_check(self):
        self.run_sync()
        before = (self.home / '.codex/AGENTS.md').read_text()
        rc, out = self.run_sync(stamp='T2')
        self.assertEqual(rc, 0)
        self.assertNotIn('written', out)
        self.assertEqual((self.home / '.codex/AGENTS.md').read_text(), before)
        self.assertFalse(list(self.home.rglob('*.bak-cos-T2')))
        self.assertEqual(self.run_sync(check=True)[0], 0)

    def test_rule_change_replaces_block_in_place(self):
        self.run_sync()
        p = self.home / '.hermes/SOUL.md'
        p.write_text(p.read_text() + '\nOwner note after block.\n')
        self.rule.write_text(RULE + '\nNew line.\n')
        self.assertEqual(self.run_sync(check=True)[0], 1)
        self.run_sync(stamp='T3')
        text = p.read_text()
        self.assertEqual(text.count('COS-RULE:BEGIN'), 1)
        self.assertIn('New line.', text)
        self.assertTrue(text.rstrip().endswith('Owner note after block.'))
        self.assertTrue((self.home / '.hermes/SOUL.md.bak-cos-T3').exists())

    def test_duplicate_blocks_collapse(self):
        block = crs.render_block(RULE)
        self.assertEqual(crs.apply_block('a\n' + block + 'b\n' + block, block), 'a\n' + block + 'b\n')


if __name__ == '__main__':
    unittest.main()
