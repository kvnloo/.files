"""No SSH, device, build, kubectl or install effects. Runs on an ordinary laptop.

Exhaustive Python decision table and mocked real scripts/fleet boundary. The
shell cases terminate before any registered worker is contacted.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from fleet_admission import (Admit, Prepare, Reason, Refuse, Request, Target,
                             Transfer, decide, reason_text, verdict_code)


def expected(target, qualified, available, room, transfer):
    """Independent declarative truth table; not a second scheduler."""
    if target is Target.MISSING:
        return Refuse(Reason.NO_REMOTE)
    if target is Target.GROOT:
        return Refuse(Reason.GROOT_FORBIDDEN)
    if not qualified:
        return Refuse(Reason.UNQUALIFIED)
    if not available:
        return Refuse(Reason.UNAVAILABLE)
    if not room:
        return Refuse(Reason.NO_ROOM)
    if transfer is Transfer.FAILED:
        return Refuse(Reason.SOURCE_TRANSFER_FAILED)
    return Prepare() if transfer is Transfer.PENDING else Admit()


def load_fleet():
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("fleet_under_test", str(SCRIPTS / "fleet"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def registry_fixture():
    lane = {"mem_floor_mb": 256, "default_mem": "256M", "cpu_quota": "100%"}
    mbp = {"name": "mbp", "role": "worker", "lane_enabled": True,
           "classes": ["build"], "capabilities": [], "arch": "amd64",
           "taints": [], "lane": lane, "k8s": False, "kind": "linux"}
    groot = {"name": "groot", "role": "server", "lane_enabled": False,
             "classes": ["render"], "capabilities": [], "arch": "amd64",
             "taints": [], "lane": lane, "k8s": True, "kind": "linux"}
    return {}, {"mbp": mbp, "groot": groot}


def fake_args(source, node="mbp", cls="build"):
    return types.SimpleNamespace(cmd=["echo", "REMOTE_ONLY"], node=node, cls=cls,
                                 arch=None, tolerate=None, mem=None, cpus=None,
                                 timeout=5, src=str(source), no_src=False,
                                 fetch=None, keep=True)


class PureLawTests(unittest.TestCase):
    def test_exhaustive_96_state_table(self):
        cases = itertools.product(Target, (False, True), (False, True),
                                  (False, True), Transfer)
        for target, qualified, available, room, transfer in cases:
            with self.subTest(target=target, qualified=qualified, available=available,
                              room=room, transfer=transfer):
                request = Request(target, qualified, available, room, transfer)
                got = decide(request)
                self.assertEqual(got, expected(target, qualified, available, room, transfer))
                self.assertIn(verdict_code(got), range(8))
                if isinstance(got, Refuse):
                    text = reason_text(got)
                    self.assertTrue(text.startswith("Refuse[" + got.reason.value + "]: "))
                    self.assertTrue(text.split(": ", 1)[1])
                if isinstance(got, Admit):
                    self.assertIs(target, Target.REMOTE)
                    self.assertTrue(qualified and available and room)
                    self.assertIn(transfer, (Transfer.COMPLETE, Transfer.NOT_REQUIRED))

    def test_malformed_observations_never_admit(self):
        cases = [
            Request("groot", True, True, True, Transfer.COMPLETE),
            Request(Target.REMOTE, 1, True, True, Transfer.COMPLETE),
            Request(Target.REMOTE, True, None, True, Transfer.COMPLETE),
            Request(Target.REMOTE, True, True, True, "complete"),
        ]
        for request in cases:
            with self.subTest(request=request):
                result = decide(request)
                self.assertIsInstance(result, Refuse)
                self.assertTrue(reason_text(result))

    def test_fail_closed_without_fallback(self):
        for transfer in Transfer:
            for available in (False, True):
                got = decide(Request(Target.GROOT, True, available, True, transfer))
                self.assertEqual(got, Refuse(Reason.GROOT_FORBIDDEN))
        self.assertEqual(decide(Request(Target.REMOTE, True, True, True,
                                        Transfer.FAILED)),
                         Refuse(Reason.SOURCE_TRANSFER_FAILED))
        self.assertIsInstance(decide(Request(Target.REMOTE, True, True, True,
                                             Transfer.PENDING)), Prepare)


class FleetAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source"
        self.source.mkdir()
        self.fleet = load_fleet()
        self.fleet.STATE = Path(self.tmp.name) / "fleet-state"
        self.real_registry = self.fleet.registry
        self.reg = mock.patch.object(self.fleet, "registry", return_value=registry_fixture())
        self.k8s = mock.patch.object(self.fleet, "k8s_nodes", return_value={})
        self.reg.start(); self.k8s.start()
        self.addCleanup(self.reg.stop); self.addCleanup(self.k8s.stop)

    def refusing(self, args, needle, probe_value=None):
        if probe_value is None:
            probe_value = {"mem_available_mb": 4096, "load1": 0.0, "ncpu": 2}
        with mock.patch.object(self.fleet, "probe", return_value=probe_value), \
             mock.patch.object(self.fleet, "ssh_cmd",
                               side_effect=AssertionError("must not build SSH command")), \
             mock.patch.object(self.fleet.subprocess, "Popen",
                               side_effect=AssertionError("must not launch process")), \
             contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                self.fleet.cmd_run(args)
        self.assertEqual(caught.exception.code, 75)
        self.assertIn("Refuse[" + needle + "]", output.getvalue())

    def test_pin_unknown_unqualified_and_groot(self):
        self.refusing(fake_args(self.source, node="absent"), "NO_REMOTE")
        self.refusing(fake_args(self.source, cls="android-build"), "UNQUALIFIED")
        self.refusing(fake_args(self.source, node="groot", cls="render"), "GROOT_FORBIDDEN")

    def test_probe_unavailable_and_no_room(self):
        self.refusing(fake_args(self.source), "UNAVAILABLE", {"error": "offline"})
        self.refusing(fake_args(self.source), "UNAVAILABLE",
                      {"mem_available_mb": None, "load1": 0, "ncpu": 2})
        self.refusing(fake_args(self.source), "UNAVAILABLE",
                      {"mem_available_mb": float("nan"), "load1": 0, "ncpu": 2})
        self.refusing(fake_args(self.source), "UNAVAILABLE",
                      {"mem_available_mb": 4096, "load1": float("inf"), "ncpu": 2})
        self.refusing(fake_args(self.source), "NO_ROOM",
                      {"mem_available_mb": 400, "load1": 0, "ncpu": 2})

    def test_poisoned_groot_lane_refuses_before_probe(self):
        _, nodes = registry_fixture()
        nodes["groot"].update(role="worker", lane_enabled=True, classes=["build"])
        with mock.patch.object(self.fleet, "registry", return_value=({}, nodes)), \
             mock.patch.object(self.fleet, "probe",
                               side_effect=AssertionError("groot must not be probed")), \
             mock.patch.object(self.fleet, "ssh_cmd",
                               side_effect=AssertionError("must not construct SSH")), \
             contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                self.fleet.cmd_run(fake_args(self.source, node="groot"))
        self.assertEqual(caught.exception.code, 75)
        self.assertIn("Refuse[GROOT_FORBIDDEN]: ", output.getvalue())

    def test_auto_without_healthy_mbp_never_falls_back(self):
        _, nodes = registry_fixture()
        nodes["groot"].update(lane_enabled=True, classes=["build"])
        observed = []

        def offline(node):
            observed.append(node["name"])
            return {"error": "offline"}

        with mock.patch.object(self.fleet, "registry", return_value=({}, nodes)), \
             mock.patch.object(self.fleet, "probe", side_effect=offline), \
             mock.patch.object(self.fleet, "ssh_cmd",
                               side_effect=AssertionError("must not construct SSH")), \
             contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                self.fleet.cmd_run(fake_args(self.source, node="auto"))
        self.assertEqual(caught.exception.code, 75)
        self.assertIn("Refuse[UNAVAILABLE]: ", output.getvalue())
        self.assertEqual(observed, ["mbp"])

    def run_mocked_transfer(self, tar_code, extract_code, runtime_code=None, *,
                            git_source=False, spawn_error=None, broken_pipe=False,
                            no_src=False, real_registry=False, node="mbp"):
        """Exercise the actual cmd_run seam, with all process effects replaced."""
        def process(rc, stdout):
            p = mock.Mock()
            p.stdout = stdout
            p.stdin = io.BytesIO()
            p.wait.return_value = rc
            p.poll.return_value = rc
            p.returncode = rc
            return p

        tar = process(tar_code, io.BytesIO(b"archive bytes"))
        send = process(extract_code, io.BytesIO())
        if git_source:
            (self.source / ".git").mkdir()
        if broken_pipe:
            tar.stdin = mock.Mock()
            tar.stdin.write.side_effect = BrokenPipeError("producer closed stdin")
        results = [tar, send]
        if spawn_error == "tar":
            results = [OSError("tar spawn failed")]
        elif spawn_error == "extract":
            results = [tar, OSError("extract spawn failed")]
        if runtime_code is not None:
            runtime = process(runtime_code, [])
            results = [runtime] if no_src else [*results, runtime]
        args = fake_args(self.source, node=node)
        args.no_src = no_src
        registry = self.real_registry() if real_registry else registry_fixture()
        with mock.patch.object(self.fleet, "registry", return_value=registry), \
             mock.patch.object(self.fleet, "probe", return_value={
                 "mem_available_mb": 16384, "load1": 0.0, "ncpu": 8}), \
             mock.patch.object(self.fleet, "ssh_cmd", return_value=["fake-ssh"]) as ssh, \
             mock.patch.object(self.fleet, "decide", wraps=decide) as decisions, \
             mock.patch.object(self.fleet.subprocess, "run", return_value=types.SimpleNamespace(
                 returncode=0, stdout=b"tracked-file\0")), \
             mock.patch.object(self.fleet.subprocess, "Popen", side_effect=results) as spawned, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            if tar_code or extract_code or spawn_error or broken_pipe:
                with self.assertRaises(SystemExit) as caught:
                    self.fleet.cmd_run(args)
                code = caught.exception.code
            else:
                code = self.fleet.cmd_run(args)
        self.last_decisions = [call.args[0] for call in decisions.call_args_list]
        self.selected_node = ssh.call_args.args[0]
        return code, stderr.getvalue(), spawned.call_count

    def test_tar_producer_or_extractor_failure_never_executes(self):
        for codes in ((1, 0), (0, 2), (1, 2), (75, 0), (0, 75)):
            with self.subTest(codes=codes):
                rc, out, launches = self.run_mocked_transfer(*codes)
                self.assertEqual(rc, 1)
                self.assertIn("Refuse[SOURCE_TRANSFER_FAILED]", out)
                self.assertEqual(launches, 2)

    def test_remote_execution_propagates_real_exit_code(self):
        for runtime_code in (0, 23, 75):
            with self.subTest(runtime_code=runtime_code):
                rc, out, launches = self.run_mocked_transfer(0, 0, runtime_code=runtime_code)
                self.assertEqual(rc, runtime_code)
                self.assertEqual(launches, 3)
                self.assertNotIn("Refuse[", out)

    def test_git_source_transfer_checks_both_sides(self):
        for codes in ((1, 0), (0, 2), (0, 0)):
            with self.subTest(codes=codes), tempfile.TemporaryDirectory() as folder:
                self.source = Path(folder)
                rc, out, launches = self.run_mocked_transfer(
                    *codes, runtime_code=0 if codes == (0, 0) else None, git_source=True)
                self.assertEqual(rc, 0 if codes == (0, 0) else 1)
                self.assertEqual(launches, 3 if codes == (0, 0) else 2)
                if rc:
                    self.assertIn("Refuse[SOURCE_TRANSFER_FAILED]: ", out)

    def test_transfer_spawn_and_broken_pipe_are_not_retryable(self):
        for stage in ("tar", "extract", "broken-pipe"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as folder:
                self.source = Path(folder)
                rc, out, launches = self.run_mocked_transfer(
                    0, 0, spawn_error=stage if stage != "broken-pipe" else None,
                    git_source=stage == "broken-pipe", broken_pipe=stage == "broken-pipe")
                self.assertEqual(rc, 1)
                self.assertIn("Refuse[SOURCE_TRANSFER_FAILED]: ", out)
                self.assertEqual(launches, 1 if stage == "tar" else 2)

    def test_healthy_real_registry_mbp_admits_with_or_without_source(self):
        for no_src in (False, True):
            with self.subTest(no_src=no_src):
                rc, out, launches = self.run_mocked_transfer(
                    0, 0, runtime_code=0, no_src=no_src, real_registry=True, node="auto")
                self.assertEqual(rc, 0)
                self.assertEqual(launches, 1 if no_src else 3)
                self.assertEqual(self.selected_node["name"], "mbp")
                self.assertNotIn("Refuse[", out)
                self.assertEqual(self.last_decisions, [
                    Request(Target.REMOTE, True, True, True, Transfer.PENDING),
                    Request(Target.REMOTE, True, True, True,
                            Transfer.NOT_REQUIRED if no_src else Transfer.COMPLETE),
                ])


class ShellBoundaryTests(unittest.TestCase):
    def test_shell_retries_only_a_nonempty_typed_capacity_refusal(self):
        for reason, first_code in (("NO_ROOM", 75), ("UNAVAILABLE", 75),
                                   ("SOURCE_TRANSFER_FAILED", 1)):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                script = workspace / "fleet-build"
                script.write_text((SCRIPTS / "fleet-build").read_text())
                marker = workspace / "invocations"
                slept = workspace / "slept"
                fake_fleet = workspace / "fleet"
                fake_fleet.write_text(
                    "#!/bin/sh\n"
                    f"if [ -e '{marker}' ]; then printf 'called\\n' >> '{marker}'; exit 0; fi\n"
                    f"printf 'called\\n' >> '{marker}'\n"
                    f"printf 'fleet: Refuse[{reason}]: nonempty fixture reason\\n' >&2\n"
                    f"exit {first_code}\n"
                )
                fake_fleet.chmod(0o755)
                fake_sleep = workspace / "sleep"
                fake_sleep.write_text(f"#!/bin/sh\nprintf 'slept\\n' >> '{slept}'\n")
                fake_sleep.chmod(0o755)
                result = subprocess.run(
                    ["bash", str(script), "--node", "mbp", "--class", "build",
                     "--wait", "65", "--src", temp, "--", "true"],
                    cwd=temp, env={**os.environ, "FLEET_STATE": str(workspace / "state"),
                                   "PATH": str(workspace) + os.pathsep + os.environ["PATH"]},
                    capture_output=True, text=True, timeout=10)
                retry = reason == "NO_ROOM"
                self.assertEqual(result.returncode, 0 if retry else first_code)
                self.assertEqual(marker.read_text().splitlines(),
                                 ["called", "called"] if retry else ["called"])
                self.assertEqual(slept.exists(), retry)
                self.assertIn(f"Refuse[{reason}]: nonempty fixture reason", result.stderr)

    def test_shell_refusal_is_typed_and_preserves_exit_class(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, FLEET_STATE=str(Path(temp) / "state"))
            script = str(SCRIPTS / "fleet-build")
            for mode in ("enforce", "report", "off"):
                with self.subTest(mode=mode):
                    result = subprocess.run(
                        ["bash", script, "--node", "groot", "--class", "build",
                         "--wait", "0", "--src", temp, "--", "echo", "NO"],
                        cwd=temp, env={**env, "Z0_GUARD_O1": mode},
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("Refuse[GROOT_FORBIDDEN]", result.stderr)
                    self.assertNotIn("NO\n", result.stdout)
            # Unknown pin reaches fleet's pure admission, but not probe or SSH.
            result = subprocess.run(
                ["bash", script, "--node", "nonexistent-worker", "--class", "build",
                 "--wait", "0", "--src", temp, "--", "echo", "NO"],
                cwd=temp, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 75)
            self.assertIn("Refuse[NO_REMOTE]", result.stderr)
            self.assertIn("admission refused (exit 75", result.stderr)

    def test_shell_never_relabels_a_remote_command_exit_75(self):
        # An isolated fake fleet executable: never an actual SSH, device or build.
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            script = workspace / "fleet-build"
            script.write_text((SCRIPTS / "fleet-build").read_text())
            fake_fleet = workspace / "fleet"
            marker = workspace / "invocations"
            fake_fleet.write_text(
                "#!/bin/sh\n"
                f"printf 'called\\n' >> '{marker}'\n"
                "printf 'fleet: job deadbeef -> mbp (mocked)\\n' >&2\n"
                "exit 75\n"
            )
            fake_fleet.chmod(0o755)
            result = subprocess.run(
                ["bash", str(script), "--node", "mbp", "--class", "build",
                 "--wait", "65", "--src", temp, "--", "true"],
                cwd=temp, env={**os.environ, "FLEET_STATE": str(workspace / "state")},
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 75)
            self.assertEqual(marker.read_text().splitlines(), ["called"])
            self.assertNotIn("admission refused", result.stderr)
            self.assertIn("not a typed admission refusal", result.stderr)


if __name__ == "__main__":
    unittest.main()
