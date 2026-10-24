"""Python job setup and guest lifetime receipts for the existing fleet executor."""
import json
import shlex
import subprocess


SNAPSHOT = r'''
import json
from pathlib import Path
uptime = float(Path('/proc/uptime').read_text().split()[0])
tracer = int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                  if line.startswith('TracerPid:')))
# Kernel uptime alone does not detect a PRoot guest restart on the same Android boot.
identity = None
if tracer:
    stat = Path('/proc/%s/stat' % tracer).read_text().rsplit(')', 1)[1].split()
    identity = [tracer, stat[19]]
print(json.dumps({'uptime': uptime,
                  'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  'guest_identity': identity, 'pip_cache': str(Path.home() / '.cache/pip')}))
'''

SETUP = r'''
import os
from pathlib import Path
import subprocess
import sys
import time
started = time.monotonic()
venv = Path.cwd().parent / 'venv'
os.environ['PIP_CACHE_DIR'] = sys.argv[1]
os.environ['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
Path(os.environ['PIP_CACHE_DIR']).mkdir(parents=True, exist_ok=True)
subprocess.run(['python3', '-m', 'venv', str(venv)], check=True)
python = str(venv / 'bin/python')
subprocess.run([python, '-m', 'pip', 'install', 'pytest'], check=True)
os.environ['VIRTUAL_ENV'] = str(venv)
os.environ['PATH'] = str(venv / 'bin') + os.pathsep + os.environ['PATH']
print('# venv_setup_seconds=%.3f pip_cache=%s' %
      (time.monotonic() - started, os.environ['PIP_CACHE_DIR']), flush=True)
started = time.monotonic()
rc = subprocess.run(sys.argv[2:]).returncode
print('# command_seconds=%.3f command_exit=%d' % (time.monotonic() - started, rc), flush=True)
sys.exit(rc if rc >= 0 else 128 - rc)
'''


def command(argv, pip_cache):
    return ['python3', '-c', SETUP, pip_cache, *argv]


def snapshot(ssh):
    result = subprocess.run(ssh + ['python3 -c ' + shlex.quote(SNAPSHOT)],
                            capture_output=True, text=True, timeout=30, check=True)
    value = json.loads(result.stdout)
    if not isinstance(value.get('uptime'), (int, float)) or not value.get('boot_id'):
        raise ValueError('guest lifetime telemetry unavailable')
    if not value.get('guest_identity'):
        raise ValueError('PRoot guest identity unavailable')
    return value


def restarted(before, after, elapsed):
    return (before['boot_id'] != after['boot_id']
            or before['guest_identity'] != after['guest_identity']
            or after['uptime'] < before['uptime']
            or after['uptime'] - before['uptime'] + 2 < elapsed)
