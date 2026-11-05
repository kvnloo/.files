"""Kueue's controller must survive groot apiserver stalls (ayo 16:3x).

On 11-05 it restarted 96 times: "leader election lost" (lease renew to the k3s
apiserver timed out under groot memory/IO pressure; controller-runtime defaults are
15s lease / 10s renew) and 1 s readiness/liveness probe timeouts. A lost lease stops
all admission. Tolerances here are what the live deployment must carry.
"""
import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KUEUE = ROOT / "config/k3s/kueue"


def seconds(v):
    m = re.fullmatch(r"(\d+)s", str(v))
    assert m, v
    return int(m.group(1))


class KueueLeaseTolerance(unittest.TestCase):
    def test_lease_outlasts_an_apiserver_stall(self):
        le = yaml.safe_load((KUEUE / "controller_manager_config.yaml").read_text())["leaderElection"]
        self.assertTrue(le["leaderElect"])
        lease, renew, retry = (seconds(le[k]) for k in ("leaseDuration", "renewDeadline", "retryPeriod"))
        self.assertGreaterEqual(renew, 45)
        self.assertLess(renew, lease)
        self.assertLess(retry, renew)

    def test_probes_tolerate_a_slow_controller(self):
        patch = json.loads((KUEUE / "controller-probes.patch.json").read_text())
        c = patch["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(c["name"], "manager")
        for probe in ("livenessProbe", "readinessProbe"):
            p = c[probe]
            self.assertGreaterEqual(p["timeoutSeconds"], 5, probe)
            self.assertGreaterEqual(p["periodSeconds"] * p["failureThreshold"], 60, probe)


if __name__ == "__main__":
    unittest.main()
