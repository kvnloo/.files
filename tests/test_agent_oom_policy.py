import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agent_oom_policy', ROOT / 'scripts/agent_oom_policy.py')
policy = importlib.util.module_from_spec(spec)
sys.modules['agent_oom_policy'] = policy
spec.loader.exec_module(policy)

USER = f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service'
DESK = USER + '/session.slice/wayland-wm@hyprland.desktop.service'
GATEWAY = USER + '/agent.slice/hermes-gateway.service'
SCOPE = USER + '/agent.slice/agent-hermes-22-1.scope'
HERMES = ('/x/python3', '-I', '-c', 'import sys\nfrom hermes_cli.main import main\nsys.exit(main())')


def P(pid, ppid, comm, args=(), exe='', cgroup=DESK, tty=0, start='100'):
    return policy.Proc(pid, ppid, comm, exe, tuple(args), cgroup, start, tty)


def session_tree():
    """Shapes taken from groot's live tree and the 2026-10-25 kill log."""
    procs = [
        P(1, 0, 'systemd', ['/usr/lib/systemd/systemd', '--user'], 'systemd', USER + '/init.scope'),
        P(10, 1, 'start-hyprland', ['start-hyprland'], 'start-hyprland'),
        P(11, 10, 'Hyprland', ['Hyprland'], 'Hyprland'),
        P(12, 11, 'tern', ['/x/tern'], 'tern'),                       # Tern GUI
        P(20, 1, 'tern', ['/x/tern', 'daemon', '--socket', 's'], 'tern'),
        P(21, 20, 'zsh', ['zsh'], 'zsh', tty=34816),                  # pane shell
        P(22, 21, 'hermes', [*HERMES, '--tui', 'tern'], 'python3.14', SCOPE, 34816),
        P(23, 22, 'node-MainThread', ['/x/node', '--expose-gc', '/p/hermes-tern/frontend/dist/entry.js'],
          'node', SCOPE, 34816),
        P(24, 22, 'bash', ['bash', '-c', 'tool'], 'bash', SCOPE),
        P(25, 24, 'python3', ['python3', 'tool.py'], 'python3.14', SCOPE),
        P(26, 24, 'hermes', [*HERMES, 'chat', '--query-file', 'q', '--oneshot'], 'python3.14', SCOPE),
        P(27, 26, 'bash', ['bash'], 'bash', SCOPE),
        P(28, 20, 'zsh', ['zsh'], 'zsh', tty=34817),                  # pane without an agent
        P(29, 28, 'cargo', ['cargo', 'build'], 'cargo', tty=34817),
        P(30, 1, 'hermes', [*HERMES, 'gateway', 'run'], 'python3.14', GATEWAY),
        P(31, 30, 'bash', ['bash', '-c', 'x'], 'bash', GATEWAY),
        P(32, 31, 'claude', ['claude', '-p', 'review'], 'claude', GATEWAY),
        P(33, 32, 'node-MainThread', ['node', '/x/mcp/server.js'], 'node', GATEWAY),
        P(34, 31, 'chromium', ['chromium', '--headless'], 'chromium', GATEWAY),
        P(41, 20, 'zsh', ['zsh'], 'zsh', tty=34818),
        P(40, 41, 'omp', ['/x/omp'], 'omp', USER + '/agent.slice/agent-omp-40-1.scope', 34818),
        P(42, 40, 'omp daemon brok', ['/x/omp', '__omp_worker_daemon_broker'], 'omp',
          USER + '/agent.slice/agent-omp-40-1.scope', 34818),
        P(50, 21, 'hermes', [*HERMES, '--tui'], 'python3.14', USER + '/agent.slice/agent-hermes-50-1.scope', 34816),
        P(51, 50, 'node-MainThread', ['/x/node', '/h/ui-tui/dist/entry.js'], 'node',
          USER + '/agent.slice/agent-hermes-50-1.scope', 34816),
        P(52, 51, 'python3', ['python3', '-m', 'tui_gateway.entry'], 'python3.14',
          USER + '/agent.slice/agent-hermes-50-1.scope', 34816),
        P(53, 52, 'bash', ['bash', '-c', 'tool'], 'bash', USER + '/agent.slice/agent-hermes-50-1.scope'),
    ]
    return {p.pid: p for p in procs}


MAINS = {'wayland-wm@hyprland.desktop.service': 10, 'hermes-gateway.service': 30}


