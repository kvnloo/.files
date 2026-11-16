import importlib.machinery
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
classify = importlib.machinery.SourceFileLoader(
    'agent_classify_loop', str(ROOT / 'scripts/agent-resource-classify')).load_module()


class Stop(Exception):
    pass


def run(results, max_failures=3):
    seq = iter(results)

    def tick():
        r = next(seq)
        if isinstance(r, BaseException):
            raise r

    sleeps = []

    def sleep(_):
        sleeps.append(1)
        if len(sleeps) >= len(results):
            raise Stop

    try:
        return classify.loop(tick, sleep, 0, max_failures), len(sleeps)
    except Stop:
        return None, len(sleeps)


def test_isolated_tick_failures_keep_the_loop_running():
    rc, ticks = run([SystemExit('boom'), None, RuntimeError('x'), None, None])
    assert rc is None and ticks == 5


def test_consecutive_failures_end_the_loop_so_onfailure_reports_it():
    rc, ticks = run([SystemExit('a'), SystemExit('b'), SystemExit('c'), None])
    assert rc == 1 and ticks == 2


def test_unit_is_resident_and_has_no_timer():
    unit = (ROOT / 'config/systemd/user/agent-resource-classify.service').read_text()
    assert 'Type=simple' in unit and '--loop' in unit and 'Restart=always' in unit
    assert not (ROOT / 'config/systemd/user/agent-resource-classify.timer').exists()
    assert '"~/.config/systemd/user/agent-resource-classify.timer"' in (ROOT / 'config/host/groot.toml').read_text()


def test_former_subminute_timers_stay_at_two_minutes_or_slower():
    import re
    for name in ('quackles-arbiter.timer', 'dash-turbo-follow.timer'):
        text = (ROOT / 'config/systemd/user' / name).read_text()
        for value in re.findall(r'^OnUnit(?:Active|Inactive)Sec=(\S+)', text, re.M):
            assert value.endswith('min') and int(value[:-3]) >= 2, (name, value)
    assert '"~/.config/systemd/user/dash-turbo-follow.timer"' in (ROOT / 'config/host/groot.toml').read_text()
