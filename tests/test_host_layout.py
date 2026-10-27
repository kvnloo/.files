import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import host_admission  # noqa: E402
from host_admission import Hosts, LINK, Live, Mount, Parent, Reason  # noqa: E402
import host_layout  # noqa: E402

FAKE_HOME = Path('/home/user')


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


installer = load('host_layout_user_installer', 'scripts/apply-agent-oom')
drift = load('host_layout_drift', 'scripts/host-drift')
materializer = load('host_layout_materialize', 'scripts/materialize-checkout-dir')


class FleetResolutionTests(unittest.TestCase):
    """The real fleet.toml: each host owns exactly its manifest and storage."""

    def test_groot_keeps_bulk_layout(self):
        import tomllib
        storage = tomllib.loads((ROOT / 'fleet.toml').read_text())['hosts']['desktop']['storage']
        for name in ('groot', '0'):
            layout = host_layout.resolve(ROOT, hostname=name, home=FAKE_HOME)
            self.assertEqual(layout.manifest, 'config/host/groot.toml')
            self.assertEqual(layout.release_root, Path(storage['release_root']))
            self.assertEqual(layout.release_mount, Path(storage['release_mount']))
            self.assertTrue(layout.release_root.is_relative_to(layout.release_mount))

    def test_mbp_uses_its_own_manifest_on_the_internal_disk(self):
        layout = host_layout.resolve(ROOT, hostname='mbp', home=FAKE_HOME)
        self.assertEqual(layout.manifest, 'config/host/mbp.toml')
        self.assertEqual(layout.release_root, FAKE_HOME / '.local/lib/releases')
        self.assertIsNone(layout.release_mount)
        self.assertTrue((ROOT / layout.manifest).is_file())

    def test_operations_state_follows_the_host(self):
        """service-watch state: desktop keeps its model-volume path, mbp stays in its home, never /mnt."""
        self.assertEqual(host_layout.resolve(ROOT, hostname='groot', home=FAKE_HOME).operations_root,
                         Path('/mnt/zer0models/workspace/zer0/data/operations'))
        mbp = host_layout.resolve(ROOT, hostname='mbp', home=FAKE_HOME).operations_root
        self.assertEqual(mbp, FAKE_HOME / '.local/state/z0/operations')
        watch = load('host_layout_service_watch', 'scripts/service-watch.py')
        with patch('socket.gethostname', return_value='mbp'):
            self.assertEqual(watch.operations_root(ROOT, home=FAKE_HOME), mbp)
        with tempfile.TemporaryDirectory() as tmp:  # an older closure without fleet.toml
            self.assertEqual(watch.operations_root(Path(tmp), home=FAKE_HOME), watch.LEGACY_OPERATIONS)

    def test_every_declared_manifest_exists(self):
        import tomllib
        fleet = tomllib.loads((ROOT / 'fleet.toml').read_text())
        for host_id, cfg in fleet['hosts'].items():
            if 'manifest' in cfg:
                self.assertTrue((ROOT / cfg['manifest']).is_file(), host_id)

    def test_unknown_host_never_falls_back_to_groot(self):
        with self.assertRaisesRegex(ValueError, 'matched no fleet host'):
            host_layout.resolve(ROOT, hostname='not-a-fleet-host')

    def test_ambiguous_and_undeclared_hosts_refuse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'fleet.toml').write_text('[hosts.a]\nmatch_hostnames=["x"]\nmanifest="config/host/a.toml"\n'
                                             '[hosts.b]\nmatch_hostnames=["x"]\nmanifest="config/host/b.toml"\n'
                                             '[hosts.c]\nmatch_hostnames=["y"]\n'
                                             '[hosts.d]\nmatch_hostnames=["z"]\nmanifest="../escape.toml"\n')
            with self.assertRaisesRegex(ValueError, 'more than one fleet host'):
                host_layout.resolve(root, hostname='x')
            for name in ('y', 'z'):
                with self.assertRaisesRegex(ValueError, 'declares no config/host manifest'):
                    host_layout.resolve(root, hostname=name)

    def test_unmounted_bulk_refuses_only_fresh_trees(self):
        with patch.object(host_layout.os.path, 'ismount', return_value=False), \
             patch.object(host_layout.socket, 'gethostname', return_value='groot'):
            with self.assertRaisesRegex(ValueError, 'not mounted'):
                host_layout.require_release_mount(ROOT, FAKE_HOME, fresh=True)
            host_layout.require_release_mount(ROOT, FAKE_HOME, fresh=False)
        with patch.object(host_layout.socket, 'gethostname', return_value='mbp'):
            host_layout.require_release_mount(ROOT, FAKE_HOME, fresh=True)


