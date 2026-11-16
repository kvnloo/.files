import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / 'config/systemd/user'

STUB = r'''#!/bin/sh
echo "$*" >> "$LOG"
case "$*" in
  *list-units*) printf 'a.service loaded active running A\nb.service loaded active running B\nhermes-web.service loaded active running W\n' ;;
  *show*) printf 'Id=a.service\nMemoryMax=infinity\nMemorySwapMax=infinity\n\nMemoryMax=2G\nId=b.service\nMemorySwapMax=infinity\n\nId=hermes-web.service\nMemorySwapMax=3G\nMemoryMax=infinity\n' ;;
  *set-property*a.service*) exit 1 ;;
esac
'''


def run(tmp_path):
    (tmp_path / 'systemctl').write_text(STUB)
    (tmp_path / 'systemctl').chmod(0o755)
    log = tmp_path / 'log'
    env = dict(os.environ, PATH=f'{tmp_path}:/usr/bin:/bin', LOG=str(log))
    out = subprocess.run([str(ROOT / 'scripts/service-envelope')], env=env,
                         capture_output=True, text=True, timeout=20)
    return out, log.read_text().splitlines()


def test_one_show_for_all_units_and_caps_only_uncapped(tmp_path):
    out, calls = run(tmp_path)
    assert out.returncode == 0, out.stderr
    assert sum('show' in c for c in calls) == 1
    sets = [c for c in calls if 'set-property' in c]
    assert sets == ['--user set-property --runtime a.service MemoryMax=4G MemorySwapMax=1G',
                    '--user set-property --runtime hermes-web.service MemoryMax=10G']


def test_a_unit_that_vanished_does_not_end_the_pass(tmp_path):
    out, _ = run(tmp_path)
    assert 'cap skipped: a.service' in out.stdout and 'cap hermes-web.service' in out.stdout


def test_unit_is_resident_and_has_no_timer():
    unit = (UNITS / 'service-envelope.service').read_text()
    assert 'Type=simple' in unit and '--loop' in unit and 'Restart=always' in unit
    assert 'WantedBy=default.target' in unit and '/home/' not in unit
    assert not (UNITS / 'service-envelope.timer').exists()
