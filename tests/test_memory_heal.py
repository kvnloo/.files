"""memory-heal: red on the failures that actually happened (2026-10-27..11-02), green when live == intent,
and every known failure class maps to exactly one remedy."""
import importlib.machinery
import importlib.util
import sys
import time
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('memory_heal', str(ROOT / 'scripts/memory-heal'))
spec_ = importlib.util.spec_from_loader(loader.name, loader)
heal = importlib.util.module_from_spec(spec_)
sys.modules[loader.name] = heal
loader.exec_module(heal)
SPEC = tomllib.loads((ROOT / 'config/host/memory-system-intent.toml').read_text())

CONFIG_CONTAINER = '''[agents]
  [agents.hermes]
    # 2026-10-27 memory-services step 5a: the profiles container
    dirs = ["~/.hermes/sessions", "~/.hermes/profiles"]

[[remote_hosts]]
host = "mbp"
'''
NOW = 1_800_000_000.0


class FakeHost(heal.Host):
    def __init__(self, units=None, wanted=None, journals=None, config=CONFIG_CONTAINER, profiles=('clean',),
                 native=None, archived=None, ctx_log='', receipt=None, empty=()):
        self.units = units or {}
        self._wanted = wanted
        self.journals = journals or {}
        self.files = {str(heal.expand(SPEC['agentsview']['config'])): config,
                      SPEC['ctx']['import_log']: ctx_log,
                      SPEC['recall']['receipt']: receipt or '{"at": "2027-01-15T08:00:00+00:00", "pass": true}'}
        self.profiles, self.native, self.archived, self.empty = list(profiles), native or {}, archived or {}, list(empty)
        self.calls = []

    def unit(self, unit):
        return self.units.get(unit, {'ActiveState': 'active'})

    def wanted(self, timer):
        return True if self._wanted is None else timer in self._wanted

    def journal(self, unit, lines=40):
        return self.journals.get(unit, '')

    def systemctl(self, *args):
        self.calls.append(args)
        return 0, '', ''

    def now(self):
        return NOW

    def read(self, path):
        return self.files[str(path)]

    def write(self, path, text):
        self.files[str(path)] = text

    def hermes_profiles(self, hermes_home):
        return self.profiles

    def native_newest(self, hermes_home, profile, before):
        v = self.native.get(profile)
        return v if v is not None and v < before else None

    def archive_newest(self, archive, hermes_home):
        return self.archived

    def mem_available_kib(self):
        return 3_000_000

    def empty_json(self, roots):
        return self.empty


def fresh_ctx():
    stamp = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(NOW - 600))
    return f'{stamp} wait_rc=0 gen a -> b took 60s\n'


def generated_config():
    return heal.render_hermes_block(CONFIG_CONTAINER, heal.hermes_dirs(SPEC, ['clean']))


def recent_receipt():
    return '{"at": "%s", "pass": true}' % time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(NOW - 600))


class Invariants(unittest.TestCase):
    def healthy(self, **kw):
        base = dict(config=generated_config(), ctx_log=fresh_ctx(), receipt=recent_receipt())
        base.update(kw)
        return FakeHost(**base)

    def test_green_when_live_matches_intent(self):
        self.assertEqual(heal.check(SPEC, self.healthy()), [])

    def test_container_config_is_red_and_regenerated(self):
        """The 2026-10-27 regression: the profiles container silently dropped every profile."""
        host = self.healthy(config=CONFIG_CONTAINER)
        [f] = heal.check(SPEC, host)
        self.assertEqual((f.invariant, f.remedy), ('agentsview_coverage', 'regenerate_agentsview'))
        heal.remedy(f, SPEC, host, Path('/nonexistent'))
        self.assertEqual(heal.configured_dirs(host.read(heal.expand(SPEC['agentsview']['config']))),
                         ['~/.hermes/sessions', '~/.hermes/profiles/clean'])
        self.assertIn(('restart', 'agentsview.service'), host.calls)
        self.assertEqual(heal.check(SPEC, host), [])

    def test_archive_lag_is_red_but_fresh_sessions_are_not(self):
        lagging = self.healthy(native={'clean': NOW - 3 * 86400}, archived={'clean': NOW - 9 * 86400})
        [f] = heal.check(SPEC, lagging)
        self.assertEqual((f.invariant, f.remedy), ('archive_fresh', 'sync_archive'))
        just_started = self.healthy(native={'clean': NOW - 60}, archived={'clean': NOW - 3 * 3600})
        self.assertEqual(heal.check(SPEC, just_started), [])

    def test_unwanted_timer_is_red(self):
        """ctx-import.timer was linked but not in timers.target.wants after the 10-31 reboot."""
        wanted = {t['unit'] for t in SPEC['timer']} - {'ctx-import.timer'}
        [f] = heal.check(SPEC, self.healthy(wanted=wanted))
        self.assertEqual((f.subject, f.remedy), ('ctx-import.timer', 'enable_now'))

    def test_stale_ctx_is_red(self):
        [f] = heal.check(SPEC, self.healthy(ctx_log='2026-10-26T14:46:47-05:00 wait_rc=0 gen a -> a\n'))
        self.assertEqual((f.invariant, f.remedy), ('ctx_fresh', 'run_ctx_import'))

    def test_zero_byte_policy_state_is_a_known_class(self):
        tb = 'json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)\n'
        host = self.healthy(units={'z0int-policy.service': {'ActiveState': 'failed'}},
                            journals={'z0int-policy.service': tb})
        [f] = heal.check(SPEC, host)
        self.assertEqual(f.remedy, 'zero_byte_json')

    def test_degraded_loop_tick_escalates_instead_of_restarting(self):
        host = self.healthy(units={'z0int-loop-tick.service': {'ActiveState': 'failed', 'ExecMainStatus': '3'}},
                            journals={'z0int-loop-tick.service': 'tick degraded (cognition:labels_not_growing)'})
        [f] = heal.check(SPEC, host)
        self.assertIsNone(f.remedy)

    def test_ctx_supervisor_failure_is_reset_not_restarted(self):
        host = self.healthy(units={'ctx.service': {'ActiveState': 'failed'}})
        [f] = heal.check(SPEC, host)
        self.assertEqual(f.remedy, 'reset_failed')
        heal.remedy(f, SPEC, host, Path('/nonexistent'))
        self.assertEqual(host.calls, [('reset-failed', 'ctx.service')])

    def test_dead_daemon_is_restarted(self):
        host = self.healthy(units={'agentsview.service': {'ActiveState': 'failed'}})
        [f] = heal.check(SPEC, host)
        heal.remedy(f, SPEC, host, Path('/nonexistent'))
        self.assertIn(('restart', 'agentsview.service'), host.calls)

    def test_every_declared_class_has_a_remedy(self):
        for row in SPEC['oneshot']:
            for cls in row.get('known', []):
                if cls != 'derived':
                    self.assertIn(cls, ('zero_byte_json',))

    def test_render_refuses_unknown_layout(self):
        with self.assertRaises(ValueError):
            heal.render_hermes_block('[agents]\n', ['x'])


if __name__ == '__main__':
    unittest.main()
