import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('failed_unit_watch', str(ROOT / 'scripts/failed-unit-watch'))
spec = importlib.util.spec_from_loader(loader.name, loader)
fuw = importlib.util.module_from_spec(spec)
loader.exec_module(fuw)

SHOW = ("Id=fork.timer\nUnit=fork.service\nSubState=elapsed\nUnitFileState=enabled\n"
        "TimersMonotonic={ OnUnitActiveUSec=1d ; next_elapse=0 }\nTimersMonotonic={ OnBootUSec=20min ; next_elapse=0 }\n\n"
        "Id=dated.timer\nUnit=dated.service\nSubState=elapsed\nUnitFileState=enabled\n"
        "TimersCalendar={ OnCalendar=2026-11-11 07:45:00 ; next_elapse=n/a }\n\n"
        "Id=ok.timer\nUnit=ok.service\nSubState=waiting\nUnitFileState=enabled\n"
        "TimersMonotonic={ OnUnitActiveUSec=6h ; next_elapse=6h }\n\n"
        "Id=off.timer\nUnit=off.service\nSubState=elapsed\nUnitFileState=disabled\n"
        "TimersMonotonic={ OnUnitInactiveUSec=1h ; next_elapse=0 }\n")


class FakeSystemctl:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = ""
        if "list-units" in cmd:
            out = "fork.timer loaded active elapsed x\ndated.timer loaded active elapsed y\nok.timer loaded active waiting z\noff.timer l a e w\n"
        elif "show" in cmd:
            out = SHOW
        return subprocess.CompletedProcess(cmd, 0, out, "")


def test_only_enabled_repeating_timers_left_elapsed_are_stalled():
    assert fuw.stalled_timers(FakeSystemctl()) == [("fork.timer", "fork.service")]


def test_rearm_starts_the_service_once_without_blocking():
    run = FakeSystemctl()
    fuw.rearm([("fork.timer", "fork.service")], run)
    assert run.calls == [["systemctl", "--user", "start", "--no-block", "fork.service"]]


def test_block_reports_stalled_timers_even_with_no_failed_units():
    out = fuw.block([], 0, 30, "now", stalled=[("fork.timer", "fork.service")])
    assert "fork.timer" in out and "re-armed: started fork.service once" in out
    assert out.startswith(fuw.BEGIN) and out.endswith(fuw.END)
    assert fuw.block([], 0, 30, "now") == ""
