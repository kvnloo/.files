"""Kernel OOM kill order for coding agents: disposable work first, never a harness root.

Owner rule (2026-10-25): "it can kill subagents just never the root process".

ROOT        A harness process (hermes, omp, claude, codex, pi, opencode) that is not a
            one-shot worker and either has no harness above it or owns a terminal of its
            own (an interactive session another agent opened); the main process of a
            *hermes* user service (gateway, dashboard, embedded agent hosts); Tern's
            daemon, GUI and remote server, which host every pane.
PROTECTED   Roots; an OMP root's direct daemon broker; a Hermes root's TUI renderer
            (node .../entry.js) and that renderer's direct children (the tui_gateway
            agent backend); every process above them up to the user manager (a pane
            shell's exit SIGHUPs the session); and the main process of every unit
            holding one of them (its exit makes systemd stop the unit).
DISPOSABLE  Everything else under a harness -- tools, MCP servers, language servers,
            subagent harnesses and their trees -- and anything else left in
            agent.slice. Desktop programs (browsers, terminals) keep their score.
BATCH       Processes of background maintenance units (BATCH_UNIT). They are killed
            before interactive tools: tonight's hogs (ctx import, agentsview sync) sat
            at 200 while every tool at 800 had to die before them.

Scores bias the kernel; they do not guarantee survival during global OOM, zone
exhaustion, or cgroup limits. Proactive relief below targets only known tools and
batch work. FLOOR_ADJ 100 is the inherited unprivileged floor on groot; failed
lowering is reported, not silently treated as protection.

Scores only move one way: protected processes are lowered, the others raised. A child
forked by a lowered shell inherits the low score; it gets back the score its parent
had before (see hand_back).
"""
from __future__ import annotations

import os
from pathlib import Path, PurePath
import signal
import re
import threading
from typing import NamedTuple

# Kevin 2026-11-06: "keep earlyoom as the one killer".  The guard no longer
# terminates processes or reclaims caches itself; it only scores the kernel OOM
# order (so earlyoom drops disposable work before a root) and reports hazards.
# Rollback: set REPORT_ONLY = False.
REPORT_ONLY = True

FLOOR_ADJ = 100
DISPOSABLE_ADJ = 800
BATCH_ADJ = 900
BATCH_UNIT = re.compile(r'^(agentsview-sync|ctx-import|worktree-reaper|artifact-leases|z0-state-packet'
                        r'|dev\.cribble\.agent\.sync|agent-telemetry-refresh'
                        r'|z0int-(policy|loop-tick|choice-[0-9a-f]+))\.service$')
HARNESSES = frozenset({'hermes', 'claude', 'omp', 'codex', 'pi', 'opencode'})
# Services that host agent sessions under a generic interpreter name (the gateway,
# dashboard, garden-room and z0live hosts): their unit's main process is a root.
ROOT_UNIT = re.compile(r'(^|[-_@.])hermes([-_@.]|$)')
# Never given a disposable score even when an agent started them.
DESKTOP = frozenset({'Hyprland', 'sway', 'kwin_wayland', 'gnome-shell', 'systemd', 'dbus-broker',
                     'chromium', 'chrome', 'firefox', 'brave', 'brave-browser', 'zen', 'zen-bin',
                     'librewolf', 'pipewire', 'pipewire-pulse', 'wireplumber', 'pulseaudio',
                     'Xwayland', 'hypridle', 'qs', 'Discord', 'tern',
                     'kitty', 'alacritty', 'wezterm-gui', 'foot', 'gnome-terminal-', 'konsole'})
# Desktop infrastructure stays protected even when no harness pane survives.
# Browsers and ordinary desktop applications remain excluded from relief, but
# do not gain infrastructure protection.
# Agent tooling: observers of remote jobs, cluster clients and bot-to-bot DM delivery.
# They hold a few MiB, so killing them frees nothing, but earlyoom kills the highest
# oom_score first and at adj 800 they went before every real hog (2026-11-05: 642
# SIGKILLs, including fleet observers and DM delivery). They stay at the floor.
TOOLING = re.compile(r'(?:^|[\s/;|&(\'"])(?:kubectl|fleet|fleet-build|fleet-kueue|bot_mode_dm\.py)(?=$|[\s;|&)\'"])')
DESKTOP_CORE = frozenset({'Hyprland', 'sway', 'kwin_wayland', 'gnome-shell',
                          'pipewire', 'pipewire-pulse', 'wireplumber', 'pulseaudio',
                          'Xwayland', 'hypridle', 'qs', 'tern', 'dbus-broker'})


