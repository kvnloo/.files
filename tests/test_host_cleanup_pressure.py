import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/host-cleanup-pressure.py"
spec = importlib.util.spec_from_file_location("cleanup_pressure", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DF = "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/block/dm-1 104857600 52428800 52428800 50% /data\n"


class PressureTests(unittest.TestCase):
    def test_reserve_boundaries(self):
        self.assertFalse(module.pressure(150 * module.GIB, 15 * module.GIB))
        self.assertTrue(module.pressure(200 * module.GIB, 19 * module.GIB))
        self.assertTrue(module.pressure(100 * module.GIB, 14 * module.GIB))
        for total, free in [(0, 0), (5, -1), (5, 6)]:
            with self.assertRaises(ValueError):
                module.pressure(total, free)

    def test_android_df_and_invalid_outputs(self):
        self.assertEqual(module.parse_df(DF), (100 * module.GIB, 50 * module.GIB))
        self.assertEqual(module.parse_df(DF.replace("/data", "/data/user/0")), (100 * module.GIB, 50 * module.GIB))
        self.assertEqual(module.parse_df(DF.replace("/data", "/storage/emulated/0/Android/obb")), (100 * module.GIB, 50 * module.GIB))
        for text in ["", DF.replace("/data", "relative"), DF + DF, DF.replace("52428800 50%", "-1 50%")]:
            with self.assertRaises(ValueError):
                module.parse_df(text)

    def test_unavailable_mount_is_unknown(self):
        self.assertEqual(module.local_disk("/does-not-exist-PH8")["status"], "unknown")

    def test_existing_transports_only_and_hardware_identity(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[-1] == "devices":
                return "List of devices attached\nwrong device\ns25 device\ns22 offline\n"
            if argv[-1] == "getprop ro.serialno":
                return module.PHONES["s25"] if "s25" in argv else "OTHER"
            return DF

        rows = module.phone_disks("adb", run)
        self.assertEqual([row["status"] for row in rows], ["ok", "unknown"])
        self.assertEqual(rows[0]["serial"], module.PHONES["s25"])
        self.assertEqual(len(calls), 4)
        self.assertFalse(any(word in argv for argv in calls for word in ["connect", "tcpip", "input", "reboot"]))

    def test_transport_and_parse_errors_are_not_healthy(self):
        def fail(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 8)

        self.assertTrue(all(row["status"] == "unknown" for row in module.phone_disks("adb", fail)))
        responses = iter(["s25 device\n", module.PHONES["s25"], "not df"])
        rows = module.phone_disks("adb", lambda *a, **k: next(responses))
        self.assertTrue(all(row["status"] == "unknown" for row in rows))

    def test_probe_budget(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return "".join(f"x{n} device\n" for n in range(50)) if argv[-1] == "devices" else "OTHER"

        module.phone_disks("adb", run)
        self.assertEqual(len(calls), 9)

    def test_repair_only_on_same_device_and_single_bounded_prune(self):
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root)
            events, calls = [], []

            def run(argv, **kwargs):
                self.assertEqual(events[0]["event"], "repair_planned")
                calls.append((argv, kwargs))
                return "Removed 1 unused file"

            rows = [{"status": "pressure", "device": cache.stat().st_dev}]
            result = module.repair_uv(rows, cache, events.append, run)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(calls, [(["uv", "cache", "prune", "--offline", "--no-config", "--cache-dir", str(cache)], {"timeout": 20})])
            rows[0]["device"] += 1
            self.assertEqual(module.repair_uv(rows, cache, events.append, run)["status"], "skipped")
            self.assertEqual(len(calls), 1)

    def test_bulk_offload_policy_prevents_prune(self):
        with patch.object(Path, "resolve", return_value=Path("/mnt/zer0models/cache/uv")), patch.object(Path, "is_dir", return_value=True), patch.object(module, "command") as run:
            result = module.repair_uv([{"status": "pressure"}], Path("/home/kvn/.cache/uv"), lambda row: None, run)
            self.assertEqual(result["status"], "skipped")
            self.assertIn("forbids", result["reason"])
            run.assert_not_called()

    def test_receipt_failure_prevents_repair(self):
        with tempfile.TemporaryDirectory() as root:
            def fail(row):
                raise OSError("receipt storage full")

            with patch.object(module, "command") as run:
                with self.assertRaises(OSError):
                    module.repair_uv([{"status": "pressure", "device": os.stat(root).st_dev}], Path(root), fail, run)
                run.assert_not_called()

    def test_timeout_is_unknown_not_success(self):
        with tempfile.TemporaryDirectory() as root:
            events = []

            def fail(argv, **kwargs):
                raise subprocess.TimeoutExpired(argv, 20)

            result = module.repair_uv([{"status": "pressure", "device": os.stat(root).st_dev}], Path(root), events.append, fail)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(len(events), 2)

    def test_cli_writes_real_private_receipt_and_reports_open_findings(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("sys.argv", [str(SCRIPT), "--state-dir", root]), patch.object(module.socket, "gethostname", return_value="groot"), patch.object(module, "local_disk", return_value={"status": "pressure"}), patch.object(module, "phone_disks", return_value=[{"status": "unknown"}]):
                self.assertEqual(module.main(), 1)
            receipts = list(Path(root).glob("*.jsonl"))
            self.assertEqual(len(receipts), 1)
            rows = [json.loads(line) for line in receipts[0].read_text().splitlines()]
            self.assertEqual([row["event"] for row in rows], ["start", "observations", "summary"])
            self.assertTrue(rows[-1]["unresolved"])
            self.assertEqual(receipts[0].stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
