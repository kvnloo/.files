"""groot's kubelet reservation must cover the host memory budgets the scheduler cannot see."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = {'G': 1, 'Gi': 1, 'M': 1 / 1024, 'Mi': 1 / 1024}
DESKTOP_GIB = 4  # compositor, session services, browsers; not under any limit


def gib(text):
    value, unit = re.fullmatch(r'(\d+)([GM]i?)', text).groups()
    return int(value) * UNITS[unit]


def setting(path, key):
    found = re.findall(rf'^{key}=(\S+)$', (ROOT / path).read_text(), re.M)
    return found[-1]  # systemd: the last assignment wins


class HostReservation(unittest.TestCase):
    def test_server_reservation_covers_host_budgets(self):
        server = (ROOT / 'config/k3s/server.yaml').read_text()
        reserved = gib(re.search(r'system-reserved=[^"]*memory=(\d+[GM]i?)', server).group(1))
        agents = gib(setting('config/systemd/user/agent.slice.d/60-oomd-desktop-guard.conf', 'MemoryMax'))
        farm = gib(setting('config/systemd/user/z0-farm-llama.service', 'MemoryHigh'))
        self.assertGreaterEqual(reserved, agents + farm + DESKTOP_GIB,
                                'k3s would schedule pods into memory groot already promised to agents/farm/desktop')


if __name__ == '__main__':
    unittest.main()
