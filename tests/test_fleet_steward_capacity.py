import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fleet_steward_capacity", ROOT / "scripts/fleet_steward_capacity.py")
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class CapacityTests(unittest.TestCase):
    def test_exact_resources_and_no_synthetic_offers(self):
        snapshot = capacity.build_capacity([{"node": "mbp", "healthy": True, "ts": 90,
            "probe": {"host_id": "host-canonical", "ts": 90, "ncpu": 8, "mem_total_mb": 16000,
                      "mem_available_mb": 4000, "max_temp_c": 98,
                      "disk_lane": {"total_bytes": 100000, "free_bytes": 12000}}}], now=100)
        self.assertEqual(snapshot["schema"], "z0.capacity.snapshot.v1")
        self.assertEqual(snapshot["hosts"][0]["host_id"], "host-canonical")
        resources = snapshot["hosts"][0]["resources"]
        self.assertEqual(resources["storage_free_bytes"], 12000)
        self.assertIsNone(resources["gpu_count"])
        self.assertNotIn("max_temp_c", resources)
        self.assertEqual(snapshot["offers"], [])
        self.assertEqual(snapshot["summary"], {"hosts": 1, "sessions": 0, "offers": 0, "leases": 0})

    def test_stale_values_unknown_and_legacy_identity_not_merged(self):
        snapshot = capacity.build_capacity([{"node": "mbp", "healthy": True, "ts": 1,
            "probe": {"ncpu": 8, "mem_available_mb": 9000}}], now=500)
        host = snapshot["hosts"][0]
        self.assertEqual(host["status"], "unknown")
        self.assertEqual(host["host_id"], "fleet:mbp")
        self.assertIsNone(host["resources"]["cpu_logical"])
        self.assertIn("alias review", snapshot["sources"]["fleet"]["reason"])

    def test_future_and_invalid_numbers_are_not_free_capacity(self):
        snapshot = capacity.build_capacity([{"node": "mbp", "healthy": True, "ts": 110,
            "probe": {"ncpu": float("nan"), "mem_available_mb": -10}}], now=100)
        self.assertIsNone(snapshot["hosts"][0]["resources"]["cpu_logical"])
        json.dumps(snapshot, allow_nan=False)

    def test_projection_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "health").mkdir()
            (root / "health/mbp.json").write_text(json.dumps({"node": "mbp", "ts": 1, "probe": {}}))
            capacity.export_capacity(root, root / "steward")
            path = root / "steward/capacity.json"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text())["summary"]["hosts"], 1)
            self.assertEqual(list((root / "steward").glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
