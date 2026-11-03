"""Bounded model-free hardware experiment; no arbitrary experiment commands."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid


def probe():
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(hash_work, [0, 1]))
    print(json.dumps({'digests': values}))


def hash_work(_):
    return hashlib.pbkdf2_hmac('sha256', b'host-optimizer-fixture', b'fixed-salt', 350000).hex()


def summarize(samples):
    if len(samples) != 12 or any(row.get('error') or not row.get('correct') for row in samples):
        return {'decision': 'reject', 'reason': 'incomplete or failed correctness/runtime evidence'}
    paired = []
    for i in range(0, 12, 2):
        arms = {row['arm']: row for row in samples[i:i+2]}
        if set(arms) != {'one_core', 'unlimited'}:
            return {'decision': 'reject', 'reason': 'missing matched arm'}
        paired.append(arms['unlimited']['wall_s']/arms['one_core']['wall_s'])
    ratio = statistics.median(paired)
    return {'decision': 'supported_fixture_only' if ratio < .9 and max(paired) < 1 else 'inconclusive',
            'median_paired_ratio': ratio, 'paired_ratios': paired,
            'scope': 'two-process PBKDF2 CPU replay, including process/scope startup; not whole-task or harness speed',
            'production_promotion': 'none; experiment validates an already owner-approved CPU policy only'}


def eligible(host):
    if host.get('cpus', 0) < 2 or host.get('mem_available_bytes', 0) < 4*2**30:
        return False
    pressure = host.get('pressure', {})
    for kind, row, threshold in (('cpu', 'some', 10), ('memory', 'full', .1), ('io', 'full', 1)):
        value = pressure.get(kind, {}).get(row, {}).get('avg10')
        if value is None or value >= threshold:
            return False
    return True


def measure_cpu(state, host, runner, atomic, sampler=None):
    path = state/'cpu-experiment.json'
    now = time.time()
    if path.exists():
        previous = json.loads(path.read_text())
        if 0 <= now-previous['attempted_at'] < 86400:
            return {'status': 'not_due', 'last_decision': previous.get('result', {}).get('decision'),
                    'last_attempted_at': previous['attempted_at']}
    if not eligible(host) or (state/'paused').exists():
        return {'status': 'held', 'reason': 'idle/resource gates or pause; no stress launched'}
    receipt = {'schema': 'z0.host-cpu-experiment.v1', 'attempted_at': now,
               'status': 'started', 'samples': []}
    # Checkpoint before launching: failures and crashes do not cause a retry storm.
    atomic(path, receipt)
    expected = hashlib.pbkdf2_hmac('sha256', b'host-optimizer-fixture', b'fixed-salt', 350000).hex()
    for pair in range(6):
        if sampler is not None and not eligible(sampler()):
            receipt['status'] = 'held_midrun'
            atomic(path, receipt)
            return {'status': 'held_midrun', 'reason': 'host became busy; partial results are not a win'}
        for arm in (('one_core', 'unlimited') if pair % 2 == 0 else ('unlimited', 'one_core')):
            if (state/'paused').exists():
                receipt['status'] = 'paused'
                atomic(path, receipt)
                return {'status': 'paused'}
            command = ['systemd-run', '--user', '--scope', '--quiet', '--collect',
                '--unit=host-optimizer-probe-'+uuid.uuid4().hex,
                '--property=Slice=agent.slice', '--property=MemoryMax=192M',
                '--property=MemorySwapMax=0', '--property=TasksMax=24',
                '--property=RuntimeMaxSec=15s', '--property=CPUWeight=1',
                '--property=CPUQuota='+('100%' if arm == 'one_core' else ''),
                sys.executable, str(Path(__file__).resolve()), 'probe']
            begin = time.monotonic()
            sample = {'pair': pair, 'arm': arm}
            try:
                observed = json.loads(runner(command, timeout=20))
                sample.update(wall_s=time.monotonic()-begin,
                              correct=observed.get('digests') == [expected, expected])
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                sample.update(wall_s=time.monotonic()-begin, error=type(exc).__name__, correct=False)
            receipt['samples'].append(sample)
            atomic(path, receipt)
            if not sample['correct']:
                receipt['result'] = summarize(receipt['samples'])
                receipt['status'] = 'failed'
                atomic(path, receipt)
                return {'status': 'failed', **receipt['result']}
    receipt['result'] = summarize(receipt['samples'])
    receipt['status'] = 'complete'
    atomic(path, receipt)
    return {'status': 'complete', **receipt['result']}


if __name__ == '__main__':
    if sys.argv[1:] != ['probe']:
        raise SystemExit('only fixed probe entry is supported')
    probe()
