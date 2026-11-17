#!/usr/bin/env python3
"""Measured runtimes per (task, node), learned from the receipts the fleet already writes.

  fleet_runtimes.py scan            rebuild the table from every receipt -> runtimes.json
  fleet_runtimes.py show [FILTER]   print the table (task, node, ok/n, p50, p90)
  fleet_runtimes.py pick --nodes mbp,boat [--repo R] -- CMD...
                                    print the eligible node to use for CMD: one with
                                    fewer than MIN_OK attempts first (explore), else the
                                    fastest measured; exit 1 with no output when no node
                                    has evidence and none needs exploring
  fleet_runtimes.py record --node N --seconds S --rc RC [--repo R] [--job J] -- CMD...
                                    append one end-to-end sample (fleet-build calls this)

Sources (read-only): fleet-build's own ledger (runtimes.jsonl, end-to-end wall
time including queue wait), the fleet run store (Kueue job receipts + native run logs),
Avrea run dirs, and the hc-turbo hill-climb ledger. `pick` never widens
eligibility: callers pass only the nodes their privacy/toolchain rules allow.
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MIN_OK = 2  # successful samples a node needs before it can win a pick
RESCAN_AFTER = 6 * 3600  # a full receipt rescan is started by `record` once the table is older
HC_LEDGER = Path('/mnt/zer0models/workspace/zer0/data/operations/hc-turbo-20261106/state/ledger.jsonl')
# (runner, pattern): a task is the runner plus its first target; flags never split a task.
RUNNERS = [
    ('gradle', r'\b(?:\./)?gradlew?\s+(?:-\S+\s+)*([:\w-]+)'),
    ('pytest', r'\bpytest\b(?:\s+-\S+(?:\s+(?:no|\d+))?)*(?:\s+([\w./-]+))?'), ('unittest', r'-m\s+unittest\b()'),
    ('bun', r'\bbun\s+(test|install|run\s+[\w:-]+)'), ('cargo', r'\bcargo\s+(build|test|bench)'),
    ('npm', r'\bnpm\s+(test|ci|run\s+[\w:-]+)'), ('pnpm', r'\bpnpm\s+(test|install|run\s+[\w:-]+)'),
    ('make', r'\bmake\b(?:\s+([\w-]+))?'), ('cmake', r'\bcmake\s+--build()'), ('go', r'\bgo\s+(build|test)'),
    ('docker', r'\bdocker\s+(build|run)'),
]


def state_dir():
    return Path(os.environ.get('FLEET_STATE') or os.path.expanduser('~/.local/state/fleet'))


def state_file():
    return state_dir() / 'runtimes.json'


def ledger_file():
    return state_dir() / 'runtimes.jsonl'


REPO_ROOTS = ['/mnt/zer0models/workspace/zer0/oss/*', '/mnt/zer0models/workspace/zer0/products/*',
              '/mnt/zer0models/github/*', '/mnt/zer0models/workspace/zer0/.files', '/workspace/*',
              os.path.expanduser('~/.hermes/hermes-agent'), '/mnt/zer0models/worktrees/*']


def repos_for_heads(heads, cache):
    """Map receipt git_head -> repo name by asking each local clone; cached across scans."""
    import subprocess
    misses = cache.setdefault('_miss', {})  # head -> last failed lookup; retried weekly
    todo = sorted(h for h in heads if h not in cache and time.time() - misses.get(h, 0) > 7 * 86400)
    if not todo:
        return cache
    deadline = time.monotonic() + 240  # unresolved heads stay unknown and are retried next scan
    for gitdir in sorted({p for root in REPO_ROOTS for p in glob.glob(root + '/.git')}):
        if not todo or time.monotonic() > deadline:
            break
        top = os.path.dirname(gitdir)
        try:
            out = subprocess.run(['git', '-C', top, 'cat-file', '--batch-check'], input='\n'.join(todo) + '\n',
                                 capture_output=True, text=True, timeout=5).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            continue
        found = {line.split()[0] for line in out if line.split()[1:2] == ['commit']}
        for h in found:
            cache[h] = os.path.basename(top)
        todo = [h for h in todo if h not in found]
    for h in todo:  # in no local clone (or not reached before the deadline)
        misses[h] = time.time()
    return cache


def norm(text):
    text = re.sub(r'[0-9a-f]{7,}', 'H', text)
    text = re.sub(r'/tmp/\S+', '/tmp/X', text)
    return re.sub(r'\d+', 'N', text).strip()


def task_key(command, repo=None):
    """Stable name for 'the same work': repo + runner + target, wrapper and SHAs stripped."""
    text = command if isinstance(command, str) else ' '.join(map(str, command))
    text = re.sub(r'\b(?:pip|uv pip|apt-get|apt)\s+install\b[^;&|\n]*', ' ', text)  # installs are not the work
    marker = list(re.finditer(r'\bfleet-build\s+\S+\s+', text))
    if marker:  # drop fleet-build's own wrapper script; keep the user's command
        text = text[marker[-1].end():]
    text = re.sub(r'^(?:env\s+)?(?:\w+=\S*\s+)*', '', text)
    for runner, pattern in RUNNERS:
        m = re.search(pattern, text)
        if m:
            key = norm(f'{runner} {m.group(1) or ""}')
            break
    else:
        key = norm(' '.join(text.split()[:3]))[:80]
    return f'{repo}:{key}' if repo else key


def iso(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def ledger_samples(path=None):
    try:
        lines = open(path or ledger_file())
    except OSError:
        return
    for line in lines:
        try:
            d = json.loads(line)
            if d['rc'] == 75 and time.time() - d['at'] > 86400:
                continue  # an admission hold is not evidence about the node; re-explore next day
            yield {'task': task_key(d['command'], d.get('repo')), 'node': d['node'], 'seconds': d['seconds'],
                   'ok': d['rc'] == 0, 'at': d['at'], 'job': d.get('job')}
        except (ValueError, KeyError, TypeError):
            continue


def fleet_samples(runs, heads=None):
    heads = {} if heads is None else heads
    for path in glob.glob(str(runs / '*.json')):
        try:
            d = json.load(open(path))
        except (OSError, ValueError):
            continue
        term = d.get('terminal') if isinstance(d.get('terminal'), dict) else None
        if term and d.get('command'):  # Kueue (MBP) receipt
            st = (term.get('job') or {}).get('status') or {}
            if st.get('startTime') and st.get('completionTime'):
                head = (d.get('source_snapshot') or {}).get('git_head') if isinstance(d.get('source_snapshot'), dict) else None
                yield {'task': task_key(d['command'], heads.get(head)), 'node': 'mbp', 'job': d.get('job_id'),
                       'seconds': iso(st['completionTime']) - iso(st['startTime']),
                       'ok': term.get('exit_code') == 0, 'at': iso(st['completionTime'])}
    for path in glob.glob(str(runs / '*.log')):
        name = Path(path).name
        m = re.match(r'(?:fleet-mbp-[0-9a-f]+|\d{8}-\d{6}-[0-9a-f]+)-(.+)\.log$', name)
        if not m or name.startswith('fleet-mbp-'):
            continue  # Kueue logs are covered by their receipts
        try:
            text = open(path, errors='replace').read()
        except OSError:
            continue
        t = re.search(r'(?:total|wall)_seconds=([\d.]+)', text)
        if not t:
            continue
        rc = re.search(r'^# (?:status=\S+ )?exit[= ](-?\d+)', text, re.M)
        cmd = re.search(r'cmd=(.*?)(?:\n# |\Z)', text, re.S)
        if m[1] == 'boat':
            cmd = re.search(r'"command":\s*(\[.*?\]|".*?")', text, re.S) or cmd
        if not cmd:
            continue  # no command recorded (old Boat logs): not attributable to any task
        receipt = Path(path[:-len(m[1]) - 5] + '.json')
        try:
            head = json.loads(receipt.read_text()).get('source_snapshot', {}).get('git_head')
        except (OSError, ValueError, AttributeError):
            head = None
        yield {'task': task_key(cmd.group(1), heads.get(head)), 'node': m[1], 'seconds': float(t[1]), 'job': name[:-5],
               'ok': bool(rc) and rc[1] == '0', 'at': os.path.getmtime(path)}


def avrea_samples(runs):
    for run in glob.glob(str(runs / 'avrea-*')):
        try:
            req = json.load(open(run + '/request.json'))
            st = json.load(open(run + '/status.json'))
        except (OSError, ValueError):
            continue
        jobs = [j for j in st.get('jobs', []) if j.get('startedAt') and j.get('completedAt')]
        if not jobs:
            continue
        start, end = min(iso(j['startedAt']) for j in jobs), max(iso(j['completedAt']) for j in jobs)
        repo = (req.get('repository') or '').split('/')[-1] or None
        yield {'task': task_key(req.get('command', ''), repo), 'node': 'avrea:' + req.get('runner', 'default'),
               'seconds': end - start, 'ok': st.get('conclusion') == 'success', 'at': end}


def hc_samples(ledger=HC_LEDGER):
    """Hill-climb evals: one sample per finished run, keyed by spec id, per device."""
    try:
        lines = open(ledger)
    except OSError:
        return
    for line in lines:
        try:
            d = json.loads(line)
            started = os.path.getmtime(Path(d['run_dir']) / 'process.json')
        except (ValueError, KeyError, OSError, TypeError):
            continue
        yield {'task': 'hc:' + d['id'], 'node': d['device'], 'seconds': d['at'] - started,
               'ok': d.get('decision') != 'FAIL', 'at': d['at'], 'decision': d.get('decision')}


def hc_metrics(ledger=HC_LEDGER):
    """Library x device speed from hill-climb runs: the incumbent's METRIC per track, not run wall
    time (wall time on an owner-active phone measures waiting, not the library)."""
    table = {}
    try:
        lines = open(ledger)
    except OSError:
        return table
    for line in lines:
        try:
            d = json.loads(line)
            with open(Path(d['run_dir']) / 'process.log', 'rb') as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 4096))
                tail = f.read().decode(errors='replace')
        except (ValueError, KeyError, OSError, TypeError):
            continue
        for m in re.finditer(r'^METRIC (\S+) inc=([\d.]+) cand=([\d.]+)', tail, re.M):
            cell = table.setdefault(m[1], {}).setdefault(d['device'], {'inc': [], 'keeps': 0})
            cell['inc'].append(float(m[2]))
            cell['keeps'] += d.get('decision') == 'KEEP'
    for devices in table.values():
        for cell in devices.values():
            xs = cell.pop('inc')
            cell.update(n=len(xs), best=min(xs), p50=round(statistics.median(xs), 2))
    return table


def summarize(samples):
    table = {}
    for s in samples:
        cell = table.setdefault(s['task'], {}).setdefault(s['node'], {'n': 0, 'ok': 0, 'ok_seconds': [], 'last': 0})
        cell['n'] += 1
        cell['last'] = max(cell['last'], s['at'])
        if s['ok'] and s['seconds'] >= 0:
            cell['ok'] += 1
            cell['ok_seconds'].append(s['seconds'])
    for nodes in table.values():
        for cell in nodes.values():
            xs = sorted(cell.pop('ok_seconds'))
            cell['p50'] = round(statistics.median(xs), 1) if xs else None
            cell['p90'] = round(xs[min(len(xs) - 1, int(0.9 * len(xs)))], 1) if xs else None
    return table


def receipt_heads(runs):
    for path in glob.glob(str(runs / '*.json')):
        try:
            snap = json.load(open(path)).get('source_snapshot')
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(snap, dict) and snap.get('git_head'):
            yield snap['git_head']


def scan():
    import fcntl
    from fleet_paths import runs_dir
    state_dir().mkdir(parents=True, exist_ok=True)
    lock = open(state_dir() / 'runtimes.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return load()  # another scan is already rebuilding the table
    runs = runs_dir()
    heads = repos_for_heads(set(receipt_heads(runs)), load().get('heads', {}))
    own = list(ledger_samples())
    seen = {s['job'] for s in own if s.get('job')}
    receipts = [s for s in fleet_samples(runs, heads) if s.get('job') not in seen]
    samples = [*own, *receipts, *avrea_samples(runs), *hc_samples()]
    out = {'generated_at': time.time(), 'samples': len(samples), 'tasks': summarize(samples), 'heads': heads,
           'metrics': hc_metrics()}
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(out, indent=1, sort_keys=True) + '\n')
    tmp.replace(path)
    return out


def load():
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {'tasks': {}}


def pick(table, task, nodes, explore=()):
    """Explore an `explore` node with < MIN_OK attempts, else the fastest node with >= MIN_OK successes."""
    seen = table.get(task, {})
    for n in explore:
        if n in nodes and seen.get(n, {}).get('n', 0) < MIN_OK:
            return n
    cells = {n: c for n, c in seen.items() if n in nodes and c['ok'] >= MIN_OK and c['p50'] is not None}
    if not cells:
        return None
    return min(cells, key=lambda n: cells[n]['p50'])


def record(node, seconds, rc, command, repo=None, job=None):
    path = ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({'at': time.time(), 'node': node, 'seconds': round(seconds, 3), 'rc': rc,
                       'repo': repo, 'job': job, 'command': command}) + '\n'
    with open(path, 'a') as f:  # one O_APPEND write per job: concurrent writers do not interleave
        f.write(line)
    # Keep the table fresh without a timer: fold this sample in directly.
    table = load()
    cell = table.setdefault('tasks', {}).setdefault(task_key(command, repo), {}).setdefault(
        node, {'n': 0, 'ok': 0, 'p50': None, 'p90': None, 'last': 0})
    cell['n'] += 1
    cell['last'] = time.time()
    if rc == 0:
        cell['ok'] += 1
        cell['p50'] = round(seconds, 1) if cell['p50'] is None else round((cell['p50'] * 3 + seconds) / 4, 1)
    tmp = state_file().with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(table, indent=1, sort_keys=True) + '\n')
    tmp.replace(state_file())
    if time.time() - table.get('generated_at', 0) > RESCAN_AFTER:  # self-refresh, no timer to forget
        import subprocess
        subprocess.Popen(['nice', '-n', '19', sys.executable, __file__, 'scan'], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('scan')
    show = sub.add_parser('show')
    show.add_argument('filter', nargs='?', default='')
    p = sub.add_parser('pick')
    p.add_argument('--nodes', required=True)
    p.add_argument('--repo')
    p.add_argument('--explore', default='', help='nodes to try MIN_OK times before trusting medians')
    p.add_argument('command', nargs=argparse.REMAINDER)
    r = sub.add_parser('record')
    for flag in ('--node', '--repo', '--job'):
        r.add_argument(flag)
    r.add_argument('--seconds', type=float, required=True)
    r.add_argument('--rc', type=int, required=True)
    r.add_argument('command', nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.cmd == 'record':
        record(a.node, a.seconds, a.rc, a.command[1:] if a.command[:1] == ['--'] else a.command, a.repo, a.job)
        return 0
    if a.cmd == 'scan':
        out = scan()
        print(f"{out['samples']} samples, {len(out['tasks'])} tasks -> {state_file()}")
        return 0
    if a.cmd == 'show':
        data = load()
        for track, devices in sorted(data.get('metrics', {}).items()):
            if a.filter in track:
                print(f"{track[:60]:60} " + ' | '.join(f"{d} p50={c['p50']} best={c['best']} n={c['n']} keeps={c['keeps']}"
                                                     for d, c in sorted(devices.items(), key=lambda kv: kv[1]['p50'])))
        for task, nodes in sorted(data['tasks'].items()):
            if a.filter not in task:
                continue
            for node, c in sorted(nodes.items(), key=lambda kv: kv[1]['p50'] or 1e18):
                print(f"{task[:60]:60} {node:16} {c['ok']:>4}/{c['n']:<4} p50={c['p50']}s p90={c['p90']}s")
        return 0
    command = a.command[1:] if a.command[:1] == ['--'] else a.command
    tasks = load()['tasks']
    nodes = set(a.nodes.split(','))
    explore = [n for n in a.explore.split(',') if n]
    key = task_key(command, a.repo)
    best = pick(tasks, key, nodes, explore)
    if best:
        exploring = best in explore and tasks.get(key, {}).get(best, {}).get('n', 0) < MIN_OK
        print(best + (' explore' if exploring else ''))
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
