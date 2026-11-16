"""A unit with a short deadline must not run in the idle IO class.

On groot's mq-deadline disks an idle-class request waits up to prio_aging_expire
(10 s) whenever best-effort IO is queued. A GPU job streaming weights keeps the
queue non-empty for hours, so every cold read of an idle unit costs ~10 s and a
20 s classifier or a 90 s watchdog dies by timeout (measured 11-15: 9.4 s for a
1 MB idle read vs 0.1 s best-effort). Long scanners may stay idle; they finish.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / 'config/systemd/user'
DEADLINES = ('TimeoutStartSec', 'TimeoutSec', 'WatchdogSec', 'RuntimeMaxSec')
SHORT = 600  # seconds; at ~10 s per starved read a shorter budget cannot be kept
SPAN = {'ms': .001, 's': 1, 'sec': 1, 'min': 60, 'm': 60, 'h': 3600, 'hr': 3600, 'd': 86400}


def seconds(value):
    value = value.strip()
    if value in ('', 'infinity', '0'):
        return None
    if value.isdigit():
        return int(value)
    parts = re.findall(r'(\d+(?:\.\d+)?)\s*([a-z]+)', value)
    assert parts, f'unparsed time span {value!r}'
    return sum(float(n) * SPAN[u] for n, u in parts)


def settings(path):
    text = path.read_text()
    for drop in sorted(path.parent.glob(path.name + '.d/*.conf')):
        text += '\n' + drop.read_text()
    found = {}
    for line in text.splitlines():
        m = re.match(r'(\w+)=(.*)$', line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    return found


def offenders():
    bad = []
    for path in sorted(UNITS.glob('*.service')):
        if not path.is_file():
            continue
        s = settings(path)
        if s.get('IOSchedulingClass', '').strip() not in ('idle', '3'):
            continue
        spans = [seconds(s[k]) for k in DEADLINES if k in s]
        short = [x for x in spans if x is not None and x <= SHORT]
        if short:
            bad.append(f'{path.name} ({min(short):g}s)')
    return bad


def test_seconds():
    assert seconds('20') == 20 and seconds('5min') == 300 and seconds('1min 30s') == 90
    assert seconds('infinity') is None and seconds('1h') == 3600


def test_short_deadline_units_are_not_idle_io():
    assert offenders() == []
