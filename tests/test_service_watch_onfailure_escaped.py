"""OnFailure=service-watch-failure@<unit>.service must systemd-escape <unit>: '-' in an
instance name unescapes to '/', so host-optimizer's literal OnFailure reported
'host/optimizer.service' -> 'Invalid unit' and left a failed watcher (11-05). %n is escaped by systemd and
is fine. Or use the escaped name (\\x2d), as the generated 90-service-watch drop-ins do."""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "config/systemd/user"
PAT = re.compile(r"^OnFailure=.*?service-watch-failure@([^\s]+)\.service", re.M)


class OnFailureEscaped(unittest.TestCase):
    def test_no_raw_dash_in_watch_instance(self):
        bad = []
        for f in ROOT.rglob("*"):
            if f.is_file() and not f.is_symlink():
                for inst in PAT.findall(f.read_text(errors="ignore")):
                    if "-" in inst and "%" not in inst:
                        bad.append(f"{f.relative_to(ROOT)}: {inst}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
