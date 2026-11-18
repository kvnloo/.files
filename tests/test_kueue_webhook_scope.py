import pathlib
import runpy
import unittest

MOD = runpy.run_path(str(pathlib.Path(__file__).parents[1] / 'scripts/kueue-webhook-scope'))


def hook(name, resources, policy='Fail'):
    return {'name': name, 'failurePolicy': policy, 'rules': [{'resources': resources}]}


class KueueWebhookScope(unittest.TestCase):
    def test_disabled_integrations_relaxed_enabled_kept(self):
        cfg = {'webhooks': [hook('mdeployment.kb.io', ['deployments']), hook('mjob.kb.io', ['jobs']),
                            hook('mpod.kb.io', ['pods']), hook('mjobset.kb.io', ['jobsets']),
                            hook('mraycluster.kb.io', ['rayclusters'])]}
        ops = MOD['relax_patches'](cfg)
        self.assertEqual([o['path'] for o in ops], ['/webhooks/0/failurePolicy', '/webhooks/2/failurePolicy'])
        self.assertTrue(all(o['value'] == 'Ignore' for o in ops))

    def test_mixed_rules_stay_fail_closed_and_idempotent(self):
        cfg = {'webhooks': [hook('mixed', ['pods', 'jobs']), hook('done', ['pods'], 'Ignore'),
                            hook('sub', ['deployments/status'])]}
        self.assertEqual([o['path'] for o in MOD['relax_patches'](cfg)], ['/webhooks/2/failurePolicy'])


if __name__ == '__main__':
    unittest.main()
