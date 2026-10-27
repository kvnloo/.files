"""Behavioral tests: no phone/network/service installation is used."""
import asyncio
from contextlib import contextmanager
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path

import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import fleet_phone as common
import fleet_phone_controller as controller


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPTS / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


sup = load("phone_supervisor", "fleet-phone-supervisor")
worker = load("phone_worker", "fleet-phone-worker")


def healthy():
    return {"ts": 1000, "mem_available_mb": 3000, "host_lane_supported": True,
            "services": {"sshd": "active"}, "power": {"on_ac": False, "source": "adb",
                "batteries": [{"pct": 80, "status": "Discharging"}],
                "battery_temp_c": 30, "android_thermal_status": 0}}


class TempHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fp-")
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.state = self.home / "s"
        self.state.mkdir()
        self.cwd = self.home / "fleet-jobs/j/src"
        self.cwd.mkdir(parents=True)

    def spec(self, **changes):
        return {"argv": [sys.executable, "-c", "print('PAYLOAD_OK')"], "cwd": str(self.cwd), **changes}


class PolicyTests(unittest.TestCase):
    def test_exponential_bounded_backoff(self):
        p = sup.Policy(base=1, cap=3, burst=8)
        self.assertEqual([p.exited(t, 0) for t in range(5)], [1, 2, 3, 3, 3])

    def test_crash_loop_opens_circuit(self):
        p = sup.Policy(burst=3)
        self.assertEqual([p.exited(t, 0) for t in range(3)], [1, 2, None])
        p.reset()
        self.assertEqual(p.exited(4, 0), 1)

    def test_stable_child_resets_failure_budget(self):
        p = sup.Policy(burst=2, stable=5)
        self.assertEqual(p.exited(1, 0), 1)
        self.assertEqual(p.exited(10, 6), 1)

    def test_invalid_restart_bounds_refused(self):
        with self.assertRaises(common.Blocked):
            sup.Policy(base=0)


