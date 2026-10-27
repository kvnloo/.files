#!/usr/bin/env python3
"""Test the native Netdata health evaluator, then remove the owned test alarm."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

NAME = 'infrastructure_install_notification_test'
PATH = Path('/etc/netdata/health.d/infra-monitor-notification-test.conf')
CONFIG = '''# Owned transient acceptance alarm: infra-monitor
alarm: infrastructure_install_notification_test
on: system.cpu
every: 5s
calc: 1
warn: $this > 0
units: test
to: sysadmin
info: Approved infrastructure monitoring notification test; no real fault
'''


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run through the coordinated root deployment entrypoint.')
    # Never replace a user's existing health file or follow a symlink.
    if PATH.exists() or PATH.is_symlink():
        if PATH.is_symlink() or PATH.stat().st_uid != 0 or PATH.read_text() != CONFIG:
            raise RuntimeError('Preexisting test-alarm path is not an owned probe file')
        PATH.unlink()
    fd = os.open(PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(CONFIG)
            out.flush()
            os.fsync(out.fileno())
        subprocess.run(['netdatacli', 'reload-health'], check=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen('http://127.0.0.1:19999/api/v1/alarms?all', timeout=5) as response:
                    alarms = json.load(response).get('alarms', {})
            except OSError:
                # Activation can precede the local API listener; never fabricate an alarm.
                time.sleep(1)
                continue
            for alarm in alarms.values():
                if alarm.get('name') == NAME and alarm.get('status') == 'WARNING':
                    print(json.dumps({'native_alert': NAME, 'status': 'WARNING',
                                      'chart': alarm.get('chart'), 'host': os.uname().nodename}))
                    return
            time.sleep(1)
        raise RuntimeError('Native health evaluator did not enter WARNING within 60 seconds')
    finally:
        PATH.unlink()
        subprocess.run(['netdatacli', 'reload-health'], check=True)


if __name__ == '__main__':
    main()
