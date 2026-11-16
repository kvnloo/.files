import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('failed_unit_watch', str(ROOT / 'scripts/failed-unit-watch'))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec
fuw = importlib.util.module_from_spec(spec)
loader.exec_module(fuw)

SHOW = ("Id=fork.timer\nUnit=fork.service\nSubState=elapsed\nUnitFileState=enabled\n"
        "TimersMonotonic={ OnUnitActiveUSec=1d ; next_elapse=0 }\nTimersMonotonic={ OnBootUSec=20min ; next_elapse=0 }\n\n"
        "Id=dated.timer\nUnit=dated.service\nSubState=elapsed\nUnitFileState=enabled\n"
        "TimersCalendar={ OnCalendar=2026-11-11 07:45:00 ; next_elapse=n/a }\n\n"
        "Id=ok.timer\nUnit=ok.service\nSubState=waiting\nUnitFileState=enabled\n"
        "TimersMonotonic={ OnUnitActiveUSec=6h ; next_elapse=6h }\n\n"
        "Id=off.timer\nUnit=off.service\nSubState=elapsed\nUnitFileState=disabled\n"
        "TimersMonotonic={ OnUnitInactiveUSec=1h ; next_elapse=0 }\n\n"
        "Id=busy.timer\nUnit=busy.service\nSubState=elapsed\nUnitFileState=enabled\n"
        "TimersMonotonic={ OnUnitInactiveUSec=45min ; next_elapse=0 }\n")
SERVICES = "Id=fork.service\nActiveState=inactive\n\nId=busy.service\nActiveState=activating\n"


class FakeSystemctl:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = ""
        if "list-units" in cmd:
            out = "fork.timer loaded active elapsed fork.timer\ndated.timer loaded active elapsed y\nok.timer loaded active waiting z\noff.timer l a e w\nbusy.timer l a e w\n"
        elif "show" in cmd:
            out = SHOW if any(c.endswith(".timer") for c in cmd) else SERVICES
        return subprocess.CompletedProcess(cmd, 0, out, "")


def test_only_enabled_repeating_timers_left_elapsed_with_an_idle_service_are_stalled():
    """busy.timer is elapsed only because its OnUnitInactiveSec service is mid-run: not stalled."""
    run = FakeSystemctl()
    assert fuw.stalled_timers(run) == [("fork.timer", "fork.service")]
    asked = [c for c in run.calls if "show" in c][0]
    assert asked.count("fork.timer") == 1  # a timer without Description must not be listed twice


def test_rearm_starts_the_service_once_without_blocking():
    run = FakeSystemctl()
    fuw.rearm([("fork.timer", "fork.service")], run)
    assert run.calls == [["systemctl", "--user", "start", "--no-block", "fork.service"]]


def test_block_reports_stalled_timers_even_with_no_failed_units():
    out = fuw.block([], 0, 30, "now", stalled=[("fork.timer", "fork.service")])
    assert "fork.timer" in out and "re-armed: started fork.service once" in out
    assert out.startswith(fuw.BEGIN) and out.endswith(fuw.END)
    assert fuw.block([], 0, 30, "now") == ""


TIMED = ("Id=tick.timer\nUnit=tick.service\n\nId=slow.timer\nUnit=slow.service\n\n"
         "Id=capped.timer\nUnit=capped.service\n\nId=idle.timer\nUnit=idle.service\n")
TIMED_SERVICES = (  # now = 10_000 s monotonic
    "Id=tick.service\nActiveState=activating\nInactiveExitTimestampMonotonic=4000000000\nTimeoutStartUSec=infinity\n\n"
    "Id=slow.service\nActiveState=activating\nInactiveExitTimestampMonotonic=9000000000\nTimeoutStartUSec=infinity\n\n"
    "Id=capped.service\nActiveState=activating\nInactiveExitTimestampMonotonic=1000000000\nTimeoutStartUSec=45min\n\n"
    "Id=idle.service\nActiveState=inactive\nInactiveExitTimestampMonotonic=1\nTimeoutStartUSec=infinity\n")


class TimedSystemctl(FakeSystemctl):
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = ""
        if "list-units" in cmd:
            out = "tick.timer l a r w\nslow.timer l a r w\ncapped.timer l a r w\nidle.timer l a w w\n"
        elif "show" in cmd:
            out = TIMED if any(c.endswith(".timer") for c in cmd) else TIMED_SERVICES
        return subprocess.CompletedProcess(cmd, 0, out, "")


def test_timer_service_running_past_the_limit_with_no_timeout_is_reported():
    """11-15: z0int-loop-tick hung 1h+ in one run, so its hourly timer never fired again; nothing failed.
    A unit with a finite TimeoutStartSec is left to systemd; one under the limit is just slow."""
    assert fuw.overrunning(TimedSystemctl(), now_mono=10_000, limit_min=60) == [("tick.service", 100)]


def test_block_reports_overrunning_services_without_acting():
    out = fuw.block([], 0, 30, "now", overrun=[("tick.service", 100)])
    assert "tick.service: activating 100 min" in out and out.startswith(fuw.BEGIN)
