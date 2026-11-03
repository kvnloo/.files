#!/usr/bin/env python3
"""Local, event-driven host performance learner; not a replacement scheduler.

No inference, shell commands, source-message capture, process kills, pod writes,
cache deletion or arbitrary mutation. The only actuator resets the previously
approved agent CPU ceilings; all other findings remain evidence-backed proposals.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time

SCHEMA = 'z0.host-optimization.v1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
CGROUP = Path('/sys/fs/cgroup')
DEFAULT_STATE = Path('/mnt/zer0models/sft-svlm/data/telemetry/activity/host-optimizer')
DEFAULT_AV = Path('/mnt/zer0models/sft-svlm/data/agentsview/sessions.db')
SERVICE_UNITS = ('fleet-health.service', 'z0int-policy.service',
                 'agent-telemetry-refresh.service', 'z0-ghcache.service')


def atomic(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)


def run(argv, timeout=12):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                            stdin=subprocess.DEVNULL, check=False)
    if result.returncode:
        # Never retain stderr: a provider/helper may print credentials there.
        raise RuntimeError(f'{Path(argv[0]).name} exit {result.returncode}')
    return result.stdout


def fields(path):
    return {key.rstrip(':'): value for key, value in
            (line.split(None, 1) for line in path.read_text().splitlines() if ' ' in line)}


def psi(path):
    result = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        result[parts[0]] = {k: float(v) for k, v in (x.split('=') for x in parts[1:])}
    return result


def scope_sample(path):
    return {'cpu_max': (path/'cpu.max').read_text().strip(),
            'cpu_stat': {k: int(v) for k, v in fields(path/'cpu.stat').items()},
            'memory_current': int((path/'memory.current').read_text()),
            'memory_events': {k: int(v) for k, v in fields(path/'memory.events').items()}}


def sample_host():
    errors = []
    memory = fields(Path('/proc/meminfo'))
    disks = {}
    for name, path in (('root', '/'), ('bulk', '/mnt/zer0models')):
        usage = shutil.disk_usage(path)
        disks[name] = {'total_bytes': usage.total, 'free_bytes': usage.free}
    sample = {'ts': time.time(), 'monotonic': time.monotonic(),
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'host': socket.gethostname(), 'cpus': os.cpu_count(),
              'mem_available_bytes': int(memory['MemAvailable'].split()[0])*1024,
              'mem_total_bytes': int(memory['MemTotal'].split()[0])*1024,
              'load': list(os.getloadavg()), 'disks': disks, 'pressure': {}, 'cgroups': {}}
    for kind in ('cpu', 'memory', 'io'):
        try:
            sample['pressure'][kind] = psi(Path('/proc/pressure')/kind)
        except (OSError, ValueError):
            errors.append('pressure unavailable: '+kind)
    base = CGROUP/f'user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service'
    for name in ('agent.slice', 'app.slice', 'app-t3code-agents.slice'):
        try:
            sample['cgroups'][name] = scope_sample(base/name)
        except (OSError, ValueError):
            errors.append('cgroup unavailable: '+name)
    # Native services/scopes stay native. Read only accounting, never argv/env.
    paths = list(base.glob('*.service'))
    for branch in ('app.slice', 'agent.slice'):
        paths.extend((base/branch).glob('*.scope'))
        paths.extend((base/branch).glob('*.service'))
    sample['native_cgroup_coverage'] = {'capped': len(paths) > 256,
        'hierarchical_totals_present': True, 'do_not_sum_parent_and_child': True}
    for path in sorted(paths)[:256]:
        if path.name.startswith(('host-optimizer', 'host-optimizer-probe')):
            continue
        try:
            row = scope_sample(path)
            if row['memory_current']:
                sample['cgroups']['native:'+path.name] = row
        except (OSError, ValueError):
            pass  # cgroup may vanish between enumeration and accounting read
    sample['mode'] = 'unknown'
    try:
        graphical = run(['systemctl', '--user', 'show', 'graphical-session.target', '-p', 'ActiveState', '--value']).strip()
        sample['mode'] = 'desktop' if graphical == 'active' else 'headless' if graphical == 'inactive' else 'unknown'
    except (OSError, RuntimeError, subprocess.SubprocessError):
        pass
    sample['errors'] = errors
    return sample


def deltas(current, prior):
    if not prior or current['boot_id'] != prior['boot_id']:
        return {'status': 'baseline_needed'}
    seconds = current['monotonic'] - prior['monotonic']
    if seconds <= 0 or seconds > 600:
        return {'status': 'stale_or_invalid_interval'}
    result = {'status': 'measured', 'interval_s': seconds, 'cgroups': {}}
    for name, row in current['cgroups'].items():
        old = prior['cgroups'].get(name)
        if not old:
            continue
        delta = {k: v-old['cpu_stat'].get(k, v) for k, v in row['cpu_stat'].items()}
        if any(v < 0 for v in delta.values()):
            continue  # recreated cgroup is a new baseline, never negative utilization
        periods = delta.get('nr_periods', 0)
        result['cgroups'][name] = {
            'cpu_cores_used': delta.get('usage_usec', 0)/1e6/seconds,
            'throttled_period_fraction': delta.get('nr_throttled', 0)/periods if periods else None,
            'oom_kill_delta': row['memory_events'].get('oom_kill', 0)-old['memory_events'].get('oom_kill', 0)}
    return result


def harness_summary(path, now=None):
    """Read derived numeric signals only; never load messages, prompts or tool args."""
    now = now or datetime.now(timezone.utc)
    since = (now-timedelta(days=7)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    conn = sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True, timeout=2)
    try:
        conn.execute('pragma query_only=on')
        deadline = time.monotonic()+4
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        rows = conn.execute('''select agent,machine,count(*),
            coalesce(sum(tool_failure_signal_count),0),coalesce(sum(tool_retry_count),0),
            coalesce(max(consecutive_failure_max),0),coalesce(sum(runaway_tool_loop_count),0),
            coalesce(sum(missing_verification_count),0)
            from sessions where local_modified_at>=? and is_automated=0
            and relationship_type!='subagent' and deleted_at is null
            group by agent,machine order by agent,machine limit 201''', (since,)).fetchall()
        groups = [{'agent': a, 'machine': m, 'sessions': n, 'failure_signals': failures,
                   'retries': retries, 'max_failure_streak': streak, 'loops': loops,
                   'missing_verification': verification}
                  for a, m, n, failures, retries, streak, loops, verification in rows[:200]]
        return {'status': 'observed', 'window_days': 7, 'capped': len(rows)>200,
                'sampled_sessions': sum(row['sessions'] for row in groups), 'source': str(path),
                'definition': 'derived parser signals in recently modified sessions; not independently verified failures or tool latency',
                'groups': groups}
    finally:
        conn.close()


def cluster_summary():
    kube = shutil.which('kubectl')
    if not kube:
        return {'status': 'unavailable', 'reason': 'kubectl missing'}
    prefix = [kube, '--kubeconfig='+str(Path.home()/'.kube/k3s.yaml'), '--request-timeout=8s']
    pods = json.loads(run(prefix+['get', 'pods', '-A', '-o', 'json']))['items']
    restarts, waiting, terminated = Counter(), Counter(), Counter()
    for pod in pods:
        namespace = pod['metadata']['namespace']
        for status in pod.get('status', {}).get('containerStatuses', []):
            restarts[namespace] += status.get('restartCount', 0)
            state = status.get('state', {})
            if state.get('waiting'):
                waiting[state['waiting'].get('reason', 'unknown')] += 1
            previous = status.get('lastState', {}).get('terminated')
            if previous:
                terminated[previous.get('reason', 'unknown')] += 1
    return {'status': 'observed', 'pod_count': len(pods), 'restarts_lifetime_by_namespace': dict(restarts),
            'waiting_reasons': dict(waiting), 'previous_termination_reasons': dict(terminated),
            'caveat': 'lifetime counters are not current restart rates; native sessions are not Kubernetes workloads'}


def cpu_repair(enabled, paused, runner=run):
    if paused or not enabled:
        return {'status': 'disabled'}
    # Narrow actuator, approved explicitly by the owner. Never kill/move sessions.
    units = json.loads(runner(['systemctl', '--user', 'list-units', '--type=scope', '--all', '--output=json']))
    targets = ['agent.slice'] + [row['unit'] for row in units
        if re.fullmatch(r'hermes-worker-[A-Za-z0-9_.-]+\.scope', row.get('unit', ''))]
    repaired = []
    for unit in targets:
        quota = runner(['systemctl', '--user', 'show', unit, '-p', 'CPUQuotaPerSecUSec', '--value']).strip()
        if quota == 'infinity':
            continue
        # Do not touch an unrecognized quota. Record it for review instead.
        if quota not in ('1s', '2s'):
            continue
        runner(['systemctl', '--user', 'set-property', '--runtime', unit, 'CPUQuota='])
        actual = runner(['systemctl', '--user', 'show', unit, '-p', 'CPUQuotaPerSecUSec', '--value']).strip()
        if actual != 'infinity':
            raise RuntimeError('CPU quota repair readback failed')
        repaired.append(unit)
    return {'status': 'checked', 'repaired': repaired,
            'scope': 'only known 1-core/2-core ceilings; weights, memory, placement and security unchanged'}


def rank_findings(host, harnesses, cluster, steward, service_states):
    result = []
    def add(key, priority, observation, owner, experiment):
        result.append({'key': key, 'priority': priority, 'observation': observation,
                       'owner': owner, 'next_experiment': experiment,
                       'promotion': 'requires paired baseline/candidate outcomes and rollback; observation alone is not a win'})
    root = host['disks']['root']['free_bytes']
    if root < 15*2**30:
        add('root-disk-pressure', 100, {'free_bytes': root, 'threshold_bytes': 15*2**30},
            '.files storage', 'Inventory allocation off critical path; do not delete active/source data.')
    for kind in ('memory', 'io'):
        value = host.get('pressure', {}).get(kind, {}).get('full', {}).get('avg60')
        if value is not None and value >= 1:
            add(kind+'-pressure', 95, {'full_avg60': value}, '.files + Kerdoios',
                'Join tool timings to this interval; compare one placement/concurrency change on replay, not live sessions.')
    for unit, state in service_states.items():
        if state.get('ActiveState') == 'failed':
            add('service:'+unit, 90, state, '.files', 'Read exact unit failure and reproduce its input before repair.')
    for group in harnesses.get('groups', []):
        if group.get('failure_signals', 0) or group.get('loops', 0):
            add('harness:'+group['agent']+':'+group['machine'], 70, group,
                'owning harness + z0evals', 'Sample provenance-linked failing tool episodes; run held-out paired evaluation with correctness and p90 guards.')
    if cluster.get('waiting_reasons'):
        add('cluster-waiting', 85, cluster['waiting_reasons'], '.files K3s',
            'Inspect queue admission and resource demand; do not raise quotas from occupancy alone.')
    for finding in steward.get('findings', [])[:30]:
        add('fleet:'+finding['key'], min(85, finding['severity']),
            {'claim': finding['claim'], 'sample_count': finding['sample_count']},
            '.files fleet / Kerdoios', 'Use steward source IDs and parameters; validate candidate before changing placement.')
    return sorted(result, key=lambda row: (-row['priority'], row['key']))


def steward_cache_reusable(cached, fingerprint, now, exists):
    age = now-cached.get('analyzed_at', 0)
    changed = cached.get('fingerprint') != fingerprint
    return (cached.get('status') == 'observed' and exists and
            0 <= age < (300 if changed else 1800))


def tick(state, fleet_state, av, repair=False, experiments=False):
    if (state/'paused').exists():
        print('HOST_OPTIMIZER_PAUSED')
        return 0
    # Do not silently write private telemetry to root when the data disk is absent.
    if not os.path.ismount('/mnt/zer0models'):
        raise RuntimeError('canonical data mount unavailable')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    os.umask(0o077)
    with (state/'writer.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('HOST_OPTIMIZER_BUSY')
            return 0
        # Recheck pause at mutation boundary; concurrent operator pause is durable.
        if (state/'paused').exists():
            return 0
        begin = time.monotonic()
        host = sample_host()
        previous_path = state/'latest.json'
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
        result = {'schema': SCHEMA, 'generated_at': host['ts'], 'host': host,
                  'delta': deltas(host, previous.get('host')), 'errors': []}
        def observe(name, fn):
            try:
                result[name] = fn()
            except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
                result[name] = {'status': 'unavailable', 'reason': type(exc).__name__}
                result['errors'].append(name+':'+type(exc).__name__)
        observe('harnesses', lambda: harness_summary(av))
        observe('cluster', cluster_summary)
        states = {}
        for unit in SERVICE_UNITS:
            try:
                text = run(['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '-p', 'Result'])
                states[unit] = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                states[unit] = {'ActiveState': 'unknown'}
        result['services'] = states
        # Reuse historical analysis until logs change or the health refresh expires.
        # Sampling stays event-driven; do not reparse thousands of unchanged logs.
        output = state/'fleet-steward'
        from fleet_paths import runs_dir
        spool = runs_dir()
        signature = hashlib.sha256()
        for path in sorted({p for root in (fleet_state/'runs', spool) for p in root.glob('*.log')}):
            try:
                stat = path.stat()
                signature.update(f'{path}:{stat.st_size}:{stat.st_mtime_ns}\n'.encode())
            except OSError:
                continue
        fingerprint = signature.hexdigest()
        cached = previous.get('steward_run', {})
        cache_age = host['ts']-cached.get('analyzed_at', 0)
        logs_changed = cached.get('fingerprint') != fingerprint
        reusable = steward_cache_reusable(cached, fingerprint, host['ts'],
                                           (output/'findings.json').is_file())
        if reusable:
            result['steward_run'] = {**cached, 'cached': True,
                                    'source_changes_pending': logs_changed, 'age_s': cache_age}
        else:
            observe('steward_run', lambda: {'status': 'observed', 'cached': False,
                'fingerprint': fingerprint, 'analyzed_at': host['ts'], 'age_s': 0,
                'summary': run([sys.executable, str(ROOT/'scripts/fleet-steward'),
                    '--state', str(fleet_state), '--output', str(output), '--runs', str(spool),
                    '--dry-run'], timeout=60).strip()})
        steward = {}
        if result['steward_run'].get('status') == 'observed':
            steward = json.loads((output/'findings.json').read_text())
        observe('cpu_policy', lambda: cpu_repair(repair, (state/'paused').exists()))
        result['findings'] = rank_findings(host, result['harnesses'], result['cluster'], steward, states)
        if experiments:
            from host_experiments import measure_cpu
            observe('cpu_experiment', lambda: measure_cpu(state, host, run, atomic, sample_host))
        result['runtime_s'] = time.monotonic()-begin
        result['coverage'] = {'host': 'live', 'cluster': result['cluster']['status'],
            'harnesses': result['harnesses']['status'], 'cross_harness_tool_latency': 'not joined',
            'automatic_experiments': 'fixed CPU replay, once daily behind idle gate' if experiments else 'not enabled', 'automatic_changes': 'known CPU-ceiling regression repair only'}
        # Bounded aggregate history, not a second raw event/trace store.
        history_path = state/'history.json'
        history = json.loads(history_path.read_text()) if history_path.exists() else []
        history = [row for row in history if host['ts']-row['ts'] < 7*86400][-5039:]
        history.append({'ts': host['ts'], 'mem_available_bytes': host['mem_available_bytes'],
            'pressure': host['pressure'], 'delta': result['delta'],
            'findings': [row['key'] for row in result['findings']]})
        atomic(history_path, history)
        recurrence = Counter(key for row in history for key in set(row['findings']))
        for finding in result['findings']:
            finding['observations_in_retained_history'] = recurrence[finding['key']]
        atomic(state/'experiments.json', {'schema': SCHEMA, 'generated_at': host['ts'],
            'status': 'ranked_proposals_not_executed', 'candidates': result['findings']})
        atomic(previous_path, result)
        print(f'HOST_OPTIMIZER_OK findings={len(result["findings"])} samples={len(history)} runtime_s={result["runtime_s"]:.3f} errors={len(result["errors"])}')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('tick', 'status', 'pause', 'resume'), nargs='?', default='tick')
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--fleet-state', type=Path, default=Path.home()/'.local/state/fleet')
    parser.add_argument('--agentsview', type=Path, default=DEFAULT_AV)
    parser.add_argument('--repair-cpu', action='store_true')
    parser.add_argument('--experiments', action='store_true', help='fixed, idle-gated CPU replay only; no model/API spend')
    args = parser.parse_args()
    if args.action in ('pause', 'resume'):
        args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = args.state/'paused'
        if args.action == 'pause':
            marker.touch(mode=0o600)
        else:
            marker.unlink(missing_ok=True)
        print(args.action)
        return 0
    if args.action == 'status':
        value = json.loads((args.state/'latest.json').read_text())
        print(json.dumps({'paused': (args.state/'paused').exists(),
            'age_s': time.time()-value['generated_at'], **value}, indent=2))
        return 0
    return tick(args.state, args.fleet_state, args.agentsview, args.repair_cpu, args.experiments)


if __name__ == '__main__':
    raise SystemExit(main())
