"""The global restart backoff must not shorten a unit's own RestartSec.

service.d/52-restart-backoff.conf sets RestartMaxDelaySec=2min for every user service. systemd resets a
longer RestartSec down to that cap, so units built to wait 5-15 min between restarts silently restarted
every 2 min (2026-11-16: srfree-v3-a0, srfree-v3-a0eval, graphrag-index). A tracked unit that declares a
longer RestartSec needs a drop-in sorting after 52 that raises RestartMaxDelaySec to at least that delay.
"""
import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / 'config/systemd/user'
SPAN = {'': 1, 's': 1, 'sec': 1, 'min': 60, 'h': 3600}


def seconds(v):
    return sum(float(n) * SPAN[u] for n, u in re.findall(r'([\d.]+)\s*(min|sec|s|h|)', v.strip()) if n)


def last(key, files):
    vals = [m for f in files for m in re.findall(rf'(?m)^{key}=(.*)$', f.read_text())]
    return vals[-1] if vals else None


def test_long_restart_delays_survive_the_global_backoff_cap():
    cap = seconds(last('RestartMaxDelaySec', [UNITS / 'service.d/52-restart-backoff.conf']))
    bad = []
    for unit in sorted(UNITS.glob('*.service')):
        own = last('RestartSec', [unit])
        if not own or seconds(own) <= cap:
            continue
        later = sorted(f for f in unit.with_name(unit.name + '.d').glob('*.conf') if f.name > '52-restart-backoff.conf')
        mx = last('RestartMaxDelaySec', later)
        if mx is None or seconds(mx) < seconds(own):
            bad.append(f'{unit.name} RestartSec={own}')
    assert not bad, f'global cap {cap:.0f}s clips: {bad}'
