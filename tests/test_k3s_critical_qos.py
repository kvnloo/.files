"""Critical k3s services this repo owns must be Guaranteed QoS and still fit groot.

A Burstable pod gets oom_score_adj near 1000, so a host-wide OOM on groot kills
it before any agent. Guaranteed (requests == limits for cpu and memory) gets -997.
Raising requests to the limits must not push groot's small allocatable over.
Services whose manifests live elsewhere (Kueue's pinned upstream release,
z0intelligence's executor, quackles' GPU plugin, k3s' CoreDNS) are not listed.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# manifest -> workload names this repo owns there
OWNED_CRITICAL = {
    'config/k3s/manifests/50-factory-gateway.yaml': {'factory-gateway'},
}
WORKLOAD_KINDS = {'Deployment', 'DaemonSet', 'StatefulSet'}

# groot node capacity (kubectl get node groot, 2026-10-28): hardware, not tunable.
GROOT_CPU = 20
GROOT_MEMORY_KI = 24494304
# Other control-plane requests on groot (CoreDNS, metrics-server, Kueue, executor,
# GPU plugins): the ~0.8Gi in config/k3s/server.yaml's reservation comment.
OTHER_CONTROL_PLANE_GIB = 0.8

MEM_UNITS = {'': 1, 'Ki': 2**10, 'Mi': 2**20, 'Gi': 2**30, 'K': 10**3, 'M': 10**6, 'G': 10**9}


def cpu(text):
    text = str(text)
    return float(text[:-1]) / 1000 if text.endswith('m') else float(text)


def memory(text):
    found = re.fullmatch(r'(\d+(?:\.\d+)?)([KMG]i?)?', str(text))
    if not found:
        raise AssertionError(f'unparsed memory quantity {text!r}')
    value, unit = found.groups()
    return float(value) * MEM_UNITS[unit or '']


def owned_workloads():
    for path, names in OWNED_CRITICAL.items():
        docs = [d for d in yaml.safe_load_all((ROOT / path).read_text()) if d]
        found = {d['metadata']['name']: d for d in docs
                 if d.get('kind') in WORKLOAD_KINDS and d['metadata']['name'] in names}
        missing = names - found.keys()
        if missing:
            raise AssertionError(f'{path}: owned critical workload(s) {sorted(missing)} not found')
        yield from ((path, d) for d in found.values())


def containers(workload):
    spec = workload['spec']['template']['spec']
    return spec.get('initContainers', []) + spec['containers']


def kubelet_args():
    return yaml.safe_load((ROOT / 'config/k3s/server.yaml').read_text())['kubelet-arg']


def kubelet_value(prefix, key):
    for arg in kubelet_args():
        if arg.startswith(prefix + '='):
            pairs = dict(p.split('=', 1) for p in arg[len(prefix) + 1:].split(','))
            return pairs[key]
    raise AssertionError(f'server.yaml has no {prefix}')


def eviction_memory():
    for arg in kubelet_args():
        found = re.match(r'eviction-hard=.*memory\.available<([^,]+)', arg)
        if found:
            return found.group(1)
    raise AssertionError('server.yaml has no eviction-hard memory.available')


class CriticalServiceQoS(unittest.TestCase):
    def test_owned_critical_services_are_guaranteed(self):
        for path, workload in owned_workloads():
            for c in containers(workload):
                where = f"{path} {workload['metadata']['name']}/{c['name']}"
                res = c.get('resources') or {}
                req, lim = res.get('requests') or {}, res.get('limits') or {}
                for key, parse in (('cpu', cpu), ('memory', memory)):
                    self.assertIn(key, lim, f'{where}: no {key} limit, so not Guaranteed')
                    self.assertIn(key, req, f'{where}: no {key} request, so not Guaranteed')
                    self.assertEqual(parse(req[key]), parse(lim[key]),
                                     f'{where}: {key} request {req[key]} != limit {lim[key]} '
                                     '(Burstable dies first in a host OOM)')

    def test_guaranteed_requests_fit_groot_allocatable(self):
        reserved_cpu = cpu(kubelet_value('system-reserved', 'cpu'))
        reserved_mem = memory(kubelet_value('system-reserved', 'memory'))
        evict_mem = memory(eviction_memory())
        alloc_cpu = GROOT_CPU - reserved_cpu
        alloc_mem = GROOT_MEMORY_KI * 2**10 - reserved_mem - evict_mem
        want_cpu = want_mem = 0.0
        for _, workload in owned_workloads():
            pinned = (workload['spec']['template']['spec'].get('nodeSelector') or {})
            if pinned.get('kubernetes.io/hostname') not in (None, 'groot'):
                continue
            replicas = workload['spec'].get('replicas', 1)
            for c in workload['spec']['template']['spec']['containers']:
                req = (c.get('resources') or {}).get('requests') or {}
                want_cpu += replicas * cpu(req.get('cpu', 0))
                want_mem += replicas * memory(req.get('memory', 0))
        self.assertLessEqual(want_cpu, alloc_cpu, 'Guaranteed CPU requests exceed groot allocatable')
        self.assertLessEqual(want_mem + OTHER_CONTROL_PLANE_GIB * 2**30, alloc_mem,
                             'Guaranteed memory requests plus the other control plane exceed '
                             'groot allocatable; pods would sit Pending')


if __name__ == '__main__':
    unittest.main()
