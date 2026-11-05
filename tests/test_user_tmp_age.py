"""MBP /tmp (tmpfs, swapped to zram) grew 6.9 GB of finished scratch (11-05): the
system rule is 10d and per-user scratch was never aged. A user tmpfiles rule ages
the known scratch roots after 2 days idle, and the user clean timer runs it."""
import re, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "config/user-tmpfiles.d/z0-tmp-age.conf"
TIMER = ROOT / "config/systemd/user/timers.target.wants/systemd-tmpfiles-clean.timer"

class UserTmpAge(unittest.TestCase):
    def rules(self):
        return [l.split() for l in CONF.read_text().splitlines() if l.strip() and not l.startswith("#")]
    def test_scratch_roots_age_out_within_3_days(self):
        got = {r[1]: r for r in self.rules()}
        for path in ("/tmp/claude-1000", "/tmp/sr-triage.*", "/tmp/dash-flow-*"):
            self.assertIn(path, got)
            typ, age = got[path][0], got[path][5]
            self.assertEqual(typ, "e", "clean-only: never create or reset modes")
            m = re.fullmatch(r"(\d+)([hd])", age); self.assertTrue(m, age)
            hours = int(m.group(1)) * (24 if m.group(2) == "d" else 1)
            self.assertTrue(24 < hours <= 72, age)
    def test_never_ages_all_of_tmp(self):
        self.assertNotIn("/tmp", {r[1] for r in self.rules()})
    def test_user_clean_timer_enabled(self):
        self.assertTrue(TIMER.is_symlink())
        self.assertEqual(str(TIMER.readlink()), "/usr/lib/systemd/user/systemd-tmpfiles-clean.timer")

if __name__ == "__main__":
    unittest.main()
