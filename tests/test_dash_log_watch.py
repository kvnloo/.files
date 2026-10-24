"""Pure-stdlib deterministic watcher contracts; no phone/provider calls."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("dashwatch", Path(__file__).resolve().parents[1] / "scripts/dash-log-watch.py")
assert SPEC is not None and SPEC.loader is not None
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


class GateTests(unittest.TestCase):
    def test_config_requires_exact_qualified_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "helper.py"
            helper.write_text("synthetic helper identity fixture")
            qualification = root / "qualification.json"
            qualification.write_text(json.dumps({"ok": True, "provider": "openai-codex", "requested_model": w.MODEL,
                "returned_model": w.MODEL, "catalog": {"slug": w.MODEL, "fresh": True}}))
            config = {"package": w.PACKAGE, "model": w.MODEL, "provider": "openai-codex",
                "hardware_serial": "R5CY93G2WNH", "phone_host": "100.117.226.39", "units": w.UNITS,
                "concurrency": 3, "calls_per_hour": 6, "reserved_tokens_per_hour": 30000, "debounce_seconds": 2,
                "helper": str(helper), "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
                "qualification": str(qualification)}
            w.validate(config)
            for key, invalid in (("package", "host.exp.exponent"), ("provider", "nous"),
                                 ("model", "openai-codex/gpt-6-luna"), ("concurrency", 4),
                                 ("hardware_serial", "OTHER"), ("helper_sha256", "bad")):
                with self.assertRaises(ValueError):
                    w.validate({**config, key: invalid})
            qualification.write_text(json.dumps({"ok": False, "returned_model": "other"}))
            with self.assertRaises(ValueError):
                w.validate(config)

    def test_snapshot_exact_native(self):
        self.assertEqual(w.foreground_snapshot("topResumedActivity=ActivityRecord{abc u0 app.dash.mobile/.MainActivity t1}"), "ACTIVE")
        for package in ("host.exp.exponent", "app.dash.mobile.fake", "other.app"):
            self.assertEqual(w.foreground_snapshot(f"topResumedActivity=ActivityRecord{{abc u0 {package}/.MainActivity t1}}"), "BACKGROUND")
        self.assertEqual(w.foreground_snapshot("websocket connected"), "UNKNOWN")

    def test_activity_lifecycle(self):
        gained = "wm_on_top_resumed_gained_called: [10,app.dash.mobile.MainActivity,topStateChanged]"
        self.assertEqual(w.foreground_event(gained, "BACKGROUND"), "ACTIVE")
        for tag in ("wm_on_top_resumed_lost_called", "wm_on_paused_called", "wm_on_stop_called"):
            self.assertEqual(w.foreground_event(f"{tag}: [10,app.dash.mobile.MainActivity,reason]", "ACTIVE"), "BACKGROUND")
        self.assertEqual(w.foreground_event("wm_set_resumed_activity: [0,app.dash.mobile/.MainActivity,reason]", "UNKNOWN"), "UNKNOWN")
        self.assertEqual(w.foreground_event("wm_on_top_resumed_gained_called: [10,host.exp.exponent.MainActivity,reason]", "ACTIVE"), "BACKGROUND")
        self.assertEqual(w.foreground_event("wm_on_top_resumed_gained_called: [10,app.dash.mobile.fake.MainActivity,reason]", "UNKNOWN"), "BACKGROUND")

    def test_classification_allowlist(self):
        self.assertEqual(w.classify("Bundled in 100ms websocket connected"), [])
        self.assertEqual(w.classify("TypeError: PRIVATE chat https://user:password@secret.example/?token=sk-xyz"), ["js_type_error"])
        self.assertEqual(w.classify(["TypeError:"]), [])
        self.assertEqual(w.classify("TypeError:" + "x" * 65536), [])


class WatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {"hardware_serial": "R5CY93G2WNH", "qualification": "synthetic-test-only",
                       "concurrency": 3, "calls_per_hour": 6, "reserved_tokens_per_hour": 30000,
                       "debounce_seconds": 0.01, "hermes_home": "/not-used", "helper": "/not-used", "helper_sha256": "fixture"}
        self.watch = w.Watch(self.config, self.tmp.name, fixture=True)
        self.calls = []
        async def review(seat, batch):
            self.calls.append((seat, batch))
        self.watch.review = review

    async def asyncTearDown(self):
        if self.watch.flush_task:
            await self.watch.flush_task
        await asyncio.gather(*self.watch.running, return_exceptions=True)
        if self.watch.status_pending:
            self.watch.status_pending.cancel()
        self.watch.db.close()

    def event(self, message="TypeError: private", source="dash-metro-native-8108.service", cursor="cursor1"):
        self.watch.event({"MESSAGE": message, "_SYSTEMD_USER_UNIT": source, "__CURSOR": cursor})

    async def flush(self):
        if self.watch.flush_task:
            await self.watch.flush_task
        await asyncio.gather(*self.watch.running)

    async def test_unknown_background_no_models(self):
        self.event()
        self.watch.set_gate("BACKGROUND")
        self.event(cursor="cursor2")
        await self.flush()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.watch.counts["background_dropped"], 2)
        self.assertEqual(self.watch.meta("journal_cursor"), "cursor2")

    async def test_healthy_zero(self):
        self.watch.set_gate("ACTIVE")
        for _ in range(100):
            self.event("healthy bundled connected")
        await self.flush()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.watch.counts["model_calls"], 0)

    async def test_runtime_dedup_and_no_raw_text(self):
        self.watch.set_gate("ACTIVE")
        self.event("TypeError: CHAT PROMPT PRIVATE token=sk-secret https://user:pw@private.invalid")
        self.event("TypeError: different details")
        await self.flush()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], "runtime")
        outbound = json.dumps(self.calls)
        for text in ("CHAT", "PROMPT", "PRIVATE", "sk-secret", "https:", "different details"):
            self.assertNotIn(text, outbound)
        evidence = self.calls[0][1][0]
        self.assertEqual(len(evidence["evidence_sha256"]), 64)
        self.assertEqual(evidence["cursor"], "cursor1")
        self.assertEqual(self.watch.counts["deduplicated"], 1)

    async def test_bridge_routing(self):
        self.watch.set_gate("ACTIVE")
        self.event("[bridge] failed ECONNRESET", "dash-bridge-4747.service")
        await self.flush()
        self.assertEqual(self.calls[0][0], "bridge")

    async def test_crosscutting_is_one_not_three(self):
        self.watch.set_gate("ACTIVE")
        self.event()
        self.event("ECONNRESET", "dash-bridge-4747.service")
        await self.flush()
        self.assertEqual([seat for seat, _ in self.calls], ["correlation"])

    async def test_critical_correlation(self):
        self.watch.set_gate("ACTIVE")
        self.event("JavaScript heap out of memory")
        await self.flush()
        self.assertEqual(self.calls[0][0], "correlation")

    async def test_background_cancels_pending_and_reentry(self):
        self.watch.set_gate("ACTIVE")
        self.event()
        self.watch.set_gate("BACKGROUND")
        self.watch.set_gate("ACTIVE")
        self.event("ReferenceError: fresh")
        await self.flush()
        # A second debounce window is intentionally owned by the new foreground generation.
        if self.watch.flush_task:
            await self.watch.flush_task
        await asyncio.gather(*self.watch.running)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1][0]["codes"], ["js_reference_error"])

    async def test_transport_loss_cannot_admit_stale_active(self):
        self.watch.transport_online = False
        self.watch.set_gate("ACTIVE")
        self.event()
        await self.flush()
        self.assertEqual(self.watch.gate, "UNKNOWN")
        self.assertEqual(self.calls, [])

    async def test_hourly_budget_persists(self):
        self.watch.config["calls_per_hour"] = 1
        self.watch.set_gate("ACTIVE")
        self.event()
        await self.flush()
        self.event("ReferenceError: second")
        await self.flush()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.watch.counts["budget_dropped"], 1)
        other = w.Watch(self.config, self.tmp.name, fixture=True)
        self.assertEqual(other.db.execute("SELECT count(*) FROM admissions").fetchone()[0], 1)
        self.assertEqual(other.meta("journal_cursor"), "cursor1")
        other.db.close()

    async def test_concurrency_cap_and_local_backpressure(self):
        stop = asyncio.Event()
        active = 0
        maximum = 0
        async def hold(seat, batch):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await stop.wait()
            active -= 1
        self.watch.review = hold
        self.watch.set_gate("ACTIVE")
        for code, source in (("TypeError:", "dash-metro-native-8108.service"),
                             ("ECONNREFUSED", "dash-bridge-4747.service"),
                             ("OutOfMemoryError", "dash-metro-native-8108.service"),
                             ("ReferenceError:", "dash-metro-native-8108.service")):
            self.event(code, source)
            await self.watch.flush_task
            await asyncio.sleep(0)
        self.assertEqual(maximum, 3)
        self.assertEqual(self.watch.counts["model_calls"], 3)
        self.assertEqual(self.watch.counts["backpressure"], 1)
        self.assertEqual(self.watch.counts["incidents"], 1)
        stop.set()
        await asyncio.gather(*self.watch.running)

    async def test_pending_bound(self):
        self.watch.set_gate("ACTIVE")
        samples = ["TypeError:", "ReferenceError:", "SyntaxError:", "ECONNRESET", "ECONNREFUSED", "ETIMEDOUT", "Cannot find module", "OutOfMemoryError", "uncaughtException", "FATAL EXCEPTION:"]
        for source in w.UNITS.values():
            for number, message in enumerate(samples):
                self.watch.event({"MESSAGE": message, "__CURSOR": str(number)}, source=source)
        self.assertEqual(len(self.watch.pending), 24)
        self.assertEqual(self.watch.counts["backpressure"], 16)
        await self.flush()

    async def test_track_devices_wire_framing_and_loss(self):
        reader = asyncio.StreamReader()
        payload = b"100.117.226.39:39815\tdevice\n"
        reader.feed_data(f"{len(payload):04x}".encode() + payload)
        class Proc:
            stdout = reader
            returncode = 0
        self.watch.endpoint = lambda: "100.117.226.39:39815"
        with patch.object(w.asyncio, "create_subprocess_exec", return_value=Proc()):
            task = asyncio.create_task(self.watch.transport())
            await asyncio.sleep(0.01)
            self.assertTrue(self.watch.transport_online)
            self.watch.set_gate("ACTIVE")
            reader.feed_data(b"0000")
            await asyncio.sleep(0.01)
            self.assertEqual(self.watch.gate, "UNKNOWN")
            self.assertFalse(self.watch.transport_online)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_invalid_cursor_resets_to_now_not_old_flood(self):
        self.watch.checkpoint("journal_cursor", "vacuumed-fixture-cursor")
        reader = asyncio.StreamReader()
        reader.feed_eof()
        class Proc:
            stdout = reader
            returncode = 1
        paused = asyncio.Event()
        never = asyncio.Event()
        async def pause(delay):
            paused.set()
            await never.wait()
        with patch.object(w.asyncio, "create_subprocess_exec", return_value=Proc()) as spawn, patch.object(w.asyncio, "sleep", side_effect=pause):
            task = asyncio.create_task(self.watch.journal())
            await paused.wait()
            argv = spawn.call_args.args
            self.assertIn("--after-cursor", argv)
            self.assertIn("--since=-2min", argv)
            self.assertEqual(self.watch.meta("journal_cursor"), "")
            self.assertEqual(self.watch.counts["cursor_gaps"], 1)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_report_retention_and_permission(self):
        # Suppress only fsync in this many-file retention test; permission test uses real atomic writes.
        with patch.object(w.os, "fsync"):
            for index in range(202):
                self.watch.local_report({"seat": "runtime", "index": index})
            reports = list((Path(self.tmp.name) / "incidents").glob("*.json"))
            self.assertEqual(len(reports), 200)
            old = reports[0]
            expired = time.time() - 8 * 86400
            os.utime(old, (expired, expired))
            self.watch.local_report({"seat": "runtime", "index": 203})
            self.assertFalse(old.exists())
            existing = next((Path(self.tmp.name) / "incidents").glob("*.json"))
            self.assertEqual(existing.stat().st_mode & 0o777, 0o600)

    async def test_restart_dedup_and_permissions(self):
        self.watch.set_gate("ACTIVE")
        self.event()
        await self.flush()
        self.assertEqual(os.stat(Path(self.tmp.name) / "status.json").st_mode & 0o777, 0o600)
        other = w.Watch(self.config, self.tmp.name, fixture=True)
        other.set_gate("ACTIVE")
        other.event({"MESSAGE": "TypeError:", "_SYSTEMD_USER_UNIT": "dash-metro-native-8108.service"})
        self.assertEqual(other.pending, [])
        self.assertEqual(other.counts["deduplicated"], 1)
        other.db.close()

    async def test_provider_timeout_kills_and_unavailable(self):
        class Proc:
            pid = 1234
            returncode = None
            async def communicate(self, data):
                raise TimeoutError()
            async def wait(self):
                self.returncode = -9
        proc = Proc()
        with patch.object(w.asyncio, "create_subprocess_exec", return_value=proc), patch.object(w.os, "killpg") as kill:
            await w.Watch.review(self.watch, "runtime", [{"codes": ["js_type_error"]}])
            kill.assert_called_once_with(1234, w.signal.SIGKILL)
        self.assertFalse(self.watch.review_available)
        self.assertEqual(self.watch.counts["model_failures"], 1)
        self.watch.set_gate("ACTIVE")
        self.event()
        await self.flush()
        self.assertEqual(self.calls, [])

    async def test_model_mismatch_rejected(self):
        class Proc:
            returncode = 0
            async def communicate(self, data):
                return json.dumps({"ok": True, "provider": "nous", "returned_model": "gpt-6-luna"}).encode(), b""
        with patch.object(w.asyncio, "create_subprocess_exec", return_value=Proc()):
            await w.Watch.review(self.watch, "bridge", [])
        report = json.loads(next((Path(self.tmp.name) / "incidents").glob("*.json")).read_text())
        self.assertEqual(report["result"]["code"], "model_mismatch")
        self.assertFalse(self.watch.review_available)


if __name__ == "__main__":
    unittest.main()