class DecideTests(unittest.TestCase):
    def test_roots_their_renderers_and_everything_above_them_are_protected(self):
        protected, disposable, _ = policy.decide(session_tree(), MAINS)
        # Victims of 2026-10-25 20:30-20:44 at adj 800: Hermes TUI renderers, tern, omp.
        self.assertEqual(protected, {10, 11, 12, 20, 21, 22, 23, 30, 40, 41, 50, 51, 52})
        # Tools, MCP servers, the omp language-server broker and one-shot subagents.
        self.assertEqual(disposable, {24, 25, 26, 27, 31, 32, 33, 42, 53})

    def test_unrelated_work_and_desktop_programs_keep_their_score(self):
        protected, disposable, _ = policy.decide(session_tree(), MAINS)
        for pid in (1, 28, 29, 34):
            self.assertNotIn(pid, protected | disposable)

    def test_renamed_process_is_not_a_root(self):
        procs = session_tree()
        procs[60] = P(60, 21, 'hermes', ['bash', 'evil.sh'], 'bash', SCOPE)
        protected, _, _ = policy.decide(procs, MAINS)
        self.assertNotIn(60, protected)

    def test_interactive_session_an_agent_opened_on_its_own_terminal_is_a_root(self):
        procs = session_tree()
        procs[61] = P(61, 31, 'hermes', [*HERMES, '-p', 'clean'], 'python3.14', GATEWAY, tty=34900)
        procs[62] = P(62, 31, 'hermes', [*HERMES, '-p', 'clean'], 'python3.14', GATEWAY, tty=0)
        protected, disposable, _ = policy.decide(procs, MAINS)
        self.assertIn(61, protected)
        self.assertIn(62, disposable)

    def test_main_process_of_a_hermes_service_is_a_root(self):
        procs = session_tree()
        procs[70] = P(70, 1, 'python3', ['python3', '-I', '/x/hermes_link_api_host.py'], 'python3.14',
                      USER + '/app.slice/garden-room-hermes-gateway.service')
        procs[71] = P(71, 70, 'ffmpeg', ['ffmpeg'], 'ffmpeg', USER + '/app.slice/garden-room-hermes-gateway.service')
        procs[72] = P(72, 1, 'python3', ['python3', 'x.py'], 'python3.14', USER + '/app.slice/myhermesx.service')
        mains = {**MAINS, 'garden-room-hermes-gateway.service': 70, 'myhermesx.service': 72}
        protected, disposable, _ = policy.decide(procs, mains)
        self.assertIn(70, protected)
        self.assertIn(71, disposable)
        self.assertNotIn(72, protected)

    def test_background_maintenance_units_are_batch(self):
        procs = session_tree()
        for pid, unit in ((90, 'agentsview-sync.service'), (91, 'ctx-import.service'),
                          (92, 'z0int-choice-ef6bedc1.service'), (93, 'agentsview.service')):
            procs[pid] = P(pid, 1, 'x', ['x'], 'x', USER + '/app.slice/' + unit)
        procs[94] = P(94, 92, 'python', ['python'], 'python', USER + '/app.slice/z0int-choice-ef6bedc1.service')
        protected, disposable, batch = policy.decide(procs, MAINS)
        self.assertEqual(batch, {90, 91, 92, 94})
        self.assertFalse(batch & (protected | disposable))

    def test_dashboard_launched_as_module_is_a_root(self):
        procs = session_tree()
        procs[80] = P(80, 1, 'hermes', ['/x/python3', '-m', 'hermes_cli.main', 'dashboard'], 'python3.14',
                      USER + '/app.slice/web.service')
        protected, _, _ = policy.decide(procs, MAINS)
        self.assertIn(80, protected)