class Proc(NamedTuple):
    pid: int
    ppid: int
    comm: str
    exe: str      # basename of /proc/PID/exe, '' when unreadable
    args: tuple
    cgroup: str   # cgroup v2 path, e.g. /user.slice/.../agent.slice/x.scope
    start: str    # starttime: tells a reused PID from the process seen before
    tty: int


def _static(base: Path, uid: int):
    try:
        if base.stat().st_uid != uid:
            return False
        args = tuple(a.decode(errors='replace')
                     for a in (base / 'cmdline').read_bytes().split(b'\0') if a)
        try:
            exe = PurePath(os.readlink(base / 'exe')).name.removesuffix(' (deleted)')
        except OSError:
            exe = ''
        cgroup = (base / 'cgroup').read_text().strip().split('::', 1)[-1]
        return exe, args, cgroup
    except OSError:
        return False


def scan(proc: Path = Path('/proc'), cache: dict | None = None, uid: int | None = None,
         reuse: dict | None = None, foreign: set | None = None) -> dict:
    """This user's processes. `cache` keeps cmdline/exe/cgroup per (pid, start, comm):
    exec keeps pid and start time but changes comm, so a re-exec is read again.
    `reuse`: settled processes from the previous pass, kept without re-reading /proc;
    apply() re-checks start time before every write, so a reused PID is never written.
    `foreign`: PIDs found to belong to other users (root, kernel threads -- most of
    /proc); filled on every pass and skipped on partial passes (reuse given)."""
    uid = os.getuid() if uid is None else uid
    cache = {} if cache is None else cache
    out = {}
    root = str(proc)
    try:
        names = os.listdir(root)
    except OSError:
        return out
    # Runs every second over ~1000 processes: raw os calls, no pathlib, in this loop.
    for name in names:
        if not name.isdigit():
            continue
        if reuse is not None:
            if int(name) in reuse:
                out[int(name)] = reuse[int(name)]
                continue
            if foreign is not None and int(name) in foreign:
                continue
        try:
            fd = os.open(f'{root}/{name}/stat', os.O_RDONLY)
            try:
                stat = os.read(fd, 4096).decode(errors='replace')
            finally:
                os.close(fd)
            close = stat.rindex(')')
            comm = stat[stat.index('(') + 1:close]
            fields = stat[close + 2:].split(None, 20)
            ppid, tty, start = int(fields[1]), int(fields[4]), fields[19]
        except (OSError, ValueError, IndexError):
            continue
        key = (int(name), start, comm)
        static = cache.get(key)
        if static is None:
            static = cache[key] = _static(proc / name, uid)
        if static is False:
            if foreign is not None:
                foreign.add(int(name))
            continue
        exe, args, cgroup = static
        out[int(name)] = Proc(int(name), ppid, comm, exe, args, cgroup, start, tty)
    return out


def _entry(p: Proc) -> str:
    return PurePath(p.args[0]).name if p.args else ''


def harness(p: Proc) -> bool:
    """comm alone is not identity: a renamed process must not become a protected root."""
    name = p.comm
    if name not in HARNESSES:
        return False
    if name in (p.exe, _entry(p)):
        return True
    if name == 'hermes':
        return (any('from hermes_cli.main import main' in a or a == 'hermes_cli.main' for a in p.args)
                or (len(p.args) > 1 and PurePath(p.args[1]).name == 'hermes'))
    if name == 'claude':
        return any('@anthropic-ai/claude-code/' in a for a in p.args)
    if name in {'omp', 'pi'}:
        return any('/pi-coding-agent/' in a or '/oh-my-pi/' in a for a in p.args)
    return False


