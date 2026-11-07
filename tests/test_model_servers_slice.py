"""2026-11-05 19:1x groot OOM: three llama units each had their own cap (5 + 3 + 8 GiB on a
23 GiB host) and nothing bounded them together. They share one slice with one cap."""
import configparser, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'config/systemd/user'
UNITS = ('hermes-ttft-llama', 'hermes-swarm-llama', 'z0-farm-llama')


def ini(path):
    c = configparser.ConfigParser(strict=False, interpolation=None)
    c.optionxform = str
    c.read(path)
    return c


class ModelServersSlice(unittest.TestCase):
    def test_slice_caps_all_model_servers_together(self):
        s = ini(ROOT / 'model-servers.slice')
        self.assertEqual(s['Slice']['MemoryMax'], '6G')
        self.assertEqual(s['Slice']['MemoryHigh'], '5G')

    def test_each_llama_unit_runs_in_the_slice(self):
        for u in UNITS:
            with self.subTest(unit=u):
                d = ini(ROOT / f'{u}.service.d/40-model-servers-slice.conf')
                self.assertEqual(d['Service']['Slice'], 'model-servers.slice')


if __name__ == '__main__':
    unittest.main()