class TwinTests(unittest.TestCase):
    def test_refusal_order_matches_model(self):
        self.assertIs(host_admission.decide(Hosts.NONE, False, Parent.THROUGH_CHECKOUT, Live.CHANGED,
                                            Mount.UNMOUNTED, True), Reason.NO_HOST)
        self.assertIs(host_admission.decide(Hosts.ONE, True, Parent.THROUGH_CHECKOUT, Live.CHANGED,
                                            Mount.UNMOUNTED, True), Reason.THROUGH_CHECKOUT)
        self.assertEqual(host_admission.decide(Hosts.ONE, True, Parent.REAL, Live.INVENTORIED,
                                               Mount.UNMOUNTED, False), LINK)


def git_checkout(path):
    path.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    return path


class CheckoutDirectoryLinkTests(unittest.TestCase):
    """Red/green for 2026-10-25 mbp: ~/.config/systemd/user -> ~/workspace/.files/config/systemd/user."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / 'home'
        self.checkout = git_checkout(self.home / 'workspace/.files')
        self.unit = 'config/systemd/user/z0int-loop-tick.timer'
        tracked = self.checkout / self.unit
        tracked.parent.mkdir(parents=True)
        tracked.write_text('[Timer]\nOnCalendar=hourly\n')
        (tracked.parent / 'timers.target.wants').mkdir()
        (tracked.parent / 'timers.target.wants/z0int-loop-tick.timer').symlink_to(
            self.home / '.config/systemd/user/z0int-loop-tick.timer')
        (tracked.parent / 'host-local.service').write_text('[Service]\nExecStart=/bin/true\n')
        self.live_dir = self.home / '.config/systemd/user'
        self.live_dir.parent.mkdir(parents=True)
        self.live_dir.symlink_to(self.checkout / 'config/systemd/user')
        self.source = base / 'source'
        (self.source / self.unit).parent.mkdir(parents=True)
        (self.source / self.unit).write_text(tracked.read_text())
        (self.source / 'config/host').mkdir(parents=True)
        (self.source / 'fleet.toml').write_text('[hosts.fixture]\nmatch_hostnames=[' + json.dumps(host_layout.socket.gethostname()) +
                                                ']\nmanifest="config/host/fixture.toml"\n')
        (self.source / 'config/host/fixture.toml').write_text(
            '[[user]]\nlive="~/.config/systemd/user/z0int-loop-tick.timer"\nsource=' + json.dumps(self.unit) +
            '\nscope="user"\ninstall="symlink-stamped"\nowner="scripts/apply-agent-oom"\nreason="fixture"\n')
        (self.source / 'tracked-files.json').write_text(json.dumps([self.unit, 'config/host/fixture.toml']))
        self.ok = subprocess.CompletedProcess([], 0, 'MemoryCurrent=1\nMemorySwapCurrent=0\n', '')

    def checkout_status(self):
        return subprocess.run(['git', '-C', str(self.checkout), 'status', '--porcelain', '--untracked-files=all'],
                              capture_output=True, text=True, check=True).stdout

    @patch.object(installer.subprocess, 'run')
    def test_red_installer_refuses_to_write_into_the_checkout(self, run):
        run.return_value = self.ok
        before = self.checkout_status()
        with self.assertRaisesRegex(ValueError, 'through checkout directory link'):
            installer.install_user_layer(self.source, self.home, True)
        self.assertEqual(self.checkout_status(), before)
        self.assertFalse((self.home / '.local/lib/files-live').exists())

    def test_red_drift_reports_the_directory_link(self):
        report = drift.audit(self.source, self.home, self.home / 'run', self.home / 'leases', [])
        kinds = {row['kind'] for row in report['drift']}
        self.assertIn('checkout_directory_link', kinds)
        self.assertNotEqual(report['status'], 'clean')

    @patch.object(installer.subprocess, 'run')
    def test_green_after_materialize_and_stamp(self, run):
        run.return_value = self.ok
        before = self.checkout_status()
        with patch.object(materializer.Path, 'home', return_value=self.home):
            self.assertEqual(materializer.materialize(self.live_dir, self.home, False), 0)
            self.assertTrue(self.live_dir.is_symlink())
            self.assertEqual(materializer.materialize(self.live_dir, self.home, True), 0)
        self.assertFalse(self.live_dir.is_symlink())
        self.assertEqual((self.live_dir / 'host-local.service').read_text(), '[Service]\nExecStart=/bin/true\n')
        self.assertTrue((self.live_dir / 'timers.target.wants/z0int-loop-tick.timer').is_symlink())
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        live = self.live_dir / 'z0int-loop-tick.timer'
        self.assertTrue(live.is_symlink())
        self.assertTrue(live.resolve().is_relative_to(self.home / '.local/lib/files-live'))
        self.assertEqual(self.checkout_status(), before)
        report = drift.audit(self.source, self.home, self.home / 'run', self.home / 'leases', [],
                             run=lambda args: '')
        self.assertEqual([row for row in report['drift'] if row['path'] == str(live)], [])
        # A later checkout edit can no longer reach the live unit.
        (self.checkout / self.unit).write_text('[Timer]\nOnCalendar=minutely\n')
        self.assertEqual(live.read_text(), '[Timer]\nOnCalendar=hourly\n')

    def test_exec_from_checkout_red_and_green(self):
        # 2026-10-25 mbp: z0int-loop-tick ran %h/workspace/z0intelligence-pinned/.venv/bin/python.
        service = 'config/systemd/user/z0int-loop-tick.service'
        (self.source / service).write_text('[Service]\nExecStart=/x\n')
        manifest = self.source / 'config/host/fixture.toml'
        manifest.write_text(manifest.read_text() + '[[user]]\nlive="~/.config/systemd/user/z0int-loop-tick.service"\n'
                            'source=' + json.dumps(service) + '\nscope="user"\ninstall="copy"\nowner="fixture"\nreason="fixture"\n')
        (self.source / 'tracked-files.json').write_text(json.dumps([self.unit, service, 'config/host/fixture.toml']))
        self.live_dir.unlink()
        self.live_dir.mkdir()
        (self.live_dir / 'z0int-loop-tick.service').write_text('[Service]\nExecStart=/x\n')
        checkout_python = self.home / 'workspace/z0intelligence-pinned/.venv/bin/python'
        git_checkout(self.home / 'workspace/z0intelligence-pinned')
        stamped = self.home / '.local/lib/z0int-shadow/current/.venv/bin/python'
        def audit(state, path):
            def run(args):
                return (f'UnitFileState={state}\nExecStart={{ path={path} ; argv[]={path} -m z0int.cli loop tick }}\n'
                        f'WorkingDirectory={self.home}\n')
            return drift.audit(self.source, self.home, self.home / 'run', self.home / 'leases', [], run=run)
        red = audit('static', checkout_python)
        self.assertIn('exec_from_checkout', {row['kind'] for row in red['drift']})
        disabled = audit('disabled', checkout_python)
        self.assertNotIn('exec_from_checkout', {row['kind'] for row in disabled['drift']})
        self.assertIn('exec_from_checkout_disabled', {row['kind'] for row in disabled['not_applicable']})
        green = audit('static', stamped)
        self.assertNotIn('exec_from_checkout', {row['kind'] for row in green['drift']})

    def test_stamped_host_drift_closure_runs(self):
        # 2026-10-26: the stamped release lacked host_admission.py and crashed on import.
        installer_mod = load('host_layout_drift_installer', 'scripts/install-host-drift')
        tracked = set(subprocess.run(['git', '-C', str(ROOT), 'ls-files'], capture_output=True, text=True,
                                     check=True).stdout.split())
        names = set(installer_mod.CLOSURE)
        for name in sorted(names):
            self.assertIn(name, tracked, name)
        with tempfile.TemporaryDirectory() as temp:
            stamp = Path(temp)
            for name in names:
                (stamp / name).parent.mkdir(parents=True, exist_ok=True)
                (stamp / name).write_bytes((ROOT / name).read_bytes())
            (stamp / 'scripts/host-drift').chmod(0o755)
            proc = subprocess.run([sys.executable, '-I', str(stamp / 'scripts/host-drift'), '--help'],
                                  capture_output=True, text=True, cwd=temp)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_materialize_refuses_non_checkout_links(self):
        other = self.home / 'plain'
        other.mkdir()
        link = self.home / '.config/plain'
        link.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'not a directory link into a git checkout'):
            materializer.materialize(link, self.home, True)


if __name__ == '__main__':
    unittest.main()
