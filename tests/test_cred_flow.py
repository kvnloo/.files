"""cred-flow (oss-factory #318): repeated requests reuse the pending device code."""
import os, subprocess, time
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parents[1] / "scripts/cred-flow")
def fake(marker):
    return ["bash", "-c", 'echo "! First copy your one-time code: $(date +%N | cut -c1-4)-AB12"; '
            'echo "Open this URL to continue: https://github.com/login/device"; sleep 30; : ' + marker]


def run(state, *args):
    env = dict(os.environ, CRED_FLOW_STATE=str(state))
    return subprocess.run([SCRIPT, *args], env=env, capture_output=True, text=True, timeout=30)


def flows(state):
    """Flows started = `script` launchers whose command carries this test's marker."""
    r = subprocess.run(["pgrep", "-fc", f"^script -qfec .*{state}"], capture_output=True, text=True)
    return int(r.stdout or 0)


def kill(state):
    pid = (state / "gh" / "pid").read_text()
    subprocess.run(["kill", "--", f"-{pid}"])


def test_three_calls_one_flow_same_code(tmp_path):
    outs = [run(tmp_path, "gh", "--", *fake(str(tmp_path))) for _ in range(3)]
    try:
        assert [o.returncode for o in outs] == [0, 0, 0]
        codes = {o.stdout.split("code ")[-1].strip() for o in outs}
        assert len(codes) == 1, outs
        assert "new flow" in outs[0].stdout and all("reused" in o.stdout for o in outs[1:])
        assert flows(tmp_path) == 1
    finally:
        kill(tmp_path)


def test_expired_flow_is_replaced(tmp_path):
    first = run(tmp_path, "gh", "--ttl", "1", "--", *fake(str(tmp_path)))
    time.sleep(1.5)
    second = run(tmp_path, "gh", "--ttl", "1", "--", *fake(str(tmp_path)))
    try:
        assert "new flow" in first.stdout and "new flow" in second.stdout
        assert first.stdout.split("code ")[-1] != second.stdout.split("code ")[-1]
    finally:
        kill(tmp_path)


def test_usage(tmp_path):
    assert run(tmp_path, "gh").returncode == 2
