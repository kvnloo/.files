import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/burn-pace'
NOW = datetime(2026, 11, 5, 6, 0, tzinfo=timezone.utc)
AT = NOW.isoformat()
RESET = (NOW + timedelta(hours=1)).isoformat()


def paid(used=20, primary=10, band='on-pace'):
    return {'observed_at': AT, 'weekly_used_pct': used, 'band': band,
            'max_workflow_agents': 6, 'usage': {
                'updatedAt': AT,
                'primary': {'usedPercent': primary, 'resetsAt': RESET},
                'secondary': {'usedPercent': used, 'resetsAt': RESET}}}


def capped(remaining=2):
    return {'observed_at': AT, 'source': 'account_observed', 'windows': [
        {'name': 'messages/hour', 'limit': 10, 'remaining': remaining, 'resets_at': RESET}]}


class AdmitTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SCRIPT))
        self.admit = self.module.get('admit')
        self.assertTrue(callable(self.admit), 'burn-pace must expose admit(lane)')

    def decide(self, row, lane='claude', **extra):
        return self.admit(lane, {'at': AT, 'lanes': {lane: row}, **extra}, now=NOW)

    def assert_denied(self, row, reason, **extra):
        out = self.decide(row, **extra)
        self.assertEqual(out['decision'], 'deny', out)
        self.assertIn(reason, out['reason'])

    def test_healthy_paid_lane(self):
        self.assertEqual(self.decide(paid())['decision'], 'allow')

    def test_exhausted_weekly_even_when_ratio_is_unknown(self):
        self.assert_denied(paid(100, band='unknown'), 'secondary exhausted')

    def test_short_window_exhaustion(self):
        self.assert_denied(paid(primary=100), 'primary exhausted')

    def test_every_reported_paid_window_binds(self):
        row = paid()
        row['usage']['tertiary'] = {'usedPercent': 100, 'resetsAt': RESET}
        self.assert_denied(row, 'tertiary exhausted')
        row = paid()
        row['usage']['extraRateWindows'] = [
            {'id': 'monthly', 'window': {'usedPercent': 100, 'resetsAt': RESET}}]
        self.assert_denied(row, 'monthly exhausted')

    def test_pace_hold_and_avoid(self):
        self.assert_denied(paid(band='hard-throttle'), 'hard-throttle')
        self.assert_denied(paid(), 'avoid', z0_factory={'avoid': ['claude']})
        row = paid()
        row['max_workflow_agents'] = 0
        self.assert_denied(row, 'no workflow agents')

    def test_unknown_and_probe_errors_do_not_allow(self):
        self.assert_denied(paid(band='unknown'), 'unknown pace')
        self.assert_denied(paid(), 'probe error', probe_errors=[{'provider': 'claude'}])
        self.assertEqual(self.decide(paid(), probe_errors=[{'provider': 'codex'}])['decision'], 'allow')

    def test_stale_future_and_expired_rows(self):
        for delta in (-901, 1):
            row = paid()
            row['observed_at'] = (NOW + timedelta(seconds=delta)).isoformat()
            self.assert_denied(row, 'timestamp')
        row = paid()
        row['usage']['updatedAt'] = (NOW - timedelta(seconds=901)).isoformat()
        self.assert_denied(row, 'timestamp')
        row = paid()
        row['usage']['secondary']['resetsAt'] = AT
        self.assert_denied(row, 'refresh')

    def test_free_models_and_apps_use_same_window_checks(self):
        for lane in ('opencode/deepseek-v4.1-flash-free', 'groq/model', 'chatgpt-app', 'deepseek-app'):
            with self.subTest(lane=lane):
                self.assertEqual(self.decide(capped(), lane=lane)['decision'], 'allow')
                self.assert_denied(capped(0), 'exhausted', lane=lane)
                row = capped()
                row['windows'].append({'name': 'monthly', 'limit': 100, 'remaining': 0, 'resets_at': RESET})
                self.assert_denied(row, 'monthly exhausted', lane=lane)

    def test_unknown_caps_and_historical_balances_deny(self):
        self.assert_denied({'observed_at': AT}, 'quota unknown')
        row = capped()
        row['source'] = 'historical'
        self.assert_denied(row, 'source')
        for value in (None, -1, 11, float('nan'), float('inf'), True, '2'):
            row = capped(value)
            self.assert_denied(row, 'invalid')
        row = capped()
        row['windows'] = []
        self.assert_denied(row, 'quota unknown')

    def test_invalid_shapes_fail_closed(self):
        for row in (None, [], 'bad', {'usage': []}, {'windows': [None], 'source': 'account_observed'}):
            self.assert_denied(row, 'invalid')
        self.assertEqual(self.admit('missing', {'at': AT, 'lanes': {}}, now=NOW)['decision'], 'deny')
        for raw in (None, [], {'lanes': []}):
            with self.subTest(raw=raw):
                if raw is not None:
                    self.assertEqual(self.admit('claude', raw, now=NOW)['decision'], 'deny')

    def test_inputs_are_not_mutated(self):
        rows = {'at': AT, 'lanes': {'claude': paid()}}
        before = copy.deepcopy(rows)
        self.admit('claude', rows, now=NOW)
        self.assertEqual(rows, before)

    def test_cached_rows_and_extra_subscriptions(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            sample = {'at': AT, 'lanes': {'claude': paid(), 'claude2': paid()}}
            for row in sample['lanes'].values():
                del row['usage']
                del row['observed_at']
            (state / 'burn-pace.jsonl').write_text(json.dumps(sample) + '\n' + '{"partial":')
            (state / 'codexbar-fresh.json').write_text(json.dumps([
                {'provider': 'claude', 'usage': paid()['usage']}]))
            (state / 'claude2-headers.json').write_text(json.dumps({
                'row': {'provider': 'claude2', 'usage': paid()['usage']}}))
            for lane in ('claude', 'claude2'):
                with patch('subprocess.run', side_effect=AssertionError('no provider calls')):
                    self.assertEqual(self.admit(lane, now=NOW, state=state)['decision'], 'allow')
            (state / 'admission-rows.json').write_text(json.dumps({
                'at': AT, 'lanes': {'deepseek-app': capped()}}))
            self.assertEqual(self.admit('deepseek-app', now=NOW, state=state)['decision'], 'allow')
            # An auxiliary file cannot replace a paid stop with a fabricated allowance.
            (state / 'admission-rows.json').write_text(json.dumps({
                'at': AT, 'lanes': {'claude': capped()}}))
            self.assertEqual(self.admit('claude', now=NOW, state=state)['decision'], 'deny')

    def test_missing_or_corrupt_live_state_is_deny(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            self.assertEqual(self.admit('claude', now=NOW, state=state)['decision'], 'deny')
            (state / 'burn-pace.jsonl').write_text('{bad}\n')
            self.assertEqual(self.admit('claude', now=NOW, state=state)['decision'], 'deny')

    def test_expired_app_caps_require_refresh_not_assumed_replenishment(self):
        row = capped(0)
        row['windows'][0]['resets_at'] = AT
        self.assert_denied(row, 'refresh', lane='chatgpt-app')
        row['windows'][0]['remaining'] = 2
        self.assert_denied(row, 'refresh', lane='chatgpt-app')

    def test_newest_corrupt_or_unterminated_sample_cannot_allow(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            sample = json.dumps({'at': AT, 'lanes': {'claude': paid()}})
            file = state / 'burn-pace.jsonl'
            for text in (sample, sample + '\n{corrupt}\n', 'x' * 65537):
                file.write_text(text)
                self.assertEqual(self.admit('claude', now=NOW, state=state)['decision'], 'deny')

    def test_cli_exit_codes_and_no_probe_or_state_write(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            clock = datetime.now(timezone.utc)
            row = capped()
            row['observed_at'] = clock.isoformat()
            row['windows'][0]['resets_at'] = (clock + timedelta(hours=1)).isoformat()
            file = state / 'admission-rows.json'
            file.write_text(json.dumps({'at': clock.isoformat(), 'lanes': {'deepseek-app': row}}))
            for remaining, code in ((2, 0), (0, 1)):
                row['windows'][0]['remaining'] = remaining
                file.write_text(json.dumps({'at': clock.isoformat(), 'lanes': {'deepseek-app': row}}))
                before = {p.name: p.read_bytes() for p in state.iterdir()}
                out = subprocess.run([sys.executable, str(SCRIPT), 'admit', 'deepseek-app',
                                      '--json', '--state-dir', str(state)], capture_output=True, text=True)
                self.assertEqual(out.returncode, code, out.stderr)
                self.assertEqual(json.loads(out.stdout)['decision'], 'allow' if code == 0 else 'deny')
                self.assertEqual(before, {p.name: p.read_bytes() for p in state.iterdir()})
            bad = subprocess.run([sys.executable, str(SCRIPT), 'admit'], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


if __name__ == '__main__':
    unittest.main()
