"""Native phone public behavior, with host transport doubles (no live device)."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
