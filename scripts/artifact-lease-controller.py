#!/usr/bin/env python3
"""Bounded fleet transport; only artifact-leases.py owns deletion policy."""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ADB = str(Path.home() / 'android/sdk/platform-tools/adb')
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=8', '-o', 'ConnectionAttempts=1',
       '-o', 'ControlMaster=no', '-o', 'ControlPath=none']


def run(argv, source=None):
    p = subprocess.run(argv, input=source, text=True, capture_output=True, timeout=120)
    if p.returncode:
        raise RuntimeError('transport/identity/core failed: ' + p.stderr[-1000:])
    return p.stdout


def native_transport(node):
    devices = run([ADB, 'devices']).splitlines()[1:]
    for line in devices:
        fields = line.split()
        if len(fields) != 2 or fields[1] != 'device':
            continue
        serial = fields[0]
        identity = run([ADB, '-s', serial, 'shell', 'getprop ro.serialno; getprop ro.product.model']).splitlines()
        if identity == [node['serial'], node['model']]:
            return serial
    raise RuntimeError('no authenticated transport with exact hardware identity')


def native_inventory(node, apply):
    serial = native_transport(node)
    # No Python on Android. No independent deletion implementation here: unknown
    # process visibility and unclassified leases must never authorize deletion.
    script = '''set -f
printf 'IDENTITY\\t%s\\t%s\\n' "$(getprop ro.serialno)" "$(getprop ro.product.model)"
printf 'SPACE\\t'; df -Pk /data/local/tmp | tail -n 1
for root in /data/local/tmp/fleet-jobs /data/local/tmp/edge-probe-*; do
  [ -d "$root" ] && [ ! -L "$root" ] || continue
  case "$root" in /data/local/tmp/fleet-jobs)
    for item in "$root"/*; do
      [ -d "$item" ] && [ ! -L "$item" ] || continue
      bytes=$(du -sk "$item" 2>/dev/null) || exit 1
      printf 'KEEP\\t%s\\t%s\\n' "$item" "$bytes"
    done;;
  *) bytes=$(du -sk "$root" 2>/dev/null) || exit 1
     printf 'KEEP\\t%s\\t%s\\n' "$root" "$bytes";;
  esac
done
'''
    # Glob expansion is restricted to fixed roots, never supplied by a report.
    script = script.replace('set -f\n', '')
    raw = run([ADB, '-s', serial, 'shell', 'sh'], script)
    first = raw.splitlines()[0].split('\t')
    if first != ['IDENTITY', node['serial'], node['model']]:
        raise RuntimeError('Android identity changed')
    return {'schema': 'z0.artifact-native-inventory.v1', 'identity': node['serial'],
            'transport': serial, 'mode': 'safe-noop-apply' if apply else 'dry-run',
            'proc_visibility': 'unknown', 'decision': 'KEEP',
            'reason': 'native inventory only; unknown live/process visibility; no deletion authority',
            'would_reap_bytes': 0, 'inventory': raw.splitlines()[1:]}


def execute(name, node, apply, enroll, source):
    if node['transport'] == 'adb':
        return native_inventory(node, apply)
    # Keep receipts on each node; ship core and its existing #63 classifier together.
    wrapper = '''import contextlib,getpass,io,json,pathlib,socket,sys,tempfile
expected=json.loads(sys.argv[1])
assert socket.gethostname()==expected['hostname'] and getpass.getuser()==expected['user'], 'identity mismatch'
payload=json.loads(sys.stdin.read())
output=pathlib.Path.home()/'.local/state/artifact-leases/core'/expected['name']
with tempfile.TemporaryDirectory(prefix='artifact-lease-source-') as tmp:
 for name,source in payload.items(): (pathlib.Path(tmp)/name).write_text(source)
 core=str(pathlib.Path(tmp)/'artifact-leases.py')
 sys.argv=[core,'--node',expected['name'],'--output',str(output)]+expected['flags']
 scope={'__name__':'__main__','__file__':core}
 with contextlib.redirect_stdout(io.StringIO()):
  try: exec(compile(payload['artifact-leases.py'],core,'exec'),scope)
  except SystemExit as e:
   if e.code not in (None,0): raise
 print((output/'report.json').read_text())
'''
    expected = {**node, 'name': name, 'flags': (['--apply'] if apply else []) + (['--enroll'] if enroll else [])}
    args = ['python3', '-c', wrapper, json.dumps(expected)]
    if node['transport'] == 'ssh':
        args = SSH + [node['host'], shlex.join(args)]
    payload = {'artifact-leases.py': source,
               'worktree-reaper.py': (ROOT / 'scripts/worktree-reaper.py').read_text()}
    return json.loads(run(args, json.dumps(payload)))


def pressure(node):
    if node['transport'] == 'local':
        st = os.statvfs(node['pressure_path'])
        return st.f_bavail * 100 / st.f_blocks
    if node['transport'] == 'ssh':
        command = "python3 -c " + shlex.quote(
            'import os,socket,getpass; assert socket.gethostname()==' + repr(node['hostname']) +
            ' and getpass.getuser()==' + repr(node['user']) +
            '; s=os.statvfs(' + repr(node['pressure_path']) + '); print(s.f_bavail*100/s.f_blocks)')
        return float(run(SSH + [node['host'], command]))
    serial = native_transport(node)
    rows = run([ADB, '-s', serial, 'shell', 'df -Pk /data/local/tmp']).splitlines()
    fields = rows[-1].split()
    return int(fields[3]) * 100 / int(fields[1])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=ROOT / 'config/fleet/artifact-leases.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--enroll', action='store_true')
    p.add_argument('--monitor', action='store_true')
    a = p.parse_args()
    if not a.output.is_absolute():
        p.error('--output must be absolute')
    config = json.loads(a.config.read_text())
    a.output.mkdir(parents=True, exist_ok=True)
    with (a.output / 'controller.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return 0
        source = (ROOT / 'scripts/artifact-leases.py').read_text()
        failed = False
        for name, node in config['nodes'].items():
            state = a.output / (name + '.last-run')
            try:
                free = pressure(node)
                due = not state.exists() or time.time() - state.stat().st_mtime >= config['hourly_seconds']
                pressured = free < config['pressure_free_percent']
                if a.monitor and not due and not pressured:
                    continue
                result = execute(name, node, a.apply, a.enroll, source)
                result['controller'] = {'node': name, 'free_percent': free, 'pressure': pressured,
                                        'threshold_basis': config['pressure_threshold_basis']}
                target = a.output / (name + '.json')
                temp = target.with_suffix('.tmp')
                temp.write_text(json.dumps(result, indent=2) + '\n')
                temp.replace(target)
                state.touch()
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
                failed = True
                (a.output / (name + '.error.json')).write_text(json.dumps({'node': name, 'error': str(e), 'time': time.time()}))
        return int(failed)


if __name__ == '__main__':
    sys.exit(main())