class HealthTests(unittest.TestCase):
    def phase(self, p):
        return common.host_health(p, now=1000)[0]

    def test_ready_is_host_lane_not_kubernetes(self):
        self.assertEqual(self.phase(healthy()), "ready")
        self.assertFalse(common.CAPABILITIES["kubernetes_member"])
        self.assertFalse(common.CAPABILITIES["security_isolation"])
        self.assertFalse(common.CAPABILITIES["hard_memory_limit"])

    def test_phone_cannot_report_cluster_ready_even_with_name_collision(self):
        cluster = {"s22": {"conditions": {"Ready": "True"}}}
        self.assertIsNone(common.kubernetes_view({"name": "s22", "kind": "phone"}, cluster))
        self.assertEqual(common.kubernetes_view({"name": "s22", "kind": "linux"}, cluster), cluster["s22"])

    def test_offline_differs_from_stale_and_pause(self):
        self.assertEqual(self.phase({"error": "timeout"}), "unavailable")
        self.assertEqual(self.phase({**healthy(), "ts": 1}), "stale")
        self.assertEqual(self.phase({**healthy(), "paused": True}), "paused")
        self.assertEqual(self.phase({**healthy(), "host_lane_supported": False}), "unsupported")

    def test_missing_resource_telemetry_does_not_gate(self):
        for changes in ({"power": {}}, {"power": None}, {"mem_available_mb": None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.phase({**healthy(), **changes}), "ready")

    def test_battery_thermal_memory_are_observations_not_caps(self):
        p = healthy()
        p.update(mem_available_mb=0, max_temp_c=150)
        p["power"].update(battery_temp_c=80, android_thermal_status=6,
                          batteries=[{"pct": 0, "status": "Discharging"}])
        self.assertEqual(self.phase(p), "ready")

    def test_charging_low_battery_allowed(self):
        p = healthy(); p["power"].update(on_ac=True, batteries=[{"pct": 20}])
        self.assertEqual(self.phase(p), "ready")

    def test_clock_skew_is_stale(self):
        self.assertEqual(self.phase({**healthy(), "ts": 1001}), "stale")

    def test_service_degradation_still_holds(self):
        for service in ("sshd", "fleet-worker"):
            p = healthy()
            p["services"][service] = "down"
            self.assertEqual(self.phase(p), "paused")


class PoliteGateIntegration(TempHome):
    def setUp(self):
        super().setUp()
        self.bin = self.home / "bin"; self.bin.mkdir()
        uname = self.bin / "uname"
        uname.write_text("#!/bin/sh\nprintf 'fixture-android\\n'\n"); uname.chmod(0o700)
        adb = self.bin / "adb"
        adb.write_text("#!/usr/bin/env python3\nimport os,sys\n"
            "if sys.argv[1:]==['devices']: print('List of devices attached\\nfixture\\tdevice')\n"
            "elif sys.argv[-1]=='battery':\n"
            " print('  level: '+os.environ.get('TEST_BATTERY','80'))\n"
            " print('  status: 3\\n  USB powered: false')\n"
            " print('  temperature: '+os.environ.get('TEST_TEMP','300'))\n"
            "elif sys.argv[-1]=='thermalservice': print('Thermal Status: '+os.environ.get('TEST_THERMAL','0'))\n")
        adb.chmod(0o700)

    def gate(self, **env):
        return subprocess.run([str(SCRIPTS / "fleet-polite-run"), "--gate-only"],
            capture_output=True, text=True, env={**os.environ, "PATH": f"{self.bin}:/usr/bin:/bin", **env})

    def test_wrapper_resource_telemetry_does_not_gate(self):
        self.assertEqual(self.gate().returncode, 0)
        for changes in ({"TEST_BATTERY": "0"}, {"TEST_TEMP": "800"}, {"TEST_THERMAL": "6"}):
            self.assertEqual(self.gate(**changes).returncode, 0)

    def test_existing_wrapper_owner_pause_is_respected(self):
        pause = self.home / ".config/fleet/pause"; pause.parent.mkdir(parents=True); pause.touch()
        result = self.gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("paused", result.stderr)

    def test_wrapper_rejects_retired_resource_options(self):
        for option in ("--floor-mb", "--mem-mb", "--cpus"):
            result = subprocess.run([str(SCRIPTS / "fleet-polite-run"), option, "1", "--gate-only"],
                capture_output=True, text=True, env={**os.environ, "PATH": f"{self.bin}:/usr/bin:/bin"})
            self.assertEqual(result.returncode, 2)
            self.assertIn("unknown option", result.stderr)
        if not common.platform_supported():
            unsupported = subprocess.run([str(SCRIPTS / "fleet-polite-run"), "--gate-only"], capture_output=True, text=True)
            self.assertEqual(unsupported.returncode, 78)


class StoreTests(TempHome):
    def setUp(self):
        super().setUp()
        self.store = worker.Store(self.state)


    def test_checked_spec_has_no_resource_defaults(self):
        checked = worker.checked_spec(self.spec())
        self.assertNotIn("mem_mb", checked)
        self.assertNotIn("floor_mb", checked)

    def test_checked_spec_retains_unrestricted_explicit_resource_metadata(self):
        for value in (-100, 0, 1, 10**20):
            with self.subTest(value=value):
                checked = worker.checked_spec(self.spec(mem_mb=value, floor_mb=value))
                self.assertEqual(checked["mem_mb"], value)
                self.assertEqual(checked["floor_mb"], value)

    def test_submit_idempotency_and_conflict(self):
        job = self.store.submit("j", self.spec())
        self.assertEqual(self.store.submit("j", self.spec()), job)
        with self.assertRaises(common.Blocked):
            self.store.submit("j", self.spec(argv=["false"]))
        self.assertEqual(len(self.store.all()), 1)

    def test_traversal_and_cwd_escape_refused(self):
        for jid in ("../x", "x/y", "-x", ""):
            with self.assertRaises(common.Blocked):
                self.store.submit(jid, self.spec())
        with self.assertRaises(common.Blocked):
            self.store.submit("x", self.spec(cwd=str(self.home)))

    def test_retry_requires_explicit_idempotence(self):
        with self.assertRaises(common.Blocked):
            self.store.submit("j", self.spec(max_attempts=2))

    def test_heartbeat_requires_generation_and_nonexpired_lease(self):
        job = self.store.submit("j", self.spec())
        with self.assertRaises(common.Blocked):
            self.store.heartbeat("j", "incorrect", 120)
        self.assertGreater(self.store.heartbeat("j", job["lease"], 300)["expires"], job["expires"])
        job["expires"] = 0; self.store.save(job)
        with self.assertRaises(common.Blocked):
            self.store.heartbeat("j", job["lease"], 120)
        new = self.store.lease("j", 120)
        self.assertNotEqual(new["lease"], job["lease"])

    def test_dead_non_idempotent_job_needs_confirmation(self):
        job = self.store.submit("j", self.spec())
        job.update(state="running", attempt=1, runner={"pid": 999999, "start": "0", "boot": "old"})
        self.store.save(job)
        self.assertEqual(self.store.recover(job)["state"], "needs-confirmation")
        with self.assertRaises(common.Blocked):
            self.store.lease("j", 120)

    def test_live_runner_never_retried_even_expired(self):
        job = self.store.submit("j", self.spec(idempotent=True, max_attempts=3))
        job.update(state="running", attempt=1, runner=common.identity(), expires=0)
        self.store.save(job)
        self.assertEqual(self.store.recover(job)["state"], "running")
        with self.assertRaises(common.Blocked):
            self.store.lease("j", 120)

    def test_confirmed_guest_death_requeues_same_id_bounded(self):
        job = self.store.submit("j", self.spec(idempotent=True, max_attempts=2))
        job.update(state="running", attempt=1, runner={"pid": 999999, "start": "0", "boot": "old"}, expires=0)
        self.store.save(job)
        self.assertEqual(self.store.recover(job)["state"], "queued")
        self.assertEqual(self.store.lease("j", 120)["id"], "j")
        job.update(state="interrupted", attempt=2)
        self.assertEqual(self.store.recover(job)["state"], "needs-confirmation")

    def test_cancel_is_durable_and_cannot_requeue(self):
        self.store.submit("j", self.spec(idempotent=True, max_attempts=2))
        self.store.cancel("j")
        self.assertEqual(self.store.get("j")["state"], "cancelled")
        self.assertTrue(worker.Store(self.state).get("j")["cancel"])

    def test_pid_reuse_is_not_liveness(self):
        fake = {**common.identity(), "start": "wrong"}
        self.assertFalse(common.alive(fake))

    def test_public_status_never_exposes_lease(self):
        job = self.store.submit("j", self.spec())
        self.assertNotIn("lease", worker.public(job))
        self.assertNotIn("spec", worker.public(job))

    def test_spawn_gap_execution_fence_refuses_requeue(self):
        job = self.store.submit("j", self.spec(idempotent=True, max_attempts=3))
        job.update(state="starting", attempt=1, runner={"pid": 999999, "start": "0", "boot": "old"})
        self.store.save(job)
        with common.lock(self.state / "j.exec.lock"):
            self.assertEqual(self.store.recover(job)["state"], "starting")
            with self.assertRaises(common.Blocked):
                self.store.lease("j", 120)
        self.assertEqual(self.store.recover(job)["state"], "queued")
        self.assertEqual(job["expires"], 0)

    def test_reserved_executor_id_refused(self):
        with self.assertRaises(common.Blocked):
            self.store.submit("executor", self.spec())

    def test_platform_failure_is_real_cli_boundary(self):
        if common.platform_supported():
            self.skipTest("desktop-only unsupported-platform probe")
        r = subprocess.run([sys.executable, str(SCRIPTS / "fleet-phone-worker"), "serve", "--state-dir", str(self.state)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 75)
        self.assertIn("unsupported platform", json.loads(r.stdout)["reason"])


class SupervisorIntegration(TempHome):
    def command(self, command, *extra):
        return [sys.executable, str(SCRIPTS / "fleet-phone-supervisor"), command, "--state-dir", str(self.state), *extra]

    def wait_for(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                result = predicate()
                if result:
                    return result
            except (OSError, KeyError):
                pass
            time.sleep(0.02)
        self.fail("fixture did not reach expected state")

    @contextmanager
    def running(self, argv, **config):
        cfg = self.home / "config.json"
        common.atomic(cfg, {"services": {"fixture": argv}, **config})
        proc = subprocess.Popen(self.command("start", "--config", str(cfg)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(lambda: (self.state / "events.sock").exists() or proc.poll() is not None)
            self.assertIsNone(proc.poll())
            yield proc
        finally:
            if proc.poll() is None:
                subprocess.run(self.command("stop"), capture_output=True)
                proc.wait(timeout=20)
            out, err = proc.communicate(timeout=2)
            self.assertEqual(proc.returncode, 0, out + err)

    def test_crash_restart_circuit_and_real_event(self):
        count = self.home / "count"
        code = "from pathlib import Path; p=Path(" + repr(str(count)) + "); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"
        with self.running([sys.executable, "-c", code], restart={"base": 0.02, "cap": 0.04, "burst": 3}):
            self.wait_for(lambda: common.read(self.state / "status.json", {}).get("services", {}).get("fixture", {}).get("state") == "circuit-open")
            self.assertEqual(count.read_text(), "3")
            self.assertTrue(common.notify(self.state, "network-available"))
            self.wait_for(lambda: count.read_text() == "6")
            self.assertEqual(common.read(self.state / "status.json")["network"], "network-available")

    def test_duplicate_start_refused_lock_not_inherited_stop_durable(self):
        with self.running([sys.executable, "-c", "import time; time.sleep(60)"]) as proc:
            duplicate = subprocess.run(self.command("start"), capture_output=True, text=True)
            self.assertEqual(duplicate.returncode, 75)
            info = self.wait_for(lambda: common.read(self.state / "status.json", {}).get("services", {}).get("fixture", {}).get("child"))
            stopped = subprocess.run(self.command("stop"), capture_output=True, text=True)
            self.assertEqual(stopped.returncode, 0)
            proc.wait(timeout=20)
            self.assertFalse(common.alive(info))
        self.assertEqual(sup.desired(self.state), "stopped")
        self.assertTrue((self.home / ".config/fleet/no-autostart").exists())
        restarted = subprocess.run(self.command("start"), capture_output=True, text=True)
        self.assertEqual(restarted.returncode, 0)
        self.assertFalse(json.loads(restarted.stdout)["live"])
        subprocess.run(self.command("resume"), check=True, capture_output=True)
        self.assertEqual(sup.desired(self.state), "enabled")
        self.assertFalse((self.home / ".config/fleet/no-autostart").exists())
        with common.lock(self.state / "instance.lock", blocking=False):
            pass

    def test_legacy_runit_lock_excludes_new_tree(self):
        with common.lock(self.home / ".local/state/fleet/supervise/lock"):
            r = subprocess.run(self.command("start"), capture_output=True, text=True)
            self.assertEqual(r.returncode, 75)

    def test_empty_config_fails_without_starting(self):
        cfg = self.home / "config.json"; common.atomic(cfg, {"services": {}})
        r = subprocess.run(self.command("start", "--config", str(cfg)), capture_output=True, text=True)
        self.assertEqual(r.returncode, 75)
        self.assertFalse((self.state / "events.sock").exists())

    def test_supervisor_crash_releases_lock_and_terminates_foreground_child(self):
        cfg = self.home / "config.json"
        common.atomic(cfg, {"services": {"fixture": [sys.executable, "-c", "import time; time.sleep(60)"]}})
        proc = subprocess.Popen(self.command("start", "--config", str(cfg)), stdout=subprocess.DEVNULL)
        try:
            child = self.wait_for(lambda: common.read(self.state / "status.json", {}).get("services", {}).get("fixture", {}).get("child"))
            # Wait until setpriv has exec'd the actual fixture: pdeathsig is installed.
            self.wait_for(lambda: b"time.sleep(60)" in Path(f"/proc/{child['pid']}/cmdline").read_bytes())
            proc.kill(); proc.wait(timeout=5)
            self.wait_for(lambda: not common.alive(child))
            with common.lock(self.state / "instance.lock", blocking=False):
                pass
            self.assertEqual(sup.desired(self.state), "enabled")
        finally:
            if proc.poll() is None:
                proc.terminate(); proc.wait(timeout=20)


class ExecutionIntegration(TempHome):
    def setUp(self):
        super().setUp()
        self.store = worker.Store(self.state)
        self.polite = self.home / "fixture-polite"
        self.polite.write_text("#!/usr/bin/env python3\nimport os,sys\na=sys.argv[1:]\nif '--gate-only' in a: sys.exit(0)\ni=a.index('--'); os.execvp(a[i+1],a[i+1:])\n")
        self.polite.chmod(0o700)

    def test_real_wrapper_executes_with_unrestricted_resource_metadata(self):
        tools = self.home / "bin"
        tools.mkdir()
        uname = tools / "uname"
        uname.write_text("#!/bin/sh\nprintf 'fixture-android\\n'\n")
        uname.chmod(0o700)
        job = self.store.submit("j", self.spec(mem_mb=10**20, floor_mb=-100))
        with patch.dict(os.environ, {"PATH": f"{tools}:{os.environ['PATH']}"}):
            asyncio.run(worker.Executor(self.store, SCRIPTS / "fleet-polite-run").execute(job))
        self.assertEqual(self.store.get("j")["state"], "succeeded")
        self.assertIn("PAYLOAD_OK", (self.state / "j.log").read_text())

    def test_payload_runs_once_logs_status_duplicate_and_no_credential_home(self):
        count = self.cwd / "count"
        code = "from pathlib import Path; import os; p=Path('count'); p.write_text('1'); print('PAYLOAD_OK'); print(os.environ['HOME'])"
        job = self.store.submit("j", self.spec(argv=[sys.executable, "-c", code]))
        executor = worker.Executor(self.store, self.polite)
        asyncio.run(executor.execute(job))
        asyncio.run(executor.execute(self.store.submit("j", self.spec(argv=[sys.executable, "-c", code]))))
        self.assertEqual(count.read_text(), "1")
        result = self.store.get("j")
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["attempt"], 1)
        log = (self.state / "j.log").read_text()
        self.assertIn("PAYLOAD_OK", log)
        self.assertIn(str(self.home.resolve() / "fleet-jobs/j/home"), log)

    def test_expired_lease_does_not_start_payload(self):
        job = self.store.submit("j", self.spec(), ttl=-1)
        asyncio.run(worker.Executor(self.store, self.polite).execute(job))
        self.assertEqual(self.store.get("j")["attempt"], 0)
        self.assertFalse((self.state / "j.log").exists())

    def test_failed_gate_leaves_queued_not_admitted(self):
        job = self.store.submit("j", self.spec())
        with patch.object(worker, "gate", return_value=False):
            asyncio.run(worker.Executor(self.store, self.polite).execute(job))
        self.assertEqual(self.store.get("j")["state"], "queued")
        self.assertEqual(self.store.get("j")["attempt"], 0)

    def test_running_lease_expiry_drains_then_requires_confirmation(self):
        job = self.store.submit("j", self.spec(argv=[sys.executable, "-c", "import time; time.sleep(60)"]), ttl=0.15)
        asyncio.run(worker.Executor(self.store, self.polite).execute(job))
        result = self.store.get("j")
        self.assertEqual(result["state"], "needs-confirmation")
        self.assertFalse(common.alive(result["child"]))

    def test_concurrent_attempts_cannot_duplicate_effect(self):
        code = "from pathlib import Path; p=Path('effects'); p.open('a').write('effect\\n')"
        job = self.store.submit("j", self.spec(argv=[sys.executable, "-c", code]))
        async def attempts():
            await asyncio.gather(worker.Executor(self.store, self.polite).execute(job),
                                 worker.Executor(self.store, self.polite).execute(job))
        asyncio.run(attempts())
        self.assertEqual((self.cwd / "effects").read_text().splitlines(), ["effect"])
        self.assertEqual(self.store.get("j")["attempt"], 1)

    def test_executor_real_event_submit_and_cancel(self):
        async def scenario():
            executor = worker.Executor(self.store, self.polite)
            with patch.object(worker, "platform_supported", return_value=True):
                serving = asyncio.create_task(executor.run())
                for _ in range(100):
                    if (self.state / "events.sock").exists():
                        break
                    await asyncio.sleep(0.01)
                self.store.submit("j", self.spec(argv=[sys.executable, "-c", "import time; time.sleep(60)"]))
                for _ in range(200):
                    if self.store.get("j")["state"] == "running":
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(self.store.get("j")["state"], "running")
                self.store.cancel("j")
                for _ in range(200):
                    if self.store.get("j")["state"] == "cancelled":
                        break
                    await asyncio.sleep(0.01)
                executor.stop.set(); executor.wake.set()
                await asyncio.wait_for(serving, 5)
                self.assertEqual(self.store.get("j")["state"], "cancelled")
        asyncio.run(scenario())


class ControllerTests(TempHome):
    def test_real_openssh_consumer_uses_strict_first_policy(self):
        argv = controller.strict_ssh(["ssh", "-F", "/dev/null", "-o", "StrictHostKeyChecking=no",
                                      "-o", "ControlMaster=auto", "host.invalid"])
        argv.insert(1, "-G")
        result = subprocess.run(argv, capture_output=True, text=True, check=True)
        config = dict(line.split(" ", 1) for line in result.stdout.splitlines())
        self.assertIn(config["stricthostkeychecking"], ("true", "yes"))
        self.assertIn(config["controlmaster"], ("false", "no"))
        self.assertEqual(config.get("controlpath", "none"), "none")

    def test_offline_cancel_persists_and_paused_rejoin_cancels_not_renews(self):
        with patch.object(controller, "transport", side_effect=common.Blocked("offline")):
            result = controller.cancel(self.state, "phone", "j", ["ssh", "host"])
        self.assertEqual(result["state"], "cancel-pending")
        path = controller.records(self.state, "phone") / "j.json"
        self.assertTrue(common.read(path)["cancel"])
        controller.update_record(path, {"state": "running", "cancel": False})
        self.assertTrue(common.read(path)["cancel"])
        probe = {**healthy(), "ts": time.time(), "paused": True}
        with patch.object(controller, "transport", return_value={"state": "cancelled"}) as transport:
            controller.reconcile(self.state, "phone", probe, ["ssh", "host"])
        self.assertEqual(transport.call_args.args[1], "cancel")
        self.assertTrue(common.read(path)["terminal"])

    def test_transport_enforces_pins_and_hides_credentials_from_argv(self):
        result = subprocess.CompletedProcess([], 0, stdout='{"state":"running"}', stderr="secret diagnostic")
        with patch.object(controller.subprocess, "run", return_value=result) as run:
            controller.transport(["ssh", "root@100.1.2.3"], "heartbeat", "j", {"lease": "SECRET"})
        argv = run.call_args.args[0]
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("ControlPath=none", argv)
        self.assertNotIn("SECRET", " ".join(argv))
        self.assertIn("SECRET", run.call_args.kwargs["input"])

    def test_failed_transport_never_exposes_raw_diagnostics(self):
        result = subprocess.CompletedProcess([], 255, stdout="", stderr="SECRET")
        with patch.object(controller.subprocess, "run", return_value=result):
            with self.assertRaises(common.Blocked) as ctx:
                controller.transport(["ssh", "host"], "status", "j")
        self.assertNotIn("SECRET", str(ctx.exception))

    def test_offline_rejoin_only_recovers_owned_same_id(self):
        directory = controller.records(self.state, "phone")
        common.atomic(directory / "j.json", {"id": "j", "lease": "TOKEN", "terminal": False})
        with patch.object(controller, "transport") as transport:
            controller.reconcile(self.state, "phone", {"error": "offline"}, ["ssh", "host"])
            transport.assert_not_called()
        self.assertEqual(common.read(directory / "j.json")["availability"], "unavailable")
        p = healthy(); p["ts"] = time.time()
        with patch.object(controller, "transport", side_effect=[{"state": "queued"}, {"lease": "NEW"}, {"state": "queued"}]) as transport:
            controller.reconcile(self.state, "phone", p, ["ssh", "host"])
        self.assertEqual([c.args[1] for c in transport.call_args_list], ["recover", "lease", "heartbeat"])
        self.assertTrue(all(c.args[2] == "j" for c in transport.call_args_list))
        self.assertEqual(common.read(directory / "j.json")["lease"], "NEW")

    def test_stale_and_paused_do_not_renew_execution(self):
        directory = controller.records(self.state, "phone")
        common.atomic(directory / "j.json", {"id": "j", "lease": "TOKEN", "terminal": False})
        for probe in (healthy(), {**healthy(), "ts": time.time(), "paused": True}):
            with patch.object(controller, "transport") as transport:
                controller.reconcile(self.state, "phone", probe, ["ssh", "host"])
                transport.assert_not_called()


class RolloutTests(TempHome):
    def test_setup_without_telemetry_installs_without_starting_tree(self):
        tools = self.home / "bin"
        tools.mkdir()
        calls = self.home / "calls"
        ssh = tools / "ssh"
        ssh.write_text("#!/bin/sh\n"
                       'printf "%s\\n" "$*" >> "$CALLS"\n'
                       'case "$*" in\n'
                       '  *"for s in "*) exit 1 ;;\n'
                       '  *"tar -xf"*) cat >/dev/null ;;\n'
                       'esac\n')
        ssh.chmod(0o755)
        env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "CALLS": str(calls)}
        command = ["bash", str(SCRIPTS / "fleet-phone-setup.sh"), "root@phone.invalid"]
        for options in ([], ["--defer-adb"]):
            with self.subTest(options=options):
                installed = subprocess.run([*command, *options], env=env, capture_output=True, text=True)
                self.assertEqual(installed.returncode, 0, installed.stderr)
                self.assertIn("self-ADB unavailable; fleet jobs remain available", installed.stderr)
                self.assertIn("API installed (not started)", installed.stdout)
        self.assertIn("tar -xf", calls.read_text())
        text = calls.read_text()
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("sv/fleet-worker", text)
        self.assertNotIn("fleet-phone-supervise up", text)
        self.assertNotIn("fleet-phone-supervise down", text)

    def test_battery_does_not_gate_but_executor_readiness_does(self):
        p = healthy()
        p["power"]["batteries"][0]["pct"] = 0
        self.assertEqual(common.host_health(p, now=1000)[0], "ready")
        p["power"]["on_ac"] = True
        self.assertEqual(common.host_health(p, now=1000)[0], "ready")
        p["services"]["fleet-worker"] = "down"
        self.assertEqual(common.host_health(p, now=1000)[0], "paused")


if __name__ == "__main__":
    unittest.main()
