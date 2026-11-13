import importlib.machinery
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'scripts/unit-allowlist'
loader = importlib.machinery.SourceFileLoader('unit_allowlist', str(path))
spec = importlib.util.spec_from_loader("unit_allowlist", loader)
assert spec
ua = importlib.util.module_from_spec(spec)
loader.exec_module(ua)


def test_comments_and_globs(tmp_path):
    f = tmp_path / 'allow'
    f.write_text('# header\nhermes-gateway.service  # core\ngit-maintenance@*.timer\n\n')
    pats = ua.load_allow(f)
    assert pats == ['hermes-gateway.service', 'git-maintenance@*.timer']
    units = {'hermes-gateway.service', 'git-maintenance@daily.timer', 'astra-drain.timer'}
    assert ua.undeclared(units, pats) == ['astra-drain.timer']


def test_report_never_acts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ua, 'live_units', lambda: ({'a.service', 'b.timer'}, {'b.timer'}))
    monkeypatch.setattr(ua, 'systemctl', lambda *a: calls.append(a) or '')
    allow = tmp_path / 'allow'
    allow.write_text('a.service\n')
    monkeypatch.setattr('sys.argv', ['unit-allowlist', '--allow', str(allow)])
    assert ua.main() == 1
    assert calls == []
    monkeypatch.setattr('sys.argv', ['unit-allowlist', '--allow', str(allow), '--enforce'])
    assert ua.main() == 1
    assert ('disable', 'b.timer') in calls and ('stop', 'b.timer') in calls
