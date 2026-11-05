"""The MBP Dash e2e army runs outside Kueue, so its memory must be capped (ayo 15:26):
every dash-army-* / eui-army-* transient unit lands in dash-army.slice, which throttles
(MemoryHigh) at 4 GiB. No MemoryMax: the army is a long-running owner job and must slow
down under pressure, not be OOM-killed."""
import configparser
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "config/systemd/user"
GIB = 1024 ** 3


def ini(path):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read(path)
    return cp


def size(v):
    units = {"K": 1024, "M": 1024 ** 2, "G": GIB}
    return int(float(v[:-1]) * units[v[-1]]) if v[-1] in units else int(v)


class DashArmyBudget(unittest.TestCase):
    def test_slice_throttles_at_or_below_4gib_without_a_kill_limit(self):
        s = ini(UNITS / "dash-army.slice")["Slice"]
        self.assertLessEqual(size(s["MemoryHigh"]), 4 * GIB)
        self.assertNotIn("MemoryMax", s)

    def test_every_army_unit_prefix_is_routed_into_the_slice(self):
        for prefix in ("dash-army-", "eui-army-"):
            drop = UNITS / f"{prefix}.service.d" / "50-memory-budget.conf"
            self.assertEqual(ini(drop)["Service"]["Slice"], "dash-army.slice", drop)


if __name__ == "__main__":
    unittest.main()
