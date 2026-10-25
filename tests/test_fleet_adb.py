"""Native phone public behavior, with host transport doubles (no live device)."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
ADB = runpy.run_path(str(SCRIPTS / "fleet-adb"))
FLEET = runpy.run_path(str(SCRIPTS / "fleet"))
Device = ADB["Device"]


class NativeLaneTests(unittest.TestCase):
    def discover(self, connected, identities, mdns=""):
        calls = []
        def transport(argv, **kwargs):
            args = argv[3:]
            self.assertEqual(kwargs.get("stdin"), subprocess.DEVNULL)
            calls.append(args)
            if args == ["devices", "-l"]:
                text = "List of devices attached\n" + "\n".join(f"{s} device" for s in connected)
            elif args == ["mdns", "services"]:
                text = mdns
            elif args[0] == "connect":
                text = "connected"
            elif args[0] == "-s":
                text = identities.get(args[1], "wrong-phone")
            else:
                raise AssertionError(args)
            return subprocess.CompletedProcess(argv, 0, stdout=text, stderr="")
        with tempfile.TemporaryDirectory() as home:
            binary = Path(home) / "android/sdk/platform-tools/adb"
            binary.parent.mkdir(parents=True)
            binary.touch()
            with mock.patch("pathlib.Path.home", return_value=Path(home)), mock.patch("subprocess.run", side_effect=transport):
                device = Device("s22")
        return device, calls

    def test_usb_preferred_only_after_hardware_identity_matches(self):
        device, calls = self.discover(["192.0.2.1:1234", "usb-other", "usb-right"],
                                      {"192.0.2.1:1234": "RFCTA1RZAQY", "usb-right": "RFCTA1RZAQY"})
        self.assertEqual(device.serial, "usb-right")
        self.assertNotIn(["-s", "192.0.2.1:1234", "shell", "getprop ro.serialno"], calls)

    def test_wireless_discovery_checks_identity_not_advertisement(self):
        device, calls = self.discover([], {"192.0.2.2:4567": "RFCTA1RZAQY"},
            "adb-RFCTA1RZAQY-random _adb-tls-connect._tcp 192.0.2.2:4567\n")
        self.assertEqual(device.serial, "192.0.2.2:4567")
        self.assertIn(["connect", "192.0.2.2:4567"], calls)

    def test_absent_hardware_has_no_guest_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "no guest fallback"):
            self.discover(["usb-wrong"], {})

    def test_battery_gate_is_exact_floor_and_ignores_thermal(self):
        node = {"kind": "phone", "health": {}}
        for pct, charging, refused in [(1, False, True), (2, False, False), (0, True, False), (100, False, False)]:
            with self.subTest(pct=pct, charging=charging):
                facts = {"transport": "adb", "power": {"on_ac": charging, "batteries": [{"pct": pct}],
                                                       "android_thermal_status": 6}}
                bad, _ = FLEET["judge"](node, facts, {}, {}, {})
                self.assertEqual(bool(bad), refused)

    def test_native_probe_does_not_invoke_ssh_or_require_guest(self):
        facts = {"transport": "adb", "online": True, "power": {"on_ac": True, "batteries": [{"pct": 1}]}}
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(facts), stderr="")
        with mock.patch("subprocess.run", return_value=result) as run:
            self.assertEqual(FLEET["probe"]({"kind": "phone", "name": "omarchy-phone"}), facts)
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.args[0][-2:], ["probe", "omarchy-phone"])
        bad, _ = FLEET["judge"]({"kind": "phone", "health": {}}, facts, {}, {}, {})
        self.assertEqual(bad, [])

    def test_native_submit_refuses_low_battery_before_staging(self):
        device = mock.Mock()
        device.probe.return_value = {"power": {"on_ac": False, "batteries": [{"pct": 1}]}}
        args = argparse.Namespace(argv=["sh"], timeout=20)
        with self.assertRaisesRegex(RuntimeError, "below 2%"):
            ADB["run"](device, args)
        device.shell.assert_not_called()
        device.push.assert_not_called()

    def test_artifact_paths_cannot_escape_job(self):
        for path in ("/etc/passwd", "../other", "src/../../other", "", "src/\nname"):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                ADB["relative"](path)
        self.assertEqual(ADB["relative"]("src/result.bin"), "src/result.bin")

    def test_changed_identity_is_never_signalled(self):
        device = mock.Mock()
        saved = {"pid": 111, "start": "10", "boot": "a"}
        device.shell.return_value = json.dumps(saved)
        with mock.patch.dict(ADB["kill"].__globals__, identity=lambda *_: {**saved, "start": "20"}):
            with self.assertRaisesRegex(RuntimeError, "changed process identity"):
                ADB["kill"](device, "owned-job")
        self.assertEqual(device.shell.call_count, 1)

    def test_guest_service_requires_foreground_linux_service(self):
        device = Device.__new__(Device)
        for text, expected in [("LinuxService isForeground=true", True),
                               ("LinuxService isForeground=false", False),
                               ("OtherService isForeground=true", False)]:
            device.shell = mock.Mock(return_value=text)
            self.assertEqual(device.guest_running(), expected)

    def restore(self, *, facts=None, ledger=True, running=None, attempts=0):
        device = Device.__new__(Device)
        device.node = "s22"
        device.guest_running = mock.Mock(side_effect=running or [False, True])
        facts = facts or ("120.0 0\nboot-a\nmLastUserActivityTime=1000\n"
                          "topResumedActivity=ActivityRecord{a u0 com.agent/.Main}\n"
                          "mCallState=0\nmMode=MODE_NORMAL\n")
        device.shell = mock.Mock(return_value=facts)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if ledger:
                (root / "s22-agent-opened.json").write_text(json.dumps({
                    "com.agent": {"boot_id": "boot-a", "opened_uptime_ms": 2000}}))
            (root / "s22-guest-restore.json").write_text(json.dumps({
                "boot_id": "boot-a", "attempts": attempts}))
            with mock.patch.dict(Device.restore_guest.__globals__,
                                 Path=lambda p: root / Path(p).name), \
                    mock.patch("builtins.open", mock.mock_open()), \
                    mock.patch("fcntl.flock"), mock.patch("time.sleep"):
                result = device.restore_guest()
            saved = json.loads((root / "s22-guest-restore.json").read_text())
            opened = json.loads((root / "s22-agent-opened.json").read_text()) if ledger else {}
        return result, device.shell, saved, opened

    def test_idle_guest_restore_records_attempt_and_agent_open(self):
        result, shell, saved, opened = self.restore()
        self.assertEqual(result, "restored")
        self.assertEqual(saved["attempts"], 1)
        self.assertEqual(opened["dev.omalauncher"]["boot_id"], "boot-a")
        self.assertEqual(shell.call_args.args[0],
                         "monkey -p dev.omalauncher -c android.intent.category.LAUNCHER 1")

    def test_guest_restore_fails_closed_for_owner_call_and_missing_evidence(self):
        base = ("120.0 0\nboot-a\nmLastUserActivityTime=1000\n"
                "topResumedActivity=ActivityRecord{a u0 com.agent/.Main}\n"
                "mCallState=0\nmMode=MODE_NORMAL\n")
        for facts, ledger, expected in [
                (base, False, "owner_busy"),
                (base.replace("=1000", "=119000"), True, "owner_busy"),
                (base.replace("mCallState=0", "mCallState=2"), True, "in_call"),
                (base.replace("MODE_NORMAL", "MODE_IN_COMMUNICATION"), True, "in_call"),
                ("unknown", True, "restore_evidence_unavailable")]:
            with self.subTest(expected=expected):
                result, shell, saved, _ = self.restore(facts=facts, ledger=ledger)
                self.assertEqual(result, expected)
                self.assertEqual(shell.call_count, 1)
                self.assertEqual(saved["attempts"], 0)

    def test_guest_restore_is_bounded_across_ticks(self):
        result, shell, saved, _ = self.restore(attempts=2)
        self.assertEqual(result, "retry_exhausted")
        self.assertEqual(shell.call_count, 1)
        result, shell, saved, _ = self.restore(running=[False] * 7)
        self.assertEqual(result, "retry_exhausted")
        self.assertEqual(saved["attempts"], 2)
        self.assertEqual(sum("monkey" in c.args[0] for c in shell.call_args_list), 2)

    def test_guest_restore_respects_ui_lock(self):
        device = Device.__new__(Device)
        device.node = "s22"
        device.shell = mock.Mock()
        with mock.patch("builtins.open", mock.mock_open()), \
                mock.patch("fcntl.flock", side_effect=BlockingIOError):
            self.assertEqual(device.restore_guest(), "ui_busy")
        device.shell.assert_not_called()

    def test_probe_reports_guest_down_without_hiding_native_availability(self):
        device = Device.__new__(Device)
        device.serial, device.hardware = "usb", "RFCTA1RZAQY"
        device.shell = mock.Mock(side_effect=["level: 50\nscale: 100",
                                              "Thermal Status: 0", "0.1 0.2 0.3", "0-7"])
        device.guest_running = mock.Mock(return_value=False)
        device.restore_guest = mock.Mock(return_value="owner_busy")
        facts = device.probe()
        self.assertEqual(facts["status"], "guest_down")
        self.assertTrue(facts["online"])
        self.assertEqual(facts["guest_recovery"], "owner_busy")

    def test_native_source_push_uses_included_immutable_snapshot_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "keep.py").write_text("captured")
            (source / "other.py").write_text("excluded")
            (source / ".git").write_text("not metadata to transport")
            runs = root / "state/runs"
            pushed = {}
            device = mock.Mock(hardware="fixture")
            device.probe.return_value = {"power": {"batteries": [{"pct": 50}], "on_ac": True}}
            def push(path, destination):
                if destination.endswith("/source.tar.gz"):
                    with Path(path).open("rb") as stream:
                        pushed["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
                    with tarfile.open(path, "r:gz") as archive:
                        pushed["names"] = archive.getnames()
                        pushed["content"] = archive.extractfile("keep.py").read()
            device.push.side_effect = push
            args = argparse.Namespace(argv=["true"], timeout=30, no_src=False, src=str(source),
                                      src_include=["keep.py"], input=[], fetch=[], dest=None)
            namespace = ADB["run"].__globals__
            with mock.patch("fleet_paths.runs_dir", return_value=runs), \
                 mock.patch.dict(namespace, {"runs_dir": lambda: runs,
                                            "identity": lambda *a: {"pid": 1, "start": "owned", "boot": "boot"}}):
                self.assertEqual(ADB["run"](device, args), 0)
            receipt = json.loads(next(runs.glob("*.json")).read_text())
            self.assertEqual(pushed["names"], ["keep.py"])
            self.assertEqual(pushed["content"], b"captured")
            self.assertEqual(receipt["source_snapshot"]["sha256"], pushed["sha256"])
            self.assertEqual(receipt["source_snapshot"]["includes"], ["keep.py"])

if __name__ == "__main__":
    unittest.main()
