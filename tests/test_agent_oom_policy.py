import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
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
        self.assertEqual(protected, {10, 11, 12, 20, 21, 22, 23, 30, 40, 41, 42, 50, 51, 52})
        # Tools, MCP servers and one-shot subagents remain disposable.
        self.assertEqual(disposable, {24, 25, 26, 27, 31, 32, 33, 53})

    def test_root_daemon_broker_is_protected_without_protecting_its_tools(self):
        procs = session_tree()
        procs[43] = P(43, 42, 'python3', ['python3', 'tool.py'], 'python3', procs[42].cgroup)
        protected, disposable, _ = policy.decide(procs, MAINS)
        self.assertIn(42, protected)
        self.assertIn(43, disposable)
        self.assertNotIn(43, protected)
        self.assertIn(33, disposable)

    def test_broker_protection_requires_real_binary_selector_and_root_parent(self):
        variants = [
            P(42, 40, 'omp daemon brok', ['/x/omp', '__omp_worker_daemon_broker'], 'bash'),
            P(42, 40, 'omp daemon brok', ['/x/other', '__omp_worker_daemon_broker'], 'omp'),
            P(42, 40, 'omp daemon brok', ['/x/omp', 'other', '__omp_worker_daemon_broker'], 'omp'),
            P(42, 24, 'omp daemon brok', ['/x/omp', '__omp_worker_daemon_broker'], 'omp'),
            P(42, 26, 'omp daemon brok', ['/x/omp', '__omp_worker_daemon_broker'], 'omp'),
            P(42, 44, 'omp daemon brok', ['/x/omp', '__omp_worker_daemon_broker'], 'omp'),
        ]
        for broker in variants:
            with self.subTest(parent=broker.ppid, executable=broker.exe, arguments=broker.args):
                procs = session_tree()
                procs[44] = P(44, 40, 'omp', ['/x/omp', '--print', 'bounded review'], 'omp')
                procs[42] = broker
                protected, disposable, _ = policy.decide(procs, MAINS)
                self.assertNotIn(42, protected)
                self.assertIn(42, disposable)

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


class AgentToolingTests(unittest.TestCase):
    """2026-11-05 19:1x: earlyoom kills the highest oom_score first. At adj 800 it took
    3 MiB observer shells, kubectl and bot-to-bot DM delivery (642 SIGKILLs that day)
    while freeing nothing. Agent tooling stays at the floor with the chain above it."""
    def tree(self):
        procs = session_tree()
        run = USER + '/app.slice/run-p1.scope'
        procs[60] = P(60, 1, 'zsh', ['/usr/bin/zsh', '-lic', 'set +m; fleet-kueue --attach fleet-mbp-1 --wait -1 > o'],
                      'zsh', run)
        procs[61] = P(61, 60, 'python3', ['/usr/bin/python3', '/h/.local/bin/fleet-kueue', '--attach', 'j'],
                      'python3.14', run)
        procs[62] = P(62, 61, 'kubectl', ['kubectl', '--kubeconfig', 'k', 'get', 'job'], 'kubectl', run)
        procs[63] = P(63, 60, 'sleep', ['sleep', '60'], 'sleep', run)
        procs[64] = P(64, 31, 'python3', ['/x/python3', '/h/hermes-agent/tools/bot_mode_dm.py', '--run-delivery'],
                      'python3.14', GATEWAY)
        procs[65] = P(65, 31, 'bash', ['bash', '-c', 'timeout 3200 fleet-build --node mbp-host -- bash x.sh'],
                      'bash', GATEWAY)
        return procs

    def test_observers_kubectl_and_dm_delivery_are_protected(self):
        protected, disposable, _ = policy.decide(self.tree(), {**MAINS, 'run-p1.scope': 60})
        for pid in (60, 61, 62, 64, 65):
            self.assertIn(pid, protected, pid)
            self.assertNotIn(pid, disposable, pid)
        self.assertIn(31, protected)           # the shell above a spared tool stays too

    def test_ordinary_tools_stay_disposable(self):
        protected, disposable, _ = policy.decide(self.tree(), {**MAINS, 'run-p1.scope': 60})
        for pid in (24, 25, 26, 27, 32, 33, 53):
            self.assertIn(pid, disposable, pid)
        self.assertNotIn(63, protected)        # a spared shell's sleep child is not protected

    def test_word_match_only(self):
        procs = self.tree()
        procs[66] = P(66, 24, 'python3', ['python3', 'fleetingly.py', 'kubectlx'], 'python3.14', SCOPE)
        protected, disposable, _ = policy.decide(procs, MAINS)
        self.assertIn(66, disposable)


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

    def test_root_broker_recovers_floor_while_its_tool_remains_killable(self):
        tree = session_tree()
        procs = {
            40: tree[40]._replace(ppid=1),
            42: tree[42],
            43: P(43, 42, 'python3', ['python3', 'tool.py'], 'python3', tree[42].cgroup),
        }
        protected, disposable, _ = policy.decide(procs)
        fake = FakeProc({40: 100, 42: 800, 43: 100})
        self.addCleanup(fake.tmp.cleanup)
        self.run_apply(fake, procs, protected, disposable)
        self.assertEqual([fake.score(pid) for pid in (40, 42, 43)], [100, 100, 800])

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


