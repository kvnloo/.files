"""Kernel OOM kill order for coding agents: disposable work first, never a harness root.

Owner rule (2026-10-25): "it can kill subagents just never the root process".

ROOT        A harness process (hermes, omp, claude, codex, pi, opencode) that is not a
            one-shot worker and either has no harness above it or owns a terminal of its
            own (an interactive session another agent opened); the main process of a
            *hermes* user service (gateway, dashboard, embedded agent hosts); Tern's
            daemon, GUI and remote server, which host every pane.
PROTECTED   Roots; a Hermes root's TUI renderer (node .../entry.js) and that renderer's
            direct children (the tui_gateway agent backend); every process above any of
            them up to the user manager (pane shell, terminal, Tern daemon, compositor --
            a pane shell's exit SIGHUPs the session running in it); and the main process
            of every unit holding one of them (its exit makes systemd stop the unit).
DISPOSABLE  Everything else under a harness -- tools, MCP servers, language-server
            brokers, subagent harnesses and their trees -- and anything else left in
            agent.slice. Desktop programs (browsers, terminals) keep their score.

Scores only move one way: protected processes are lowered, disposable ones raised.
An unprivileged process may lower a score only to the floor the user manager started
with (oom_score_adj_min: 100 under user@.service), so PROTECT_ADJ is tried first and
FLOOR_ADJ is the fallback. A child forked by a lowered shell inherits the low score;
it gets back the score its parent had before (see hand_back).
"""
from __future__ import annotations

import os
from pathlib import Path, PurePath
import re
from typing import NamedTuple

PROTECT_ADJ = -900
FLOOR_ADJ = 100
DISPOSABLE_ADJ = 800
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


def decide(procs: dict, unit_mains: dict | None = None) -> tuple[set, set]:
    """(protected, disposable) PIDs for one snapshot."""
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
    protected = roots | front | backends
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
    return protected, disposable


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
          proc: Path = Path('/proc'), dry_run: bool = False) -> dict:
    """Lower protected, raise disposable, hand inherited low scores back.

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
            if current <= PROTECT_ADJ or not _same(proc, p):
                continue
            target = None
            for value in (PROTECT_ADJ, FLOOR_ADJ):
                if current <= value:
                    break
                if value == PROTECT_ADJ and ('floor', pid, p.start) in checked:
                    continue  # refused before; retried when the caller clears `checked`
                if dry_run:
                    target = value
                    break
                try:
                    _write_adj(proc, pid, value)
                    target = value
                    break
                except PermissionError:
                    checked.add(('floor', pid, p.start))
                    continue
            if target is not None:
                lowered.setdefault(f'{pid}:{p.start}', current)
                result['lowered'].append([pid, p.comm, current, target])
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            result['failures'].append({'pid': pid, 'error': str(error)})
    for pid in sorted(disposable):
        p = procs[pid]
        if (pid, p.start) in checked:
            continue
        checked.add((pid, p.start))
        try:
            current = _read_adj(proc, pid)
            if current < DISPOSABLE_ADJ and _same(proc, p):
                if not dry_run:
                    _write_adj(proc, pid, DISPOSABLE_ADJ)
                result['raised'].append([pid, p.comm, current, DISPOSABLE_ADJ])
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            result['failures'].append({'pid': pid, 'error': str(error)})
    result['handed_back'] = hand_back(procs, protected, disposable, lowered, checked, proc, dry_run)
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
