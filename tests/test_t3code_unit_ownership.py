"""T3's own updater (`t3 update --yes`, t3-auto-update.timer) rewrites ~/.config/systemd/user/t3code.service
on every release. When .files also owned that file, the update replaced our link (live_drift 'replaced'),
dropped the agent memory policy, and left a source pinned to a deleted version (0.1.2 on 2026-11-16).
.files owns only a drop-in, which the updater never touches."""
import pathlib
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DROPIN = "config/systemd/user/t3code.service.d/50-agent-memory-policy.conf"


class T3UnitOwnership(unittest.TestCase):
    def setUp(self):
        self.rows = tomllib.loads((ROOT / "config/host/groot.toml").read_text())["user"]

    def test_no_row_claims_the_unit_file_t3_rewrites(self):
        claimed = [r["live"] for r in self.rows if r["live"].endswith("/t3code.service")]
        self.assertEqual(claimed, [])
        self.assertFalse((ROOT / "config/systemd/user/t3code.service").exists())

    def test_memory_policy_survives_t3_update_as_a_dropin(self):
        self.assertIn("Environment=T3CODE_AGENT_MEMORY_POLICY=inherit", (ROOT / DROPIN).read_text())
        self.assertIn(DROPIN, [r["source"] for r in self.rows])


if __name__ == "__main__":
    unittest.main()