class ReliefTests(unittest.TestCase):
    def pressure(self, free=16640, blocks=0):
        # MemAvailable can be 4 GiB and is intentionally absent from this decision.
        return policy.zone_pressure(
            f'Node 0, zone Normal\n  pages free {free}\n high 1024\n',
            f'Node 0, zone Normal 1 2 3 {blocks} 0 0 0 0 0 0 0\n')

    def test_fragmented_normal_zone_ignores_apparently_available_cache(self):
        self.assertTrue(self.pressure()['threatened'])
        self.assertFalse(self.pressure(free=100000)['threatened'])
        self.assertFalse(self.pressure(blocks=1000)['threatened'])
        self.assertFalse(policy.zone_pressure('', '')['available'])

    def test_desktop_core_survives_without_a_harness_descendant(self):
        procs = {1: P(1, 0, 'systemd'), 2: P(2, 1, 'Hyprland', ['Hyprland'], 'Hyprland'),
                 3: P(3, 2, 'qs', ['qs'], 'qs')}
        protected, disposable, batch = policy.decide(procs)
        self.assertEqual(protected, {2, 3})
        self.assertFalse(disposable | batch)

    def test_only_known_substantial_tools_and_batch_are_candidates(self):
        procs = session_tree()
        procs[80] = P(80, 1, 'python3', ['python3', 'unknown.py'], 'python3', SCOPE)
        protected, tools, jobs = policy.decide(procs, MAINS)
        with patch.object(policy, 'reclaim_kb', return_value=policy.MIN_RECLAIM_KB):
            candidate = policy.relief_candidate(procs, protected, tools, jobs)
            self.assertIn(candidate.pid, tools - {80})
            self.assertIsNone(policy.relief_candidate(procs, protected, {80}, set()))
            self.assertIsNone(policy.relief_candidate(procs, protected, protected, set()))
        with patch.object(policy, 'reclaim_kb', return_value=policy.MIN_RECLAIM_KB - 1):
            self.assertIsNone(policy.relief_candidate(procs, protected, tools, jobs))

    def test_safe_pressure_and_dry_run_never_signal_or_mutate_cooldown(self):
        procs = session_tree()
        protected, tools, jobs = policy.decide(procs, MAINS)
        relief = policy.Relief()
        with patch.object(policy, 'reclaim_kb', return_value=policy.MIN_RECLAIM_KB), \
                patch.object(policy.os, 'pidfd_open') as opened, \
                patch.object(policy.signal, 'pidfd_send_signal') as sent:
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(free=100000), 0)['action'], 'none')
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(), 0, dry_run=True)['action'], 'would-term')
            opened.assert_not_called()
            sent.assert_not_called()
            self.assertIsNone(relief.pending)
            self.assertEqual(relief.last, float('-inf'))

    def test_pid_reuse_between_pin_and_signal_fails_closed(self):
        procs = session_tree()
        protected, tools, jobs = policy.decide(procs, MAINS)
        relief = policy.Relief()
        p = procs[25]
        changed = dict(procs)
        changed[25] = p._replace(start='999')
        with patch.object(policy, 'REPORT_ONLY', False), \
                patch.object(policy, 'relief_candidate', return_value=p), \
                patch.object(policy.os, 'pidfd_open', return_value=123), \
                patch.object(policy.os, 'close') as closed, \
                patch.object(policy, 'scan', return_value=changed), \
                patch.object(policy.signal, 'pidfd_send_signal') as sent:
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(), 0)['action'], 'changed')
            sent.assert_not_called()
            closed.assert_called_once_with(123)

    def test_term_grace_kill_and_cooldown_are_bounded_to_one_process(self):
        procs = session_tree()
        protected, tools, jobs = policy.decide(procs, MAINS)
        relief = policy.Relief()
        p = procs[25]
        with patch.object(policy, 'REPORT_ONLY', False), \
                patch.object(policy, 'relief_candidate', return_value=p), \
                patch.object(policy.os, 'pidfd_open', return_value=123), \
                patch.object(policy.os, 'close'), \
                patch.object(policy, '_same', return_value=True), \
                patch.object(policy, 'scan', return_value=procs), \
                patch.object(policy.signal, 'pidfd_send_signal') as sent:
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(), 0)['action'], 'term')
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(), 1)['action'], 'waiting')
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(), 2)['action'], 'kill')
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                        self.pressure(), 3)['action'], 'cooldown')
            self.assertEqual(sent.call_args_list[0].args, (123, policy.signal.SIGTERM))
            self.assertEqual(sent.call_args_list[1].args, (123, policy.signal.SIGKILL))
            self.assertEqual(sent.call_count, 2)

    def test_dead_reused_or_newly_protected_pending_process_is_released(self):
        procs = session_tree()
        p = procs[25]
        for same, protected in ((False, set()), (True, {25})):
            relief = policy.Relief()
            relief.pending = (p, 123, 2)
            with patch.object(policy, '_same', return_value=same), \
                    patch.object(policy.os, 'close') as closed, \
                    patch.object(policy.signal, 'pidfd_send_signal') as sent:
                self.assertEqual(relief.step(procs, protected, {25}, set(),
                                            self.pressure(), 3)['action'], 'released')
                sent.assert_not_called()
                closed.assert_called_once_with(123)
                self.assertIsNone(relief.pending)


    def test_escalation_stops_if_pressure_clears_or_victim_shrinks(self):
        procs = session_tree()
        protected, tools, jobs = policy.decide(procs, MAINS)
        p = procs[25]
        for threatened, candidate in ((False, p), (True, None)):
            relief = policy.Relief()
            relief.pending = (p, 123, 2)
            with patch.object(policy, '_same', return_value=True), \
                    patch.object(policy, 'scan', return_value=procs), \
                    patch.object(policy, 'relief_candidate', return_value=candidate), \
                    patch.object(policy.os, 'close'), \
                    patch.object(policy.signal, 'pidfd_send_signal') as sent:
                result = relief.step(procs, protected, tools, jobs,
                                     {'threatened': threatened}, 3)
                self.assertEqual(result['action'], 'released')
                sent.assert_not_called()


