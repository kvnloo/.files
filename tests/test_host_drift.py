import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('host_drift', str(ROOT / 'scripts/host-drift'))
spec = importlib.util.spec_from_loader(loader.name, loader)
drift = importlib.util.module_from_spec(spec)
loader.exec_module(drift)
loader = importlib.machinery.SourceFileLoader('install_host_drift', str(ROOT / 'scripts/install-host-drift'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


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
        text = '[Service]\nMemoryHigh=infinity\nMemoryMax=256M\nCPUQuota=200%\n'
        (self.root / self.source).write_text(text)
        self.live.write_text(text)
        self.manifest(scope='user')
        self.assertEqual(self.run_audit()['status'], 'unknown')
        self.assertEqual(self.run_audit({'MemoryHigh': 'infinity', 'MemoryMax': '268435456', 'CPUQuotaPerSecUSec': '2s'})['status'], 'clean')
        report = self.run_audit({'MemoryHigh': '1024', 'MemoryMax': '268435456', 'CPUQuotaPerSecUSec': '2s'})
        self.assertEqual(report['status'], 'drift')
        self.assertEqual(report['drift'][0]['detail']['property'], 'MemoryHigh')

    def test_private_exception_never_claims_verified_content(self):
        self.live.write_text('private content must not enter output')
        self.live.chmod(0o600)
        self.manifest('secret=\"private-exception\"')
        report = self.run_audit()
        self.assertEqual(report['status'], 'unknown')
        self.assertNotIn('private content', json.dumps(report))
        self.assertEqual(report['drift'], [])
        self.live.chmod(0o644)
        self.assertEqual(self.run_audit()['drift'][0]['kind'], 'private_file_permissions')

    def test_mask_is_exact_dev_null_not_an_empty_copy(self):
        (self.root / self.source).write_text('')
        self.live.write_text('')
        self.manifest('mask=true')
        self.assertEqual(self.run_audit()['drift'][0]['kind'], 'mask_changed')
        self.live.unlink()
        self.live.symlink_to('/dev/null')
        self.assertEqual(self.run_audit()['status'], 'clean')

    def test_owned_upstream_drift_stays_nonclean(self):
        self.live.write_text('changed')
        self.manifest('drift=\"owned-upstream\"\\nissue=\"https://example.test/issue/1\"')
        report = self.run_audit()
        self.assertEqual(report['status'], 'drift')
        self.assertEqual(report['drift'][0]['classification'], 'owned-upstream')

    def test_continuous_budget_keeps_unbounded_groups_unknown(self):
        self.manifest('[budget]\ndesktop="session.slice"\ngroups=[{scope="user",unit="agent.slice"}]')
        maximum = ['60']
        def run(args):
            if args[0] == 'git':
                return self.source
            unit = args[3]
            if unit == 'session.slice':
                return 'MemoryMin=50\nControlGroup=/desktop\n'
            return f'MemoryMax={maximum[0]}\nControlGroup=/agent\n'
        def audit():
            with patch.object(drift.os, 'sysconf', side_effect=[100, 1]):
                return drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc], run)
        self.assertEqual(audit()['drift'][0]['kind'], 'desktop_budget')
        maximum[0] = '50'
        self.assertEqual(audit()['status'], 'clean')
        maximum[0] = 'infinity'
        self.assertEqual(audit()['status'], 'unknown')


class InstallerTests(unittest.TestCase):
    def test_dry_run_and_idempotent_content_stamped_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = base / 'repo', base / 'home'
            for name in installer.CLOSURE:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture\\n')
            (source / 'config/host/groot.toml').write_text('')
            with patch.object(installer.subprocess, 'check_output', return_value='\\n'.join(installer.CLOSURE)), \
                 patch.object(installer.subprocess, 'run') as run:
                self.assertEqual(installer.install(source, home, False), 0)
                self.assertFalse(home.exists())
                self.assertFalse(run.called)
                self.assertEqual(installer.install(source, home, True), 0)
                target = (home / '.local/bin/host-drift').resolve()
                self.assertNotEqual(target, source / 'scripts/host-drift')
                self.assertEqual(len(target.parents[1].name), 64)
                self.assertTrue((home / '.config/z0-guard/state.json').is_symlink())
                self.assertEqual(installer.install(source, home, True), 0)
                self.assertEqual((home / '.local/bin/host-drift').resolve(), target)
                self.assertNotIn('restart', ' '.join(str(call) for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
