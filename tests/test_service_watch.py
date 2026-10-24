"""Behavioral watcher contracts; execute on MBP, never on the desktop."""
import contextlib
import datetime
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('service_watch', ROOT / 'scripts/service-watch.py')
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.watch = sw.Watch(self.root / 'state', self.root / 'inventory.json')

    def tearDown(self):
        self.watch.store.db.close()
        self.temp.cleanup()

    def test_finite_projection_withholds_every_arbitrary_string(self):
        secrets = ['sk-secret-abcdef', 'Bearer abc.eyJWT.def', 'Cookie: session=SUPERSECRET',
                   'kevin@example.com', '100.117.226.39', 'https://example.test/?token=secret',
                   '/home/kvn/private/account.json', '123 Main Street', 'Chicago',
                   '41.8781,-87.6298', 'SERIAL-R5CY93G2WNH', 'account_9123456']
        result = sw.project([sw.event('failed', count=7)], secrets)
        encoded = json.dumps(result)
        for secret in secrets:
            self.assertNotIn(secret, encoded)
        self.assertEqual(result['redaction_counts']['withheld_lines'], len(secrets))
        self.assertFalse(result['raw_text_transmitted'])

    def test_cognition_nested_transport_error(self):
        self.assertTrue(sw.receipt_error({'shadow': [{'error': 'transport unavailable'}]}))
        self.assertTrue(sw.receipt_error({'shadow': [{'parse_error': 'not served'}]}))
        self.assertFalse(sw.receipt_error({'shadow': [{'selected_action': 'read', 'error': None}]}))

    def test_file_growth_error_share_and_freshness(self):
        path = self.root / 'receipts.jsonl'
        path.write_text(''.join(json.dumps({'shadow': [{'error': 'not served'}]}) + '\n' for _ in range(10)))
        invariant = {'kind': 'receipt_error_share', 'path': str(path), 'max_error_share': .5}
        events = self.watch.invariant('user', 'fixture.service', invariant, {}, time.time())
        self.assertEqual([e['code'] for e in events], ['receipt_error_share'])
        with path.open('a') as stream:
            stream.write(''.join(json.dumps({'error': 'x' * 200}) + '\n' for _ in range(1000)))
        events = self.watch.invariant('user', 'fixture.service', invariant, {}, time.time())
        self.assertIn('error_file_growth', [e['code'] for e in events])
        events = self.watch.invariant('user', 'fixture.service', {'kind': 'file_freshness', 'path': str(path), 'max_age_seconds': 1}, {}, time.time() + 10)
        self.assertEqual(events[0]['code'], 'stale_file')

    def test_unknown_and_missing_invariants_are_not_healthy(self):
        self.assertEqual(self.watch.invariant('user', 'fixture.service', {'kind': 'unknown'}, {}, time.time())[0]['code'], 'invariant_unavailable')
        self.assertEqual(self.watch.invariant('user', 'fixture.service', {'kind': 'file_freshness', 'path': str(self.root / 'missing'), 'max_age_seconds': 1}, {}, time.time())[0]['code'], 'invariant_unavailable')

    def test_phone_caps_invariant_red_green_and_unavailable(self):
        invariant = {'kind': 'phone_caps', 'root': str(self.root)}
        cases = [
            (3, {'gate': 'O10', 'checked': ['fleet'], 'status': 'refused', 'findings': [{'rule': 'registry-phone-cap'}]}, ['phone_resource_caps']),
            (0, {'gate': 'O10', 'checked': ['fleet'], 'status': 'ok', 'findings': []}, []),
            (2, {}, ['invariant_unavailable']),
            (0, {'gate': 'O10', 'checked': [], 'status': 'ok', 'findings': []}, ['invariant_unavailable']),
            (3, {'gate': 'O10', 'checked': ['fleet'], 'status': 'refused', 'findings': [{'rule': 'scan-unavailable'}]}, ['invariant_unavailable']),
        ]
        for code, report, expected in cases:
            result = subprocess.CompletedProcess([], code, json.dumps(report), '')
            with patch.object(sw.subprocess, 'run', return_value=result) as run:
                events = self.watch.invariant('user', 'fixture.service', invariant, {}, time.time())
            self.assertEqual([e['code'] for e in events], expected)
            self.assertEqual(run.call_args[0][0], ['z0-guard', 'phone-caps', '--root', str(self.root)])
            self.assertEqual(run.call_args.kwargs['env']['Z0_GUARD_O10'], 'enforce')

    def test_phone_caps_recurring_root_follows_installed_fleet(self):
        with patch.object(sw.shutil, 'which', return_value=str(self.root / 'scripts/fleet')), patch.object(self.watch, 'invariant', return_value=[]) as invariant, patch.object(self.watch, 'record') as record:
            self.watch.phone_caps_invariant()
        self.assertEqual(invariant.call_args[0][2], {'kind': 'phone_caps', 'root': str(self.root)})
        record.assert_called_once_with('user', 'service-watch.service', [])

    def test_failure_notifies_once_with_persistent_dedupe_and_digest(self):
        delivered = []
        def fake(argv, timeout=15):
            delivered.append(argv)
            return subprocess.CompletedProcess(argv, 0, '', '')
        with patch.object(sw, 'command', fake):
            ident = self.watch.record('user', 'fixture.service', [sw.event('failed')])
            self.watch.record('user', 'fixture.service', [sw.event('failed')], force=True)
            other = sw.Store(self.root / 'state')
            fingerprint = self.watch.store.db.execute('SELECT fingerprint FROM incidents WHERE id=?', (ident,)).fetchone()[0]
            self.assertEqual(other.notify(fingerprint, 'fixture.service', 'failed', ident), 'deduplicated')
            other.db.close()
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0][0], 'notify-send')
        digest = self.watch.store.digest().read_text()
        self.assertIn('fixture.service', digest)
        self.assertIn('severe', digest)

    def test_global_rate_limit(self):
        with patch.object(sw, 'command', return_value=subprocess.CompletedProcess([], 0, '', '')) as send:
            results = [self.watch.store.notify(str(i), 'fixture.service', 'failed', str(i), now=100000) for i in range(6)]
        self.assertEqual(results, ['delivered'] * 5 + ['rate_limited'])
        self.assertEqual(send.call_count, 5)

    def test_loop_receipts_consecutive_zero_ticks(self):
        home = self.root / 'home'
        folder = home / '.z0int/loop/reports' / str(datetime.date.today())
        folder.mkdir(parents=True)
        path = folder / 'ticks.jsonl'
        path.write_text(''.join(json.dumps({'rows_added': {'shadow_decisions': count}}) + '\n' for count in [0, 0, 0, 3]))
        self.watch.units = {('user', 'z0int-loop-tick.service'): {}}
        with patch.object(sw.Path, 'home', return_value=home), patch.object(self.watch, 'record') as record:
            self.watch.loop_invariants()
            record.assert_not_called()
            self.watch.loop_invariants(seed=True)
            self.assertEqual(record.call_args[0][2][0]['code'], 'silent_noop')

    def test_restarts_in_window_not_lifetime_and_no_remediation(self):
        self.watch.last_scan = time.time()
        self.watch.units = {('user', 'fixture.service'): {'health_invariant': {'kind': 'systemd'}}}
        with patch.object(sw, 'properties', return_value={'fixture.service': {'ActiveState': 'active', 'NRestarts': '30'}}), patch.object(self.watch, 'journals'), patch.object(self.watch, 'loop_invariants'), patch.object(self.watch, 'phone_caps_invariant'), patch.object(self.watch, 'record') as record:
            self.watch.scan()
            self.assertEqual(record.call_args[0][2], [])
        with patch.object(sw, 'properties', return_value={'fixture.service': {'ActiveState': 'active', 'NRestarts': '33'}}), patch.object(self.watch, 'journals'), patch.object(self.watch, 'loop_invariants'), patch.object(self.watch, 'phone_caps_invariant'), patch.object(self.watch, 'record') as record:
            self.watch.scan()
            self.assertEqual(record.call_args[0][2][0]['code'], 'restart_loop')

    def test_timer_failure_and_age(self):
        self.watch.store.set('timer-success:user:fixture.service', time.time() - 1000)
        with patch.object(sw, 'properties', return_value={'fixture.service': {'Result': 'exit-code', 'ExecMainExitTimestampMonotonic': str(int((time.monotonic() - 1000) * 1000000))}}):
            events = self.watch.invariant('user', 'fixture.timer', {'kind': 'timer', 'max_age_seconds': 600}, {}, time.time())
        self.assertEqual([e['code'] for e in events], ['timer_failed', 'timer_stale'])

    def test_failed_timer_attempt_does_not_refresh_success_age(self):
        invariant = {'kind': 'timer', 'max_age_seconds': 600}
        with patch.object(sw, 'properties', return_value={'fixture.service': {'Result': 'success', 'ActiveState': 'inactive', 'ExecMainExitTimestampMonotonic': str(int((time.monotonic() - 1000) * 1000000))}}):
            self.watch.invariant('user', 'fixture.timer', invariant, {}, time.time())
        successful_at = self.watch.store.get('timer-success:user:fixture.service')
        with patch.object(sw, 'properties', return_value={'fixture.service': {'Result': 'exit-code', 'ActiveState': 'failed', 'ExecMainExitTimestampMonotonic': str(int(time.monotonic() * 1000000))}}):
            events = self.watch.invariant('user', 'fixture.timer', invariant, {}, time.time())
        self.assertEqual(self.watch.store.get('timer-success:user:fixture.service'), successful_at)
        self.assertEqual([e['code'] for e in events], ['timer_failed', 'timer_stale'])

    def test_unknown_timer_success_is_unavailable_not_invented_age(self):
        with patch.object(sw, 'properties', return_value={'fixture.service': {'Result': 'exit-code', 'ExecMainExitTimestampMonotonic': str(int(time.monotonic() * 1000000))}}):
            events = self.watch.invariant('user', 'fixture.timer', {'kind': 'timer', 'max_age_seconds': 600}, {}, time.time())
        self.assertEqual([e['code'] for e in events], ['timer_failed', 'invariant_unavailable'])

    def test_real_http_request_bodies_and_local_summary_never_leave(self):
        secret = 'sk-test-secret-0123456789 Bearer eyJwt.private.token Cookie=SECRET kevin@example.com 10.2.3.4 https://a.test/?token=foo /home/kvn/private 123 Main Street Chicago 41.88,-87.63 serial-R5CY93G2WNH'
        captured = []
        decision = {'severity': 'severe', 'cause': 'failed', 'fix': 'Inspect manually', 'evidence': [0], 'confidence': .9}
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                captured.append({'path': self.path, 'body': json.loads(body)})
                if self.path == '/local':
                    output = {**decision, 'cause': secret, 'fix': secret}
                    value = {'choices': [{'message': {'content': json.dumps(output)}}]}
                else:
                    value = {'ok': True, 'provider': 'groq', 'model': 'openai/gpt-oss-20b', 'output': json.dumps(decision)}
                payload = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        original = sw.post
        def routed(url, body, timeout=40):
            local = url == sw.LOCAL_URL
            return original(f'http://127.0.0.1:{server.server_port}/' + ('local' if local else 'offhost'), body, timeout)
        oauth = []
        def helper(argv, **kwargs):
            oauth.append(json.loads(kwargs['input']))
            return subprocess.CompletedProcess(argv, 0, json.dumps({'ok': True, 'returned_model': 'gpt-6-luna', 'text': json.dumps(decision)}), '')
        try:
            with patch.object(sw, 'command', return_value=subprocess.CompletedProcess([], 0, '', '')):
                ident = self.watch.record('user', 'fixture.service', [sw.event('failed')], [secret])
            with patch.object(sw, 'post', routed), patch.object(sw.subprocess, 'run', helper), patch.object(self.watch.store, 'notify'):
                self.watch.triage(ident, [secret])
            self.assertIn(secret, json.dumps(captured[0]['body']))
            self.assertEqual(captured[-1]['path'], '/offhost')
            self.assertNotIn(secret, json.dumps(captured[-1]['body']))
            self.assertNotIn(secret, json.dumps(oauth))
            for marker in ['sk-test-secret', 'kevin@example.com', '10.2.3.4', 'Main Street', 'Chicago', 'serial-R5']:
                self.assertNotIn(marker, json.dumps(captured[-1]['body']))
                self.assertNotIn(marker, json.dumps(oauth))
            self.assertNotIn(secret, (self.watch.store.root / 'triage.jsonl').read_text())
            evidence = {'ok': True, 'raw_local_only': True, 'offhost_secret_matches': 0,
                        'captured_requests': captured, 'subscription_stdin': oauth}
            output = Path(os.environ.get('SERVICE_WATCH_TEST_EVIDENCE', str(self.root / 'evidence.json')))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(evidence, indent=2))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_model_only_severe_requires_subscription_confirmation(self):
        decision = {'severity': 'warn', 'cause': 'Error rate elevated', 'fix': 'Inspect manually', 'evidence': [0], 'confidence': .8}
        ident = self.watch.record('user', 'fixture.service', [sw.event('journal_error_rate', count=10)], ['synthetic error'])
        local = {'choices': [{'message': {'content': json.dumps(decision)}}]}
        remote = {'ok': True, 'provider': 'groq', 'model': 'openai/gpt-oss-20b',
                  'output': json.dumps({**decision, 'severity': 'severe'})}
        def routed(url, body, timeout=40):
            return local if url == sw.LOCAL_URL else remote
        with patch.object(sw, 'post', routed), patch.object(sw.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"ok":false}', '')), patch.object(self.watch.store, 'notify') as notify:
            self.watch.triage(ident, ['synthetic error'])
            notify.assert_not_called()
        data = json.loads(self.watch.store.db.execute('SELECT data FROM incidents WHERE id=?', (ident,)).fetchone()[0])
        self.assertEqual(data['decision']['severity'], 'severe')
        self.assertFalse(data['severe_confirmed'])

    def test_raw_route_fails_closed_if_host_does_not_own_address(self):
        with patch.object(sw, 'command', return_value=subprocess.CompletedProcess([], 0, '[{\"addr_info\":[{\"local\":\"127.0.0.1\"}]}]', '')), patch.object(sw.urllib.request, 'build_opener') as opener:
            with self.assertRaises(ValueError):
                sw.post(sw.LOCAL_URL, {'raw': 'synthetic secret'})
            opener.assert_not_called()

    def test_post_refuses_redirects(self):
        captured = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                captured.append(self.path)
                self.send_response(307)
                self.send_header('Location', '/offhost')
                self.end_headers()
        server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with self.assertRaises(Exception):
                sw.post(f'http://127.0.0.1:{server.server_port}/local', {'raw': 'synthetic_secret'})
            self.assertEqual(captured, ['/local'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