class FakeProc:
    """A /proc where unprivileged writes below the inherited floor are refused."""

    def __init__(self, scores, starts=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.refused = 0
        for pid, score in scores.items():
            base = self.root / str(pid)
            base.mkdir()
            start = (starts or {}).get(pid, '100')
            (base / 'stat').write_text(f'{pid} (x y) ' + ' '.join(['S'] + ['0'] * 18 + [start]))
            (base / 'oom_score_adj').write_text(f'{score}\n')

    def write(self, proc, pid, value):
        if value < policy.FLOOR_ADJ:
            self.refused += 1
            raise PermissionError(13, 'Permission denied')
        (proc / str(pid) / 'oom_score_adj').write_text(str(value))

    def score(self, pid):
        return int((self.root / str(pid) / 'oom_score_adj').read_text())


class ApplyTests(unittest.TestCase):
    def run_apply(self, fake, procs, protected, disposable, lowered=None, checked=None):
        lowered = {} if lowered is None else lowered
        checked = set() if checked is None else checked
        with patch.object(policy, '_write_adj', fake.write):
            return policy.apply(procs, protected, disposable, lowered, checked, fake.root), lowered, checked

    def test_protected_go_to_the_floor_disposable_up_never_the_other_way(self):
        procs = {pid: P(pid, 1, f'p{pid}') for pid in (2, 3, 4, 5, 6)}
        fake = FakeProc({2: 200, 3: 800, 4: 200, 5: 999, 6: 0})
        result, lowered, checked = self.run_apply(fake, procs, {2, 3, 6}, {4, 5})
        self.assertEqual([fake.score(p) for p in (2, 3, 4, 5, 6)], [100, 100, 800, 999, 0])
        self.assertEqual(lowered, {'2:100': 200, '3:100': 800})
        # Never below the unprivileged floor: no write is ever refused.
        self.run_apply(fake, procs, {2, 3, 6}, {4, 5}, lowered, checked)
        self.assertEqual(fake.refused, 0)
        self.assertEqual(result['failures'], [])

    def test_batch_jobs_rank_above_tools(self):
        procs = {pid: P(pid, 1, f'p{pid}') for pid in (2, 3)}
        fake = FakeProc({2: 200, 3: 200})
        with patch.object(policy, '_write_adj', fake.write):
            policy.apply(procs, set(), {3}, {}, set(), fake.root, batch={2})
        self.assertEqual([fake.score(2), fake.score(3)], [policy.BATCH_ADJ, policy.DISPOSABLE_ADJ])

    def test_reused_pid_is_never_written(self):
        procs = {7: P(7, 1, 'p7', start='100'), 8: P(8, 1, 'p8', start='100')}
        fake = FakeProc({7: 200, 8: 200}, starts={7: '555', 8: '555'})
        self.run_apply(fake, procs, {7}, {8})
        self.assertEqual([fake.score(7), fake.score(8)], [200, 200])

    def test_child_of_a_lowered_shell_gets_the_shells_old_score_back(self):
        procs = {20: P(20, 1, 'zsh'), 21: P(21, 20, 'cargo'), 22: P(22, 20, 'ssh'),
                 23: P(23, 21, 'rustc')}
        fake = FakeProc({20: 100, 21: 100, 22: 0, 23: 100})
        self.run_apply(fake, procs, {20}, set(), lowered={'20:100': 200})
        self.assertEqual([fake.score(p) for p in (20, 21, 22, 23)], [100, 200, 0, 200])

    def test_a_process_no_longer_protected_returns_to_its_old_score(self):
        procs = {30: P(30, 1, 'zsh')}
        fake = FakeProc({30: 100})
        result, lowered, _ = self.run_apply(fake, procs, set(), set(), lowered={'30:100': 200, '99:1': 200})
        self.assertEqual(fake.score(30), 200)
        self.assertEqual(lowered, {})
        self.assertEqual(result['restored'], [[30, 'zsh', 200]])


class ScanTests(unittest.TestCase):
    def make(self, root, pid, comm, args, start='100'):
        base = root / str(pid)
        base.mkdir(exist_ok=True)
        (base / 'stat').write_text(f'{pid} ({comm}) ' + ' '.join(['S', '1', '0', '0', '34816'] + ['0'] * 14 + [start]))
        (base / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in args) + b'\0')
        (base / 'cgroup').write_text('0::' + SCOPE + '\n')
        if not (base / 'exe').is_symlink():
            (base / 'exe').symlink_to('/usr/bin/omp (deleted)')

    def test_reads_comm_with_spaces_and_rereads_after_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make(root, 5, 'omp daemon brok', ['/x/omp', '__omp_worker_daemon_broker'])
            cache = {}
            p = policy.scan(root, cache)[5]
            self.assertEqual((p.comm, p.exe, p.ppid, p.tty, p.cgroup), ('omp daemon brok', 'omp', 1, 34816, SCOPE))
            self.make(root, 5, 'hermes', [*HERMES, '--tui'])   # same pid and start: an exec
            self.assertEqual(policy.scan(root, cache)[5].args[-1], '--tui')
            self.assertEqual(policy.scan(root, {}, uid=os.getuid() + 1), {})

    def test_settled_processes_are_reused_without_reading_proc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make(root, 5, 'hermes', [*HERMES, '--tui'])
            self.make(root, 6, 'bash', ['bash'])
            settled = P(5, 1, 'hermes', HERMES, 'python3.14', SCOPE)
            procs = policy.scan(root, {}, reuse={5: settled, 99: P(99, 1, 'gone')})
            self.assertIs(procs[5], settled)
            self.assertEqual(procs[6].comm, 'bash')
            self.assertNotIn(99, procs)   # vanished from /proc: dropped, never reused
            foreign = set()
            self.assertEqual(policy.scan(root, {}, uid=os.getuid() + 1, foreign=foreign), {})
            self.assertEqual(foreign, {5, 6})
            os.unlink(root / '6' / 'stat')  # a partial pass must not even read a foreign PID
            self.assertEqual(policy.scan(root, {}, reuse={}, foreign=foreign), {})


if __name__ == '__main__':
    unittest.main()
