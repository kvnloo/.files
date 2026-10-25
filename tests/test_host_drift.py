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

    def manifest(self, extra='', scope='system', install='copy'):
        (self.root / 'config/host/groot.toml').write_text(
            f'[[{scope}]]\nlive={json.dumps(str(self.live))}\nsource="{self.source}"\n'
            f'scope="{scope}"\ninstall="{install}"\nowner="fixture"\nreason="test"\n{extra}')

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

    def test_exhausted_command_deadline_is_unknown(self):
        with patch.object(drift.time, 'monotonic', side_effect=[0, 121]), \
             patch.object(drift, 'command') as run:
            report = drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc], run=run)
        self.assertEqual(report['status'], 'unknown')
        self.assertFalse(run.called)

    def test_untracked_source(self):
        self.source = 'config/host/not-tracked.conf'
        self.manifest()
        report = self.run_audit()
        self.assertEqual(report['status'], 'drift')
        self.assertEqual(report['drift'][0]['kind'], 'untracked_source')

    def test_generated_source_compares_offline_render_and_fails_unknown(self):
        generator = self.root / 'scripts/render'
        generator.parent.mkdir()
        generator.write_text('offline fixture')
        self.manifest('generator="scripts/render --render fixture.service"', install='generated')
        fails = [False]
        def run(args):
            if args[0] == 'git':
                return self.source + '\nscripts/render'
            if fails[0]:
                raise ValueError('render failed')
            self.assertEqual(args, [str(generator), '--render', 'fixture.service'])
            return 'safe\n'
        def audit():
            return drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc], run)
        self.assertEqual(audit()['status'], 'clean')
        self.live.write_text('wrong')
        self.assertEqual(audit()['drift'][0]['kind'], 'changed_file')
        fails[0] = True
        self.assertEqual(audit()['status'], 'unknown')

    def test_checkout_symlink_even_when_content_agrees(self):
        checkout = self.base / 'arbitrary-name'
        checkout.mkdir()
        (checkout / '.git').write_text('gitdir: elsewhere')
        target = checkout / 'file'
        target.write_text('safe\n')
        self.live.unlink()
        self.live.symlink_to(target)
        self.assertIn('checkout_symlink', {row['kind'] for row in self.run_audit()['drift']})

    def test_relative_wants_link_reaches_stamped_release(self):
        release = self.home / '.local/lib/fixture' / ('a' * 64)
        release.mkdir(parents=True)
        target = release / 'fixture.service'
        target.write_text('safe\n')
        unit = self.home / '.config/systemd/user/fixture.service'
        unit.parent.mkdir(parents=True)
        unit.symlink_to(target)
        self.live = unit.parent / 'default.target.wants/fixture.service'
        self.live.parent.mkdir()
        self.live.symlink_to('../fixture.service')
        self.manifest(install='symlink-stamped')
        self.assertEqual(self.run_audit()['status'], 'clean')
        physical = self.base / 'physical-files-live'
        destination = physical / ('b' * 64) / 'fixture.service'
        destination.parent.mkdir(parents=True)
        destination.write_text('safe\n')
        unit.unlink()
        unit.symlink_to(destination)
        with patch.object(drift, 'PHYSICAL_RELEASE_ROOT', physical):
            self.assertEqual(self.run_audit()['status'], 'clean')
        self.assertEqual(self.run_audit()['drift'][0]['kind'], 'unstamped_install')

    def test_declared_git_stamp_requires_identity_and_exact_source(self):
        physical = self.base / 'releases'
        release = physical / 'fixture' / ('c' * 40)
        target = release / self.source
        target.parent.mkdir(parents=True)
        target.write_text('safe\n')
        self.live.unlink()
        self.live.symlink_to(target)
        self.manifest('stamp_name="fixture"', install='symlink-stamped')
        stamp = release / '.deployment-stamp.json'
        stamp.write_text(json.dumps({'name': 'fixture', 'source_sha': 'c' * 40}))
        with patch.object(drift, 'DEPLOYMENT_RELEASE_ROOT', physical):
            self.assertEqual(self.run_audit()['status'], 'clean')
            stamp.write_text(json.dumps({'name': 'different', 'source_sha': 'c' * 40}))
            self.assertIn('unstamped_install', {r['kind'] for r in self.run_audit()['drift']})
            stamp.unlink()
            self.assertEqual(self.run_audit()['status'], 'unknown')

    def test_pacnew_deduplicates_and_pending_action_stays_drift(self):
        candidate = self.live.with_name(self.live.name + '.pacnew')
        candidate.write_text('package update\n')
        self.manifest('\n[[pending_action]]\npaths=[' + json.dumps(str(candidate)) +
                      ']\nowner="Kevin"\ncommand="sudo review-package"\nreason="manual review"')
        report = self.run_audit()
        self.assertEqual(report['status'], 'drift')
        self.assertEqual(len(report['drift']), 1)
        self.assertEqual(report['drift'][0]['disposition'], 'pending-owner-action')
        self.assertEqual(report['drift'][0]['command'], 'sudo review-package')

    def test_root_slice_is_not_a_dashed_prefix_or_cli_option(self):
        self.live = self.etc / 'systemd/system/-.slice.d/50-policy.conf'
        self.live.parent.mkdir(parents=True)
        text = '[Slice]\nMemoryMin=0\n'
        (self.root / self.source).write_text(text)
        self.live.write_text(text)
        self.manifest()
        def run(args):
            if args[0] == 'git':
                return self.source
            self.assertEqual(args[-2:], ['--', '-.slice'])
            return 'MemoryMin=0'
        self.assertEqual(drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc], run)['status'], 'clean')

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

    def test_prefix_and_template_compare_loaded_instances_not_fake_units(self):
        for name in ('hermes-worker-.scope', 'worker@.service'):
            self.live = self.home / '.config/systemd/user' / (name + '.d') / '50-budget.conf'
            self.live.parent.mkdir(parents=True)
            text = '[Scope]\nMemoryMax=256M\n'
            (self.root / self.source).write_text(text)
            self.live.write_text(text)
            self.manifest(scope='user')
            names = ['hermes-worker-123.scope' if name.endswith('scope') else 'worker@123.service']
            def run(args):
                if args[0] == 'git':
                    return self.source
                if args[2] == 'list-units':
                    return '\n'.join(unit + ' loaded active running fixture' for unit in names)
                self.assertIn(args[-1], names)
                return 'MemoryMax=268435456'
            def audit():
                return drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc], run)
            self.assertEqual(audit()['status'], 'clean')
            names.clear()
            report = audit()
            self.assertEqual(report['status'], 'clean')
            self.assertEqual(len(report['not_applicable']), 1)

    def test_io_latency_uses_kernel_target_not_missing_systemctl_scalar(self):
        self.live = self.home / '.config/systemd/user/session.slice.d/50-io.conf'
        self.live.parent.mkdir(parents=True)
        text = '[Slice]\nIODeviceLatencyTargetSec=/dev/null 10ms\n'
        (self.root / self.source).write_text(text)
        self.live.write_text(text)
        self.manifest(scope='user')
        cgroup = self.base / 'cgroups/session.slice'
        cgroup.mkdir(parents=True)
        path = cgroup / 'io.latency'
        path.write_text('1:3 target=10000\n')
        def run(args):
            return self.source if args[0] == 'git' else '/session.slice'
        def audit():
            return drift.audit(self.root, self.home, self.runtime, self.leases, [self.etc],
                               run=run, cgroup_root=self.base / 'cgroups')
        self.assertEqual(audit()['status'], 'clean')
        path.write_text('1:3 target=0\n')
        self.assertEqual(audit()['drift'][0]['kind'], 'io_latency_effective')
        path.unlink()
        self.assertEqual(audit()['status'], 'unknown')

    def test_private_exception_never_claims_verified_content(self):
        self.live.write_text('SENSITIVE_FIXTURE_must_not_enter_output')
        self.live.chmod(0o600)
        self.manifest('secret=\"private-exception\"')
        report = self.run_audit()
        self.assertEqual(report['status'], 'unknown')
        self.assertNotIn('SENSITIVE_FIXTURE', json.dumps(report))
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
        self.manifest('drift="owned-upstream"\nissue="https://example.test/issue/1"')
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
                path.write_text('fixture\n')
            (source / 'config/host/groot.toml').write_text('')
            with patch.object(installer.subprocess, 'check_output', return_value='\n'.join(installer.CLOSURE)), \
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