def worker(p: Proc) -> bool:
    """One-shot invocations are subagents wherever they were started from."""
    args = set(p.args[1:])
    if p.comm == 'hermes':
        return bool(args & {'--oneshot', '--query', '--query-file'}) or {'chat', '-q'} <= args
    if p.comm in {'claude', 'omp', 'pi'}:
        return bool(args & {'-p', '--print'})
    if p.comm == 'codex':
        return 'exec' in p.args[1:3]
    if p.comm == 'opencode':
        return 'run' in p.args[1:3]
    return False


def tern_host(p: Proc) -> bool:
    if p.comm != 'tern' or 'tern' not in (p.exe, _entry(p)):
        return False
    return len(p.args) < 2 or p.args[1] in {'daemon', 'remote'}


def frontend(p: Proc) -> bool:
    return ((p.exe.startswith('node') or p.comm.startswith('node'))
            and any(PurePath(a).name == 'entry.js' for a in p.args[1:4]))


def unit_of(cgroup: str) -> str:
    for part in reversed(PurePath(cgroup).parts):
        if part.endswith(('.service', '.scope')):
            return part
    return ''


def decide(procs: dict, unit_mains: dict | None = None) -> tuple[set, set, set]:
    """(protected, disposable, batch) PIDs for one snapshot."""
    unit_mains = unit_mains or {}
    managers = {pid for pid, p in procs.items() if p.comm == 'systemd'}

    def above(pid):
        chain, p = [], procs.get(pid)
        while p is not None and p.ppid in procs and p.ppid not in managers \
                and p.ppid not in chain and len(chain) < 64:
            chain.append(p.ppid)
            p = procs[p.ppid]
        return chain

    harnesses = {pid for pid, p in procs.items() if harness(p)}
    hosts = {main for unit, main in unit_mains.items()
             if ROOT_UNIT.search(unit) and main in procs and main not in managers}
    roots = hosts | {pid for pid, p in procs.items() if tern_host(p)}
    for pid in harnesses:
        p = procs[pid]
        if worker(p):
            continue
        parents = [a for a in above(pid) if a in harnesses]
        if not parents or (p.tty and p.tty != procs[parents[0]].tty):
            roots.add(pid)
    children = {}
    for pid, p in procs.items():
        children.setdefault(p.ppid, []).append(pid)
    front = {pid for pid, p in procs.items()
             if p.ppid in roots and procs[p.ppid].comm == 'hermes' and frontend(p)}
    backends = {c for f in front for c in children.get(f, ())}
    desktop = {pid for pid, p in procs.items()
               if p.comm in DESKTOP_CORE and p.comm in (p.exe, _entry(p))}
    # This broker owns daemon lifetime and completion RPCs, not just language servers.
    # Protect only its root-owned process; managed tools still remain disposable.
    brokers = {pid for pid, p in procs.items()
               if p.ppid in roots and procs[p.ppid].comm == 'omp'
               and p.exe == 'omp' and _entry(p) == 'omp'
               and p.args[1:2] == ('__omp_worker_daemon_broker',)}
    tooling = {pid for pid, p in procs.items() if pid not in managers
               and any(TOOLING.search(arg) for arg in p.args)}
    protected = roots | front | backends | desktop | brokers | tooling
    for pid in list(protected):
        protected.update(above(pid))
    for pid in list(protected):
        main = unit_mains.get(unit_of(procs[pid].cgroup))
        if main in procs and main not in managers:
            protected.add(main)
            protected.update(above(main))
    tree, stack = harnesses | hosts, list(harnesses | hosts)
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in tree:
                tree.add(child)
                stack.append(child)
    in_slice = {pid for pid, p in procs.items() if '/agent.slice/' in p.cgroup}
    disposable = {pid for pid in (tree | in_slice) - protected
                  if procs[pid].comm not in DESKTOP and pid not in managers}
    batch = {pid for pid, p in procs.items()
             if BATCH_UNIT.match(unit_of(p.cgroup)) and pid not in protected and pid not in managers}
    return protected, disposable - batch, batch


def _read_adj(proc: Path, pid: int) -> int:
    return int((proc / str(pid) / 'oom_score_adj').read_text())


def _write_adj(proc: Path, pid: int, value: int) -> None:
    fd = os.open(proc / str(pid) / 'oom_score_adj', os.O_WRONLY)
    try:
        os.write(fd, str(value).encode())
    finally:
        os.close(fd)