class ReportOnlyTests(unittest.TestCase):
    """Kevin 2026-11-06: 'keep earlyoom as the one killer'.

    The guard still scores the kernel OOM order and reports a hazard, but it
    must not signal a process itself and must not re-report the same victim
    every tick (that is the 16k-lines/day spam this replaces).
    """

    def pressure(self):
        return policy.zone_pressure(
            'Node 0, zone Normal\n  pages free 16640\n high 1024\n',
            'Node 0, zone Normal 1 2 3 0 0 0 0 0 0 0 0\n')

    def test_report_only_reports_once_per_cooldown_and_never_signals(self):
        self.assertTrue(policy.REPORT_ONLY, 'deployed default must be report-only')
        procs = session_tree()
        protected, tools, jobs = policy.decide(procs, MAINS)
        relief = policy.Relief()
        with patch.object(policy, 'reclaim_kb', return_value=policy.MIN_RECLAIM_KB), \
                patch.object(policy.os, 'pidfd_open') as opened, \
                patch.object(policy.os, 'close') as closed, \
                patch.object(policy.signal, 'pidfd_send_signal') as sent:
            first = relief.step(procs, protected, tools, jobs, self.pressure(), 0)
            second = relief.step(procs, protected, tools, jobs, self.pressure(), 1)
        self.assertEqual(first['action'], 'report-only-term')
        self.assertIn(first['pid'], tools, 'the victim is a known disposable tool')
        self.assertNotIn(first['pid'], protected)
        self.assertIn('reclaim_kb', first)
        self.assertEqual(second['action'], 'cooldown')
        opened.assert_not_called()
        sent.assert_not_called()
        closed.assert_not_called()
        self.assertIsNone(relief.pending, 'nothing is pinned, so nothing to release')

    def test_report_only_is_one_switch_back_to_enforcement(self):
        procs = session_tree()
        protected, tools, jobs = policy.decide(procs, MAINS)
        relief = policy.Relief()
        p = procs[25]
        with patch.object(policy, 'REPORT_ONLY', False), \
                patch.object(policy, 'relief_candidate', return_value=p), \
                patch.object(policy.os, 'pidfd_open', return_value=123), \
                patch.object(policy.os, 'close'), \
                patch.object(policy, '_same', return_value=True), \
                patch.object(policy, 'scan', return_value=procs), \
                patch.object(policy.signal, 'pidfd_send_signal') as sent:
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                         self.pressure(), 0)['action'], 'term')
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                         self.pressure(), 1)['action'], 'waiting')
            self.assertEqual(relief.step(procs, protected, tools, jobs,
                                         self.pressure(), 2)['action'], 'kill')
        self.assertEqual(sent.call_args_list[0].args, (123, policy.signal.SIGTERM))
        self.assertEqual(sent.call_args_list[1].args, (123, policy.signal.SIGKILL))

    def test_report_only_never_starts_a_cache_reclaim_thread(self):
        relief = policy.CacheRelief()
        with patch.object(relief, 'target', return_value=Path('/owned/memory.reclaim')), \
                patch.object(policy.threading, 'Thread') as thread:
            self.assertEqual(relief.step(0)['action'], 'would-reclaim-cache')
            thread.assert_not_called()
            self.assertEqual(relief.last, float('-inf'))


