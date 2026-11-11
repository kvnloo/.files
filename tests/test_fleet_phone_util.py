import importlib.machinery
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "scripts" / "fleet-phone-util"
spec = importlib.util.spec_from_loader("fleet_phone_util", importlib.machinery.SourceFileLoader("fleet_phone_util", str(PATH)))
util = importlib.util.module_from_spec(spec)
spec.loader.exec_module(util)


class PhoneUtilTest(unittest.TestCase):
    def test_offline_phone_does_not_void_other_phones(self):
        def run(cmd, **_):
            if "dead" in cmd:
                return subprocess.CompletedProcess(cmd, 1, "", "adb: device offline")
            run.n += 1
            return subprocess.CompletedProcess(cmd, 0, f"cpu {run.n * 90} 0 0 {run.n * 10} 0\n8\n", "")
        run.n = 0
        with mock.patch("subprocess.run", side_effect=run), mock.patch("time.sleep"), \
                mock.patch("sys.argv", ["x", "--json", "ok=a", "off=dead"]), \
                mock.patch("builtins.print") as out:
            self.assertEqual(util.main(), 0)
        row = __import__("json").loads(out.call_args.args[0])["phones"]
        self.assertEqual(row["ok"], {"busy_pct": 90.0, "cores": 8})
        self.assertEqual(row["off"], {"error": "RuntimeError: adb: device offline"})


if __name__ == "__main__":
    unittest.main()
