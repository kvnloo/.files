"""The factory gateway must retain Guaranteed QoS when its containers change."""
import re
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MULTIPLIERS = {'': 1, 'm': Decimal('0.001'), 'Ki': 2**10, 'Mi': 2**20,
               'Gi': 2**30, 'K': 10**3, 'M': 10**6, 'G': 10**9}


def quantity(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)(m|[KMG]i?)?', str(value))
    if not match:
        raise AssertionError(f'unsupported resource quantity: {value!r}')
    return Decimal(match[1]) * MULTIPLIERS[match[2] or '']


class CriticalServiceQoS(unittest.TestCase):
    def test_gateway_containers_have_positive_equal_requests_and_limits(self):
        manifests = yaml.safe_load_all(
            (ROOT / 'config/k3s/manifests/50-factory-gateway.yaml').read_text())
        gateway = next(doc for doc in manifests if doc and doc.get('kind') == 'Deployment'
                       and doc['metadata']['name'] == 'factory-gateway')
        spec = gateway['spec']['template']['spec']
        for container in spec.get('initContainers', []) + spec['containers']:
            for resource in ('cpu', 'memory'):
                with self.subTest(container=container['name'], resource=resource):
                    resources = container.get('resources', {})
                    request = quantity(resources.get('requests', {}).get(resource, 0))
                    limit = quantity(resources.get('limits', {}).get(resource, 0))
                    self.assertGreater(limit, 0)
                    self.assertEqual(request, limit, 'unequal resources lose Guaranteed QoS')


if __name__ == '__main__':
    unittest.main()
