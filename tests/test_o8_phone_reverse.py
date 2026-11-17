"""o8-phone-reverse: an absent S25 is a finding, not a unit failure (unit-o8-phone-reverse tape)."""
import os, subprocess, tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/o8-phone-reverse"


def run(devices: str, serial: str = ""):
    with tempfile.TemporaryDirectory() as d:
        adb = Path(d) / "adb"
        log = Path(d) / "calls"
        adb.write_text(f"""#!/bin/sh
echo "$@" >> {log}
case "$*" in
  devices) printf 'List of devices attached\\n{devices}' ;;
  *getprop*) echo {serial} ;;
esac
""")
        adb.chmod(0o755)
        env = dict(os.environ, PATH=f"{d}:/usr/bin:/bin", O8_PHONE_SERIALNO="WANT")
        p = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
        return p, log.read_text() if log.exists() else ""


def test_absent_phone_exits_zero_and_logs():
    p, _ = run("")
    assert p.returncode == 0
    assert "not connected over adb" in p.stderr


def test_other_device_is_not_tunneled():
    p, calls = run("10.0.0.9:5555\\tdevice\\n", serial="OTHER")
    assert p.returncode == 0 and "reverse" not in calls


def test_present_phone_gets_both_ports():
    p, calls = run("10.0.0.2:5555\\tdevice\\n", serial="WANT")
    assert p.returncode == 0 and p.stdout.strip() == "ok 10.0.0.2:5555"
    assert "reverse tcp:47100 tcp:47100" in calls and "reverse tcp:47105 tcp:47105" in calls