def _same(proc: Path, p: Proc) -> bool:
    """Write only to the process that was classified, not a PID reused since."""
    try:
        stat = (proc / str(p.pid) / 'stat').read_text()
        return stat[stat.rindex(')') + 2:].split()[19] == p.start
    except (OSError, IndexError):
        return False


def apply(procs: dict, protected: set, disposable: set, lowered: dict, checked: set,
          proc: Path = Path('/proc'), dry_run: bool = False, batch: set = frozenset()) -> dict:
    """Lower protected, raise disposable and batch, hand inherited low scores back.

    lowered: {'pid:start': score before lowering}; the caller persists it.
    checked: (pid, start) already examined as disposable/inheritor; scores only change
    at fork or by an explicit write, so each such process is examined once.
    """
    result = {'protected': sorted(protected), 'lowered': [], 'restored': [], 'raised': [],
              'handed_back': [], 'failures': []}
    live = {f'{p.pid}:{p.start}': p for p in procs.values()}
    for key in [k for k in lowered if k not in live]:
        del lowered[key]
    # No longer protected (its session ended): back to the score it had before.
    for key, p in live.items():
        if key in lowered and p.pid not in protected:
            try:
                if _same(proc, p) and _read_adj(proc, p.pid) < lowered[key]:
                    if not dry_run:
                        _write_adj(proc, p.pid, lowered[key])
                    result['restored'].append([p.pid, p.comm, lowered[key]])
                del lowered[key]
            except (OSError, ValueError):
                continue
    for pid in sorted(protected):
        p = procs[pid]
        try:
            current = _read_adj(proc, pid)
            if current <= FLOOR_ADJ or not _same(proc, p):
                continue
            if not dry_run:
                _write_adj(proc, pid, FLOOR_ADJ)
            lowered.setdefault(f'{pid}:{p.start}', current)
            result['lowered'].append([pid, p.comm, current, FLOOR_ADJ])
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            result['failures'].append({'pid': pid, 'error': str(error)})
    targets = [(pid, BATCH_ADJ) for pid in sorted(batch)] + [(pid, DISPOSABLE_ADJ) for pid in sorted(disposable)]
    for pid, target in targets:
        p = procs[pid]
        if (pid, p.start) in checked:
            continue
        checked.add((pid, p.start))
        try:
            current = _read_adj(proc, pid)
            if current < target and _same(proc, p):
                if not dry_run:
                    _write_adj(proc, pid, target)
                result['raised'].append([pid, p.comm, current, target])
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            result['failures'].append({'pid': pid, 'error': str(error)})
    result['handed_back'] = hand_back(procs, protected, set(disposable) | set(batch), lowered, checked,
                                      proc, dry_run)
    return result


def hand_back(procs, protected, disposable, lowered, checked, proc, dry_run):
    """A child forked by a lowered shell or compositor inherited the protected score.

    It is not protected itself: give it the score its protected ancestor had before
    lowering. Only an exact inherited value is reset, never a score set otherwise."""
    done = []
    for pid, p in procs.items():
        if pid in protected or pid in disposable or (pid, p.start) in checked:
            continue
        checked.add((pid, p.start))
        ancestor, hops = procs.get(p.ppid), 0
        while ancestor is not None and ancestor.pid not in protected and hops < 64:
            ancestor, hops = procs.get(ancestor.ppid), hops + 1
        if ancestor is None:
            continue
        before = lowered.get(f'{ancestor.pid}:{ancestor.start}')
        if before is None:
            continue
        try:
            current, inherited = _read_adj(proc, pid), _read_adj(proc, ancestor.pid)
            if current == inherited and current < before and _same(proc, p):
                if not dry_run:
                    _write_adj(proc, pid, before)
                done.append([pid, p.comm, current, before])
        except (OSError, ValueError):
            continue
    return done


# The incident had ~4 GiB MemAvailable (mostly cache), ~65 MiB Normal free
# and no order-3 blocks. Reserve 128 MiB / twice the zone high watermark and
# intervene while at most 32 order-3-or-larger blocks remain, not after zero.
MIN_RECLAIM_KB = 256 * 1024
RELIEF_COOLDOWN = 15.0
TERM_GRACE = 2.0