class CacheReliefTests(unittest.TestCase):
    def test_only_owned_user_session_leaf_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            (proc / 'self').mkdir()
            (proc / 'self/cgroup').write_text(f'0::{USER}/agent.slice/guard.service\n')
            self.assertEqual(policy.CacheRelief.target(proc, Path('/cgroups')),
                             Path('/cgroups') / USER.lstrip('/') / 'session.slice/memory.reclaim')
            (proc / 'self/cgroup').write_text('0::/system.slice/unknown.service\n')
            with self.assertRaises(OSError):
                policy.CacheRelief.target(proc)

    def test_file_only_request_and_permission_failure_are_observable(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'memory.reclaim'
            target.touch()
            relief = policy.CacheRelief()
            relief._run(target)
            self.assertEqual(target.read_text(), '268435456 swappiness=0\n')
            self.assertEqual(relief.result['action'], 'cache-reclaim-requested')
            relief._run(Path(tmp) / 'missing')
            self.assertEqual(relief.result['action'], 'cache-reclaim-unavailable')

    def test_dry_run_and_single_inflight_reclaim_are_bounded(self):
        relief = policy.CacheRelief()
        with patch.object(policy, 'REPORT_ONLY', False), \
                patch.object(relief, 'target', return_value=Path('/owned/memory.reclaim')), \
                patch.object(policy.threading, 'Thread') as thread:
            self.assertEqual(relief.step(0, dry_run=True)['action'], 'would-reclaim-cache')
            thread.assert_not_called()
            self.assertEqual(relief.last, float('-inf'))
            self.assertEqual(relief.step(0)['action'], 'cache-reclaim-started')
            thread.return_value.is_alive.return_value = True
            self.assertEqual(relief.step(1)['action'], 'cache-reclaim-pending')
            self.assertEqual(thread.call_count, 1)
            thread.return_value.is_alive.return_value = False
            relief.result = {'action': 'cache-reclaim-unavailable'}
            self.assertEqual(relief.step(2)['action'], 'cache-reclaim-unavailable')
            self.assertEqual(relief.step(3)['action'], 'cache-reclaim-cooldown')


class GuardLoopTests(unittest.TestCase):
    def test_urgent_tick_never_waits_for_service_or_journal_helpers(self):
        loader = importlib.machinery.SourceFileLoader('agent_oom_guard', str(ROOT / 'scripts/agent-oom-guard'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        guard = importlib.util.module_from_spec(spec)
        loader.exec_module(guard)
        state = {'cache': {}, 'checked': set(), 'mains': {'known.service': 1},
                 'refreshed': float('-inf'), 'full': float('-inf'), 'procs': {},
                 'first_seen': {}, 'foreign': set(), 'lowered': {}, 'history': {}}
        safe = {'threatened': False, 'available': True, 'zones': []}
        with patch.object(guard, 'unit_mains', side_effect=AssertionError('blocking discovery')), \
                patch.object(guard, 'record_kills', side_effect=AssertionError('blocking journal')), \
                patch.object(guard.policy, 'scan', return_value={}), \
                patch.object(guard.policy, 'read_pressure', return_value=safe):
            result = guard.tick(state, dry_run=True)
        self.assertEqual(result['relief']['action'], 'none')
        self.assertEqual(result['pressure'], safe)

    def test_prior_protection_waits_for_service_discovery_before_restoration(self):
        loader = importlib.machinery.SourceFileLoader('agent_oom_guard_startup', str(ROOT / 'scripts/agent-oom-guard'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        guard = importlib.util.module_from_spec(spec)
        loader.exec_module(guard)
        procs = {77: P(77, 1, 'python3', ['python3', 'service.py'], 'python3')}
        fake = FakeProc({77: 100})
        self.addCleanup(fake.tmp.cleanup)
        state = {'cache': {}, 'checked': set(), 'mains': {},
                 'refreshed': float('-inf'), 'full': float('-inf'), 'procs': {},
                 'first_seen': {}, 'foreign': set(), 'lowered': {'77:100': 200}, 'history': {}}
        safe = {'threatened': False, 'available': True, 'zones': []}
        real_apply = guard.policy.apply

        def apply_to_fixture(*args, **kwargs):
            return real_apply(*args, proc=fake.root, **kwargs)

        with patch.object(guard.policy, 'scan', return_value=procs), \
                patch.object(guard.policy, 'read_pressure', return_value=safe), \
                patch.object(guard.policy, 'apply', side_effect=apply_to_fixture), \
                patch.object(guard.policy, '_write_adj', fake.write), \
                patch.object(guard, 'save'):
            result = guard.tick(state)
            self.assertEqual(result['restored'], [])
            self.assertEqual(fake.score(77), 100)
            state['mains'] = {'unrelated.service': 1}
            result = guard.tick(state)
            self.assertEqual(result['restored'], [[77, 'python3', 200]])
            self.assertEqual(fake.score(77), 200)

    def test_protected_kill_is_reported_once_per_summary(self):
        """One protected kill was re-logged ~692x/day; a byte cursor ends that."""
        loader = importlib.machinery.SourceFileLoader('agent_oom_guard_kills',
                                                     str(ROOT / 'scripts/agent-oom-guard'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        guard = importlib.util.module_from_spec(spec)
        loader.exec_module(guard)
        row = json.dumps({'ts': 1.0, 'class': 'protected', 'pid': 42,
                          'comm': 'hermes-gateway'})
        quiet = SimpleNamespace(stdout='', returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / 'kills.jsonl').write_text(row + '\n')
            state = {'cache': {}, 'mains': {'known.service': 1}}
            with patch.object(guard, 'STATE', state_dir), \
                    patch.object(guard.subprocess, 'run', return_value=quiet), \
                    patch.object(guard.policy, 'read_pressure',
                                 return_value={'available': True, 'threatened': False,
                                               'zones': []}):
                first = guard.check(state)
                again = guard.check(state)
                third = guard.check(state)
            self.assertEqual([p for p in first
                              if p.startswith('protected process was OOM-killed')],
                             [f'protected process was OOM-killed: {json.loads(row)}'])
            self.assertEqual([p for p in again + third
                              if p.startswith('protected process was OOM-killed')], [])
            self.assertEqual((state_dir / 'kills-reported.offset').read_text(),
                             str(len(row) + 1))


if __name__ == '__main__':
    unittest.main()
