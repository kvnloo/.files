"""Memory drift law (scripts/memory-drift): red on today's known drift, green when live == intent."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('memory_drift', str(ROOT / 'scripts/memory-drift'))
spec = importlib.util.spec_from_loader(loader.name, loader)
law = importlib.util.module_from_spec(spec)
loader.exec_module(law)


class FakeHost(law.Host):
    def __init__(self, tmp, show, files, cgroups, procs=None, controls=None, sysctls=None):
        self.tmp = Path(tmp)
        self._show = show
        self._files = files
        self._cgroups = cgroups
        self._procs = procs or {}
        self._controls = controls or {}
        self._sysctls = sysctls or {}

    def cgroup_file(self, path, name):
        return self._cgroups[f'{path}/{name}']

    def show(self, scope, unit, prop):
        if prop == 'DropInPaths':
            return ' '.join(p for p in self._files if p.startswith(f'/d/{unit}.d/'))
        if prop == 'FragmentPath':
            return ''
        return self._show[(unit, prop)]

    def read_text(self, path):
        return self._files[path]

    def control_dirs(self, scope, unit):
        directory = self.tmp / unit
        if unit in self._controls:
            directory.mkdir(exist_ok=True)
            for name, text in self._controls[unit].items():
                (directory / name).write_text(text)
        return [directory]

    def pids(self, comm):
        return [pid for pid, (c, _) in self._procs.items() if c == comm]

    def pid_cgroup(self, pid):
        return self._procs[pid][1]

    def sysctl(self, key):
        return self._sysctls[key]


INTENT = tomllib.loads('''
[[unit]]
unit = "agent.slice"
property = "MemoryMax"
equals = "10G"
owner = "60-guard.conf"

[[cgroup]]
group = "app"
path = "u/app.slice"
file = "memory.max"
equals = "8G"

[[placement]]
comm = "Hyprland"
under = "session.slice"

[[sysctl]]
key = "vm.swappiness"
equals = "180"
''')

GREEN = dict(
    show={('agent.slice', 'MemoryMax'): '10737418240'},
    files={'/d/agent.slice.d/50-budget.conf': '[Slice]\nCPUWeight=30\n',
           '/d/agent.slice.d/60-guard.conf': '[Slice]\nMemoryMax=10G\n'},
    cgroups={'u/app.slice/memory.max': '8589934592'},
    procs={7: ('Hyprland', '/user.slice/u/session.slice/wayland-wm@hyprland.desktop.service')},
    sysctls={'vm.swappiness': '180'},
)


class MemoryDriftLaw(unittest.TestCase):
    def audit(self, groups=None, **change):
        with tempfile.TemporaryDirectory() as tmp:
            host = FakeHost(tmp, **{**GREEN, **change})
            return law.audit(INTENT, host, groups)

    def test_green_when_live_equals_intent(self):
        rows = self.audit()
        self.assertTrue(all(row['ok'] for row in rows), rows)
        self.assertEqual(len(rows), 4)

    def test_red_when_effective_value_differs(self):
        rows = self.audit(cgroups={'u/app.slice/memory.max': 'max'})
        self.assertFalse(next(r for r in rows if r['kind'] == 'cgroup')['ok'])

    def test_red_when_later_sorting_dropin_shadows_owner(self):
        files = {**GREEN['files'], '/d/agent.slice.d/70-other.conf': '[Slice]\nMemoryMax=10G\n'}
        rows = self.audit(files=files)
        unit = next(r for r in rows if r['kind'] == 'unit')
        self.assertFalse(unit['ok'])
        self.assertIn('shadows', unit['problems'][0])

    def test_red_on_set_property_residue(self):
        rows = self.audit(controls={'agent.slice': {'50-MemoryMax.conf': '[Slice]\nMemoryMax=15032385536\n'}})
        unit = next(r for r in rows if r['kind'] == 'unit')
        self.assertFalse(unit['ok'])
        self.assertIn('runtime override', ' '.join(unit['problems']))

    def test_red_when_ui_process_left_protected_subtree(self):
        rows = self.audit(procs={7: ('Hyprland', '/user.slice/u/app.slice/x.scope')})
        self.assertFalse(next(r for r in rows if r['kind'] == 'placement')['ok'])

    def test_unreadable_value_is_drift_not_pass(self):
        rows = self.audit(cgroups={})
        self.assertFalse(next(r for r in rows if r['kind'] == 'cgroup')['ok'])

    def test_group_filter(self):
        rows = self.audit(groups={'app'})
        self.assertEqual([r['kind'] for r in rows], ['cgroup'])

    def test_repo_intent_parses_and_names_owned_files(self):
        intent = tomllib.loads((ROOT / 'config/host/groot-memory-intent.toml').read_text())
        dropins = {p.name for p in (ROOT / 'config/systemd/user').glob('*.d/*.conf')}
        for row in intent['unit']:
            if 'owner' in row:
                self.assertIn(row['owner'], dropins, row)


if __name__ == '__main__':
    unittest.main()
