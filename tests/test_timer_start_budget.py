"""Planned starts per hour of the tracked user timers must not grow (F16 start budget).

2026-11-16: F16 slowed the old 1-min timers, then new units landed at 1-2 min and took user
starts from ~700 back to ~1,041/h. Nothing counted cadence at review time, so this does.
Adding a fast timer means slowing another one, or raising BUDGET with the owner's reason.
"""
import re
import subprocess
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / 'config/systemd/user'
# 843 -> 848 (2026-11-16): adopting astra-drain.timer.d/pace.conf, a live untracked 2 min poll (30/h), at 10 min (6/h).
BUDGET = 750  # starts/h over every tracked .timer (+ timer.d drop-ins); untracked live timers: home sysgraph timer_starts_h
SPAN = {'us': 1e-6, 'ms': 1e-3, 's': 1, 'sec': 1, 'm': 60, 'min': 60, 'h': 3600, 'hr': 3600, 'd': 86400, 'w': 604800}
REPEAT = re.compile(r'^(OnUnit(?:Active|Inactive)Sec|OnCalendar)=(.*)$', re.M)


def seconds(span):
    span = span.strip()
    if re.fullmatch(r'[\d.]+', span):
        return float(span)
    return sum(float(n) * SPAN[u] for n, u in re.findall(r'([\d.]+)\s*(us|ms|sec|min|hr|s|m|h|d|w)\b', span))


def per_day(expr):
    out = subprocess.run(['systemd-analyze', 'calendar', '--iterations=1500', expr],
                         capture_output=True, text=True, timeout=20).stdout
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    times = re.findall(r'\(in UTC\): \w+ (\S+ \S+) UTC', out)
    return sum(1 for t in times if (datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S') - now).total_seconds() <= 86400)


def timer_rate(path):
    """Starts/h of one timer: its repeat and calendar lines, drop-ins applied (an empty value resets)."""
    keys = {'OnUnitActiveSec': [], 'OnUnitInactiveSec': [], 'OnCalendar': []}
    for f in [path, *sorted(path.with_name(path.name + '.d').glob('*.conf'))]:
        for key, value in REPEAT.findall(f.read_text()):
            keys[key] = keys[key] + [value] if value.strip() else []
    rate = sum(3600 / seconds(v) for k in ('OnUnitActiveSec', 'OnUnitInactiveSec') for v in keys[k] if seconds(v))
    return rate + sum(per_day(v.strip()) / 24 for v in keys['OnCalendar'])


def test_tracked_timers_stay_inside_the_start_budget():
    rates = sorted(((timer_rate(p), p.name) for p in UNITS.glob('*.timer')), reverse=True)
    total = round(sum(r for r, _ in rates))
    top = ', '.join(f'{n} {r:.0f}/h' for r, n in rates[:8])
    assert total <= BUDGET, f'planned timer starts {total}/h > budget {BUDGET}/h; top: {top}'


def test_rate_reads_spans_calendars_and_dropin_resets(tmp_path):
    t = tmp_path / 'x.timer'
    t.write_text('[Timer]\nOnUnitActiveSec=60\nOnCalendar=*-*-* *:00/15:00\n')
    assert round(timer_rate(t)) == 64
    (tmp_path / 'x.timer.d').mkdir()
    (tmp_path / 'x.timer.d/pace.conf').write_text('[Timer]\nOnUnitActiveSec=\nOnUnitActiveSec=1h 30min\n')
    assert round(timer_rate(t), 2) == round(4 + 1 / 1.5, 2)


def test_recurring_timers_do_not_use_on_active_sec():
    # Every user daemon-reload re-fires OnActiveSec (probe 2026-11-16: reload + 20 s); with ~170 reloads a day
    # that was ~7 extra starts/h per timer. OnBootSec fires at once when started after boot and survives reloads.
    # One-shot and debounce timers (no repeat line) keep OnActiveSec.
    bad = []
    for p in UNITS.glob('*.timer'):
        text = ''.join(f.read_text() for f in [p, *sorted(p.with_name(p.name + '.d').glob('*.conf'))])
        if re.search(r'^OnActiveSec=\S', text, re.M) and REPEAT.search(text):
            bad.append(p.name)
    assert not bad, f'recurring timers re-fired by every daemon-reload: {sorted(bad)}'