def zone_pressure(zoneinfo: str, buddyinfo: str, page_size: int = 4096) -> dict:
    zones = {}
    current = None
    for line in zoneinfo.splitlines():
        match = re.match(r'Node\s+(\d+), zone\s+(\S+)', line.strip())
        if match:
            current = (int(match[1]), match[2])
            zones[current] = {}
        elif current is not None:
            fields = line.split()
            if fields[:2] == ['pages', 'free'] and len(fields) == 3:
                zones[current]['free'] = int(fields[2])
            elif fields[:1] == ['high'] and len(fields) == 2:
                zones[current]['high'] = int(fields[1])
    observations = []
    for line in buddyinfo.splitlines():
        match = re.match(r'Node\s+(\d+), zone\s+(\S+)\s+(.+)', line.strip())
        if not match or match[2] != 'Normal':
            continue
        zone = zones.get((int(match[1]), match[2]), {})
        orders = [int(v) for v in match[3].split()]
        if 'free' not in zone or 'high' not in zone or len(orders) < 4:
            continue
        reserve = max(2 * zone['high'], 128 * 1024 * 1024 // page_size)
        blocks = sum(orders[3:])
        observations.append({'node': int(match[1]), 'free_pages': zone['free'],
                             'reserve_pages': reserve, 'order3_blocks': blocks,
                             'threatened': zone['free'] <= reserve and blocks <= 32})
    return {'threatened': any(z['threatened'] for z in observations), 'zones': observations,
            'available': bool(observations)}


def read_pressure(proc: Path = Path('/proc')) -> dict:
    try:
        return zone_pressure((proc / 'zoneinfo').read_text(),
                             (proc / 'buddyinfo').read_text(), os.sysconf('SC_PAGE_SIZE'))
    except (OSError, ValueError) as error:
        return {'threatened': False, 'available': False, 'error': str(error), 'zones': []}


def reclaim_kb(proc: Path, p: Proc) -> int:
    """Resident anonymous memory, not shared/file cache or already-swapped bytes."""
    try:
        status = (proc / str(p.pid) / 'status').read_text()
        match = re.search(r'^RssAnon:\s+(\d+)\s+kB$', status, re.M)
        return int(match[1]) if match and _same(proc, p) else 0
    except (OSError, ValueError):
        return 0


def relief_candidate(procs, protected, disposable, batch, proc=Path('/proc'),
                     minimum_kb=MIN_RECLAIM_KB):
    candidates = []
    for pid in (disposable | batch) - protected:
        p = procs[pid]
        if p.comm in DESKTOP or pid == os.getpid():
            continue
        # Merely being in agent.slice is not affirmative evidence of a tool.
        known = pid in batch or (harness(p) and worker(p))
        parent, seen = procs.get(p.ppid), set()
        while not known and parent is not None and parent.pid not in seen:
            seen.add(parent.pid)
            known = harness(parent)
            parent = procs.get(parent.ppid)
        if not known:
            continue
        size = reclaim_kb(proc, p)
        if size >= minimum_kb:
            candidates.append((pid in batch, size, -pid, p))
    return max(candidates)[-1] if candidates else None


class Relief:
    """One pidfd-pinned process at a time; no PID-based signal fallback."""

    def __init__(self):
        self.pending = None
        self.last = float('-inf')

    def step(self, procs, protected, disposable, batch, pressure, now,
             proc=Path('/proc'), dry_run=False, unit_mains=None):
        report_only = REPORT_ONLY
        if self.pending is not None:
            p, fd, deadline = self.pending
            if dry_run:
                return {'action': 'pending', 'pid': p.pid}
            if not _same(proc, p) or p.pid in protected:
                os.close(fd)
                self.pending = None
                return {'action': 'released', 'pid': p.pid}
            if now < deadline:
                return {'action': 'waiting', 'pid': p.pid}
            # Revalidate classification after TERM; an exec may become a root.
            fresh = scan(proc=proc)
            safe, tools, jobs = decide(fresh, unit_mains)
            live = fresh.get(p.pid)
            try:
                if pressure.get('threatened') and live == p and p.pid in tools | jobs \
                        and p.pid not in safe and relief_candidate(
                            fresh, safe, tools & {p.pid}, jobs & {p.pid}, proc) == p:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                    return {'action': 'kill', 'pid': p.pid}
                return {'action': 'released', 'pid': p.pid}
            except OSError as error:
                return {'action': 'gone', 'pid': p.pid, 'error': str(error)}
            finally:
                os.close(fd)
                self.pending = None
        if not pressure.get('threatened'):
            return {'action': 'none'}
        if now - self.last < RELIEF_COOLDOWN:
            return {'action': 'cooldown'}
        p = relief_candidate(procs, protected, disposable, batch, proc)
        if p is None:
            return {'action': 'no-candidate'}
        if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            return {'action': 'unavailable', 'reason': 'pidfd signaling required'}
        if dry_run or report_only:
            action = 'would-term' if dry_run else 'report-only-term'
            if not dry_run:
                # One report per victim per cooldown, not one per tick: the
                # report must not become the log spam it replaced.
                self.last = now
            return {'action': action,
                    'pid': p.pid, 'start': p.start,
                    'reclaim_kb': reclaim_kb(proc, p)}
        fd = None
        try:
            fd = os.pidfd_open(p.pid)
            # Pin first, then verify identity, ownership and exec metadata afresh.
            fresh = scan(proc=proc)
            safe, tools, jobs = decide(fresh, unit_mains)
            if fresh.get(p.pid) != p or not _same(proc, p) or p.pid in safe \
                    or relief_candidate({p.pid: p, **fresh}, safe,
                                        tools & {p.pid}, jobs & {p.pid}, proc) != p:
                return {'action': 'changed', 'pid': p.pid}
            signal.pidfd_send_signal(fd, signal.SIGTERM)
            self.last = now
            self.pending = (p, fd, now + TERM_GRACE)
            fd = None
            return {'action': 'term', 'pid': p.pid, 'start': p.start}
        except OSError as error:
            return {'action': 'unavailable', 'pid': p.pid, 'error': str(error)}
        finally:
            if fd is not None:
                os.close(fd)


class CacheRelief:
    """One delegated file-cache reclaim in flight; kernel reclaim may block.

    swappiness=0 excludes anonymous swapout. This can evict reusable file cache
    but never signals a process or changes a memory limit.
    """

    def __init__(self):
        self.thread = None
        self.result = None
        self.last = float('-inf')

    @staticmethod
    def target(proc=Path('/proc'), cgroups=Path('/sys/fs/cgroup')):
        path = (proc / 'self/cgroup').read_text().strip().split('::', 1)[-1]
        parts = PurePath(path).parts
        for index, part in enumerate(parts):
            if part == f'user@{os.getuid()}.service':
                return cgroups.joinpath(*parts[1:index + 1], 'session.slice', 'memory.reclaim')
        raise OSError('no owned user-manager cgroup found')

    def _run(self, target):
        try:
            # Resolve only the known delegated session leaf, never a broad parent.
            if target.stat().st_uid != os.getuid():
                raise PermissionError('session memory.reclaim is not owned by this user')
            with target.open('w') as handle:
                handle.write('268435456 swappiness=0\n')
            self.result = {'action': 'cache-reclaim-requested', 'requested_bytes': 268435456}
        except OSError as error:
            self.result = {'action': 'cache-reclaim-unavailable', 'error': str(error)}

    def step(self, now, dry_run=False):
        if self.thread is not None:
            if self.thread.is_alive():
                return {'action': 'cache-reclaim-pending'}
            result = self.result
            self.thread = None
            self.result = None
            return result
        if now - self.last < RELIEF_COOLDOWN:
            return {'action': 'cache-reclaim-cooldown'}
        try:
            target = self.target()
        except OSError as error:
            return {'action': 'cache-reclaim-unavailable', 'error': str(error)}
        if dry_run or REPORT_ONLY:
            return {'action': 'would-reclaim-cache', 'path': str(target),
                    'requested_bytes': 268435456, 'swappiness': 0}
        self.last = now
        self.thread = threading.Thread(target=self._run, args=(target,), daemon=True,
                                       name='oom-file-cache-reclaim')
        self.thread.start()
        return {'action': 'cache-reclaim-started', 'requested_bytes': 268435456}
