"""Behavioral watcher contracts; execute on MBP, never on the desktop."""
import contextlib
import datetime
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
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
        self.watch.checkout_roots = []
        self.watch.checkout_discover = lambda roots: []
        self.watch.reaper_status = self.root / 'latest.json'
        self.watch.refresh_checkout_count()

    def tearDown(self):
        self.watch.stop.set()
        self.watch.store.db.close()
        self.temp.cleanup()

    def test_host_drift_uses_existing_notification_dedupe(self):
        receipt = self.root / '.local/state/host-drift/latest.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({'schema': 'host-drift.v1', 'status': 'drift',
                                       'drift': [{'path': '/private/not-forwarded'}], 'unknown': []}))
        with patch.object(sw.Path, 'home', return_value=self.root), \
             patch.object(sw, 'Watch', return_value=self.watch), \
             patch.object(sys, 'argv', ['service-watch', 'host-drift']), \
             patch.object(self.watch.store, 'notify') as notify:
            self.assertEqual(sw.main(), 0)
            self.assertEqual(sw.main(), 0)
            self.assertEqual(notify.call_count, 1)
        text = self.watch.store.db.execute('SELECT data FROM incidents').fetchone()[0]
        self.assertIn('host_config_drift', text)
        self.assertNotIn('/private/not-forwarded', text)

    def test_host_drift_missing_receipt_is_unknown_and_notifies(self):
        with patch.object(sw.Path, 'home', return_value=self.root), \
             patch.object(sw, 'Watch', return_value=self.watch), \
             patch.object(sys, 'argv', ['service-watch', 'host-drift']), \
             patch.object(self.watch.store, 'notify') as notify:
            self.assertEqual(sw.main(), 0)
            self.assertEqual(notify.call_count, 1)
        text = self.watch.store.db.execute('SELECT data FROM incidents').fetchone()[0]
        self.assertIn('host_drift_unknown', text)

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

    def test_live_checkout_count_overrides_stale_daily_snapshot_and_notifies(self):
        self.watch.checkout_threshold = 1
        self.watch.checkout_roots = [self.root]
        paths = [self.root / name for name in ('first', 'second')]
        for path in paths:
            path.mkdir()
        self.watch.reaper_status.write_text(json.dumps({
            'checkout_count': 0, 'timestamp': 'old', 'removed_count': 7,
            'bytes_freed': 123, 'errors': [{'stage': 'archive', 'error': 'archive failed'}]}))
        with patch.object(self.watch, 'checkout_discover', return_value=paths) as discover, patch.object(self.watch.store, 'notify') as notify:
            self.watch.refresh_checkout_count()
            self.watch.checkout_invariants()
            notify.assert_called_once()
            discover.assert_called_once_with([self.root])
        status = self.watch.store.get('worktree-reaper')
        self.assertEqual(status['checkout_count'], 2)
        row = self.watch.store.db.execute('SELECT data FROM incidents').fetchone()
        data = json.loads(row[0])
        self.assertEqual(data['window']['evidence'][0]['code'], 'checkout_count_exceeded')
        self.assertEqual(data['window']['evidence'][0]['metrics'], {'count': 2, 'threshold': 1})
        digest = self.watch.store.digest().read_text()
        for text in ('Live checkout count: 2', 'removed_count', '123', 'archive failed', 'old'):
            self.assertIn(text, digest)
        self.assertNotIn('archive failed', json.dumps(data['window']))

    def test_checkout_count_is_fresh_deduplicated_and_threshold_is_strict(self):
        self.watch.checkout_threshold = 1
        self.watch.checkout_roots = [self.root, self.root]
        path = self.root / 'checkout'
        path.mkdir()
        with patch.object(self.watch, 'checkout_discover', return_value=[path, path]) as discover, patch.object(self.watch, 'record') as record:
            self.watch.refresh_checkout_count()
            self.watch.checkout_invariants()
            record.assert_not_called()
            self.assertEqual(self.watch.store.get('worktree-reaper')['checkout_count'], 1)
            path.rmdir()
            self.watch.refresh_checkout_count()
            self.watch.checkout_invariants()
            self.assertEqual(self.watch.store.get('worktree-reaper')['checkout_count'], 0)
            self.assertEqual(discover.call_count, 2)

    def test_checkout_read_failure_is_unavailable_not_healthy(self):
        self.watch.checkout_roots = [self.root]
        with patch.object(self.watch, 'checkout_discover', side_effect=OSError('private error')), patch.object(self.watch, 'record') as record:
            self.watch.refresh_checkout_count()
            self.watch.checkout_invariants()
        self.assertEqual(record.call_args[0][2][0]['code'], 'invariant_unavailable')
        status = self.watch.store.get('worktree-reaper')
        self.assertEqual(status['count_errors'], 1)
        self.assertEqual(status['status'], 'unavailable')
        self.assertNotIn('private error', json.dumps(status))

    def test_checkout_default_threshold_and_negative_configuration(self):
        self.assertEqual(self.watch.checkout_threshold, 200)
        with self.assertRaises(ValueError):
            sw.Watch(self.root / 'invalid', checkout_threshold=-1)

    def test_checkout_cache_reports_staleness_and_preserves_last_count_on_failure(self):
        self.watch.checkout_threshold = 1
        self.watch.checkout_cache.update(checkout_count=9, refreshed_at=time.time() - 700)
        with patch.object(self.watch, 'record') as record:
            self.watch.checkout_invariants()
        status = self.watch.store.get('worktree-reaper')
        self.assertEqual(status['checkout_count'], 9)
        self.assertEqual(status['count_status'], 'unavailable')
        self.assertGreaterEqual(status['refresh_age_seconds'], 700)
        self.assertEqual([item['code'] for item in record.call_args[0][2]],
                         ['invariant_unavailable'])
        with patch.object(self.watch, 'checkout_discover', side_effect=OSError('failed')):
            self.watch.refresh_checkout_count()
        self.assertEqual(self.watch.checkout_cache['checkout_count'], 9)
        self.assertEqual(self.watch.checkout_cache['count_errors'], 1)
        with patch.object(self.watch, 'record') as record:
            self.watch.checkout_invariants()
        self.assertEqual([item['code'] for item in record.call_args[0][2]],
                         ['invariant_unavailable'])

    def test_slow_checkout_discovery_cannot_block_real_scans_or_watchdog(self):
        entered, release, scanned, pinged = [threading.Event() for _ in range(4)]
        scans, pings, discoveries = [], [], []
        self.watch.checkout_cache.update(checkout_count=None, refreshed_at=None)
        self.watch.last_scan = time.time()
        def slow_discovery(roots):
            discoveries.append(threading.current_thread().name)
            entered.set()
            if not release.wait(4):
                raise TimeoutError('synthetic discovery deadline')
            return [self.root]
        original_scan = self.watch.scan
        def scan():
            original_scan()
            scans.append(json.loads((self.watch.store.root / 'status.json').read_text()))
            if len(scans) >= 5:
                scanned.set()
        def notify(value):
            if value == 'WATCHDOG=1':
                pings.append(value)
                if len(pings) >= 5:
                    pinged.set()
        daemon = threading.Thread(target=self.watch.serve,
                                  kwargs={'scan_interval': .01, 'watchdog_interval': .01})
        with patch.object(self.watch, 'checkout_discover', slow_discovery), \
                patch.object(self.watch, 'worker', lambda: self.watch.stop.wait()), \
                patch.object(self.watch, 'scan', scan), \
                patch.object(sw, 'properties', return_value={}), \
                patch.object(self.watch, 'phone_caps_invariant'), \
                patch.object(self.watch, 'journals'), \
                patch.object(sw, 'notify_systemd', notify):
            # Discovery can start even while state/model operations hold the Store.
            with self.watch.store.lock:
                daemon.start()
                self.assertTrue(entered.wait(2))
            try:
                self.assertTrue(scanned.wait(2))
                self.assertTrue(pinged.wait(2))
                self.assertFalse(release.is_set())
                self.assertEqual(discoveries, ['service-watch-checkouts'])
                status = self.watch.store.get('worktree-reaper')
                self.assertTrue(status['inflight'])
                self.assertIsNone(status['checkout_count'])
                self.assertEqual(status['count_status'], 'unavailable')
            finally:
                self.watch.stop.set()
                release.set()
                daemon.join(3)
            self.assertFalse(daemon.is_alive())
        self.assertEqual(self.watch.checkout_cache['checkout_count'], 1)
        self.assertFalse(self.watch.checkout_cache['inflight'])
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


    def test_policy_age_ingest_stall_and_offload_violations(self):
        now = time.time()
        home = self.root / 'z0int'
        (home / 'findings').mkdir(parents=True)
        (home / 'policy').mkdir()
        source = self.root / 'source.json'
        source.write_text('changed source')
        finding = {'id': 'latest', 'ts': now - 90000,
                   'source': {'path': str(source), 'sha256': 'old-digest'}}
        (home / 'findings/findings.jsonl').write_text(json.dumps(finding) + '\n')
        (home / 'policy/decision-policy.json').write_text(json.dumps(
            {'compiled_at': now - 8000, 'findings_head': 'older'}))
        (home / 'policy/guard-report.json').write_text(json.dumps(
            {'schema': 'z0.policy_guard.v1', 'ts': now, 'available': True,
             'unavailable_reason': None, 'counts': {'o12_offload_obligation': 2}}))
        with patch.object(self.watch.store, 'notify') as notify:
            self.watch.policy_invariants(home, now)
            notify.assert_called_once()
        row = json.loads(self.watch.store.db.execute('SELECT data FROM incidents').fetchone()[0])
        self.assertEqual({e['code'] for e in row['window']['evidence']},
                         {'policy_stale', 'findings_ingest_stall', 'offload_obligation'})
        self.assertNotIn(str(source), json.dumps(row['window']))

    def test_policy_unavailable_guard_is_explicit_in_digest(self):
        home = self.root / 'z0int'
        (home / 'policy').mkdir(parents=True)
        (home / 'policy/guard-report.json').write_text(json.dumps(
            {'schema': 'z0.policy_guard.v1', 'ts': time.time(), 'available': False,
             'unavailable_reason': 'compiler unavailable', 'counts': {'o12_offload_obligation': 0}}))
        self.watch.policy_invariants(home)
        self.assertFalse(self.watch.store.get('policy-pipeline')['guard_available'])
        self.assertIn('Guard: UNAVAILABLE', self.watch.store.digest().read_text())
        data = json.loads(self.watch.store.db.execute('SELECT data FROM incidents').fetchone()[0])
        self.assertEqual(data['window']['evidence'][0]['code'], 'invariant_unavailable')

    def test_old_policy_without_new_findings_is_not_stale(self):
        now = time.time()
        home = self.root / 'z0int'
        (home / 'findings').mkdir(parents=True)
        (home / 'policy').mkdir()
        source = self.root / 'source.json'
        source.write_text('source')
        finding = {'id': 'same', 'ts': now - 100,
                   'source': {'path': str(source), 'sha256': sw.hashlib.sha256(source.read_bytes()).hexdigest()}}
        (home / 'findings/findings.jsonl').write_text(json.dumps(finding) + '\n')
        (home / 'policy/decision-policy.json').write_text(json.dumps(
            {'compiled_at': now - 90000, 'findings_head': 'same'}))
        (home / 'policy/guard-report.json').write_text(json.dumps(
            {'schema': 'z0.policy_guard.v1', 'ts': now, 'available': True,
             'unavailable_reason': None, 'counts': {'o12_offload_obligation': 0}}))
        self.watch.policy_invariants(home, now)
        self.assertEqual(self.watch.store.db.execute('SELECT count(*) FROM incidents').fetchone()[0], 0)

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
        with patch.object(sw, 'properties', return_value={'fixture.service': {'ActiveState': 'active', 'NRestarts': '30'}}), patch.object(self.watch, 'journals'), patch.object(self.watch, 'loop_invariants'), patch.object(self.watch, 'phone_caps_invariant'), patch.object(self.watch, 'checkout_invariants'), patch.object(self.watch, 'record') as record:
            self.watch.scan()
            self.assertEqual(record.call_args[0][2], [])
        with patch.object(sw, 'properties', return_value={'fixture.service': {'ActiveState': 'active', 'NRestarts': '33'}}), patch.object(self.watch, 'journals'), patch.object(self.watch, 'loop_invariants'), patch.object(self.watch, 'phone_caps_invariant'), patch.object(self.watch, 'checkout_invariants'), patch.object(self.watch, 'record') as record:
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

    def test_slow_model_cannot_block_scans_or_independent_watchdog(self):
        entered = threading.Event()
        release = threading.Event()
        scanned = threading.Event()
        pinged = threading.Event()
        scans, pings, model_threads = [], [], []
        decision = {'severity': 'warn', 'cause': 'synthetic error', 'fix': 'Inspect manually',
                    'evidence': [0], 'confidence': .8}
        self.watch.record('user', 'fixture.service', [sw.event('journal_error_rate', count=5)], ['synthetic error'])
        def slow_model(url, body, timeout=40):
            model_threads.append(threading.current_thread().name)
            entered.set()
            if not release.wait(3):
                raise TimeoutError('synthetic model deadline')
            if url == sw.LOCAL_URL:
                return {'choices': [{'message': {'content': json.dumps(decision)}}]}
            return {'ok': True, 'provider': 'groq', 'model': 'openai/gpt-oss-20b',
                    'output': json.dumps(decision)}
        def scan():
            scans.append(time.monotonic())
            if len(scans) >= 5:
                scanned.set()
        def notify(value):
            if value == 'WATCHDOG=1':
                pings.append(time.monotonic())
                if len(pings) >= 5:
                    pinged.set()
        daemon = threading.Thread(target=self.watch.serve, kwargs={'scan_interval': .01, 'watchdog_interval': .01})
        with patch.object(sw, 'post', slow_model), patch.object(self.watch, 'scan', scan), patch.object(sw, 'notify_systemd', notify):
            daemon.start()
            try:
                self.assertTrue(entered.wait(2))
                # Even a held state lock must not suppress systemd watchdog pings.
                with self.watch.store.lock:
                    self.assertTrue(scanned.wait(2))
                    self.assertTrue(pinged.wait(2))
                self.assertFalse(release.is_set())
                self.assertEqual(set(model_threads), {'service-watch-triage'})
            finally:
                self.watch.stop.set()
                release.set()
                daemon.join(3)
            self.assertFalse(daemon.is_alive())

    def test_watchdog_requires_recent_completed_scan_without_store_lock(self):
        self.watch.scan_watchdog_at = 100
        with self.watch.store.lock, \
                patch.object(self.watch.stop, 'wait', side_effect=[False, False, True]), \
                patch.object(sw.time, 'monotonic', side_effect=[189, 191]), \
                patch.object(sw, 'notify_systemd') as notify:
            self.watch.watchdog(.01)
        self.assertEqual(notify.call_args_list[0].args, ('WATCHDOG=1',))
        self.assertNotIn('WATCHDOG=1', notify.call_args_list[1].args[0])
        self.assertIn('stale', notify.call_args_list[1].args[0])

    def test_stalled_scan_cannot_refresh_watchdog_completion_anchor(self):
        entered, release = threading.Event(), threading.Event()
        self.watch.scan_freshness_seconds = .05
        def stalled_scan():
            entered.set()
            release.wait(3)
        daemon = threading.Thread(target=self.watch.serve,
                                  kwargs={'watchdog_interval': .01})
        stale = threading.Event()
        calls = []
        def notify(value):
            calls.append(value)
            if value.startswith('STATUS='):
                stale.set()
        with patch.object(self.watch, 'scan', stalled_scan), \
                patch.object(self.watch, 'worker', lambda: self.watch.stop.wait()), \
                patch.object(sw, 'notify_systemd', notify):
            daemon.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(stale.wait(2))
                self.assertFalse(release.is_set())
                self.assertLessEqual(self.watch.scan_watchdog_at,
                                     time.monotonic() - .05)
                self.assertFalse((self.watch.store.root / 'status.json').exists())
            finally:
                self.watch.stop.set()
                release.set()
                daemon.join(3)
        self.assertFalse(daemon.is_alive())
        stale_index = next(i for i, value in enumerate(calls) if value.startswith('STATUS='))
        self.assertNotIn('WATCHDOG=1', calls[stale_index:])

    def test_stalled_journal_read_has_real_wall_deadline(self):
        proc = subprocess.Popen([sys.executable, '-c',
                                 'import json,time; print(json.dumps({"MESSAGE":"synthetic"}),flush=True); time.sleep(5)'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            lines = sw.journal_lines(proc, .3)
            self.assertEqual(json.loads(next(lines)), {'MESSAGE': 'synthetic'})
            with self.assertRaises(subprocess.TimeoutExpired):
                list(lines)
            self.assertLess(time.monotonic() - started, 2)
        finally:
            proc.kill()
            proc.communicate()
            proc.stdout.close()

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
