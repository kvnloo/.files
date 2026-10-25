import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('host_drift', str(ROOT / 'scripts/host-drift'))
spec = importlib.util.spec_from_loader(loader.name, loader)
drift = importlib.util.module_from_spec(spec)
loader.exec_module(drift)


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.home = self.base / 'home'
        self.runtime = self.base / 'run'
        self.leases = self.base / 'leases'
        self.etc = self.base / 'etc'
        self.etc.mkdir()
        (self.root / 'config/host').mkdir(parents=True)
        self.source = 'config/host/source.conf'
        (self.root / self.source).write_text('safe\n')
        self.live = self.etc / 'source.conf'
        self.live.write_text('safe\n')
        self.manifest()

    def manifest(self, extra='', scope='system'):
        (self.root / 'config/host/groot.toml').write_text(
            f'[[{scope}]]\nlive={json.dumps(str(self.live))}\nsource="{self.source}"\n'
            f'scope="{scope}"\ninstall="copy"\nowner="fixture"\nreason="test"\n{extra}')

    def run_audit(self, properties=None):
        def run(args):
            if args[0] == 'git':
                return 'config/host/source.conf\n'
            if args[0] == 'sysctl':
                return (properties or {}).get(args[-1], '42')
            if args[0] == 'systemctl':
                if properties is None:
                    raise ValueError('manager unavailable')
                return '\n'.join(f'{key}={value}' for key, value in properties.items())
            raise AssertionError(args)
        return drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc], run)

    def test_clean_and_changed_and_missing(self):
        self.assertEqual(self.run_audit()['status'], 'clean')
        self.live.write_text('changed')
        self.assertEqual(self.run_audit()['drift'][0]['kind'], 'changed_file')
        self.live.unlink()
        self.assertEqual(self.run_audit()['drift'][0]['kind'], 'missing_file')

    def test_missing_manifest_unknown_not_clean(self):
        (self.root / 'config/host/groot.toml').unlink()
        self.assertEqual(self.run_audit()['status'], 'unknown')

    def test_untracked_source(self):
        self.source = 'config/host/not-tracked.conf'
        self.manifest()
        report = self.run_audit()
        self.assertEqual(report['status'], 'drift')
        self.assertEqual(report['drift'][0]['kind'], 'untracked_source')

    def test_checkout_symlink_even_when_content_agrees(self):
        checkout = self.base / 'arbitrary-name'
        checkout.mkdir()
        (checkout / '.git').write_text('gitdir: elsewhere')
        target = checkout / 'file'
        target.write_text('safe\n')
        self.live.unlink()
        self.live.symlink_to(target)
        self.assertIn('checkout_symlink', {row['kind'] for row in self.run_audit()['drift']})

    def test_persistent_and_runtime_control_require_bound_leases(self):
        paths = [self.home / '.config/systemd/user.control/a.service.d/50-MemoryMax.conf',
                 self.runtime / 'systemd/user.control/b.service.d/50-MemoryMax.conf']
        for path in paths:
            path.parent.mkdir(parents=True)
            path.write_text('[Service]\nMemoryMax=1G\n')
        self.assertEqual(len(self.run_audit()['drift']), 2)
        self.leases.mkdir()
        for path in paths:
            lease = dict(schema='host-drift.lease.v1', path=str(path), owner='test',
                         expires_at=time.time() + 60, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            (self.leases / (hashlib.sha256(str(path).encode()).hexdigest() + '.json')).write_text(json.dumps(lease))
        self.assertEqual(self.run_audit()['status'], 'clean')
        paths[0].write_text('different')
        self.assertEqual(len(self.run_audit()['drift']), 1)

    def test_sysctl_values_and_pacnew(self):
        self.live = self.etc / 'sysctl.d/99-groot.conf'
        self.live.parent.mkdir()
        (self.root / self.source).write_text('vm.swappiness = 42\n')
        self.live.write_text('vm.swappiness = 42\n')
        self.manifest()
        self.assertEqual(self.run_audit()['status'], 'clean')
        (self.etc / 'new.pacnew').write_text('new')
        kinds = {row['kind'] for row in self.run_audit({'vm.swappiness': '43'})['drift']}
        self.assertEqual(kinds, {'pacnew', 'sysctl_effective'})

    def test_effective_resource_values_and_unknown_manager(self):
        self.live = self.home / '.config/systemd/user/a.service.d/50-budget.conf'
        self.live.parent.mkdir(parents=True)
        text = '[Service]\nMemoryHigh=infinity\nMemoryMax=256M\n'
        (self.root / self.source).write_text(text)
        self.live.write_text(text)
        self.manifest(scope='user')
        self.assertEqual(self.run_audit()['status'], 'unknown')
        self.assertEqual(self.run_audit({'MemoryHigh': 'infinity', 'MemoryMax': '268435456'})['status'], 'clean')
        report = self.run_audit({'MemoryHigh': '1024', 'MemoryMax': '268435456'})
        self.assertEqual(report['status'], 'drift')
        self.assertEqual(report['drift'][0]['detail']['property'], 'MemoryHigh')


if __name__ == '__main__':
    unittest.main()
