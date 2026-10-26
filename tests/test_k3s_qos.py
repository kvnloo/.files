"""k3s-qos-reconcile keeps infrastructure pods Guaranteed (adj -997), behind agent subagents (adj 800)."""
import importlib.machinery
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(ROOT / 'scripts' / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


Q = load('k3s-qos-reconcile')


def mib(text):
    v, u = re.fullmatch(r'(\d+)(Mi|Gi)', text).groups()
    return int(v) * (1024 if u == 'Gi' else 1)


def workload(resources, extra=()):
    return {'spec': {'template': {'spec': {'containers': [{'name': 'coredns', 'resources': resources}, *extra]}}}}


class Drift(unittest.TestCase):
    def test_live_burstable_coredns_is_drift(self):
        # red: the shape coredns had during the 2026-10-26 crash loop (adj 998)
        live = {'requests': {'cpu': '100m', 'memory': '70Mi'}, 'limits': {'memory': '170Mi'}}
        self.assertIsNotNone(Q.drift(workload(live), 'coredns', '200m', '170Mi'))

    def test_guaranteed_shape_is_clean(self):
        self.assertIsNone(Q.drift(workload(Q.want('200m', '170Mi')), 'coredns', '200m', '170Mi'))

    def test_untabled_burstable_sidecar_is_drift(self):
        side = {'name': 'proxy', 'resources': {'requests': {'cpu': '5m'}}}
        self.assertIsNotNone(Q.drift(workload(Q.want('200m', '170Mi'), [side]), 'coredns', '200m', '170Mi'))

    def test_patch_sets_requests_equal_limits(self):
        body = json.loads(Q.patch_body('coredns', '200m', '170Mi'))
        res = body['spec']['template']['spec']['containers'][0]['resources']
        self.assertEqual(res['requests'], res['limits'])


class Budget(unittest.TestCase):
    def test_guaranteed_requests_fit_reserved_allocatable(self):
        server = (ROOT / 'config/k3s/server.yaml').read_text()
        reserved = mib(re.search(r'system-reserved=[^"]*memory=(\d+(?:Mi|Gi))', server).group(1))
        evict = mib(re.search(r'memory\.available<(\d+(?:Mi|Gi))', server).group(1))
        capacity = 24494304 // 1024  # groot MemTotal, MiB
        total = sum(mib(row[5]) for row in Q.TABLE)
        self.assertLess(total, capacity - reserved - evict, 'Guaranteed requests would not schedule')

    def test_every_row_is_complete_and_unique(self):
        keys = [(r[0], r[1], r[2]) for r in Q.TABLE]
        self.assertEqual(len(keys), len(set(keys)))
        for row in Q.TABLE:
            self.assertEqual(len(row), 6)

    def test_owned_manifests_match_table(self):
        for path, name in (('config/k3s/manifests/50-factory-gateway.yaml', 'factory-gateway'),
                           ('config/k3s/manifests/10-nvidia.yaml', 'nvidia-device-plugin')):
            row = next(r for r in Q.TABLE if r[2] == name)
            text = (ROOT / path).read_text()
            want = f'{{cpu: {row[4]}, memory: {row[5]}}}'
            self.assertIn(f'requests: {want}', text, path)
            self.assertIn(f'limits: {want}', text, path)


if __name__ == '__main__':
    unittest.main()
