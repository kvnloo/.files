import importlib.machinery, importlib.util, os, stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    loader = importlib.machinery.SourceFileLoader("phone_worker", str(ROOT / "scripts/phone-worker"))
    spec = importlib.util.spec_from_loader("phone_worker", loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_notify_reaches_kevin_push(tmp_path, monkeypatch):
    # 2026-11-16: notify() ran a removed worktree's dash-notify and swallowed the error, so every
    # "S25 worker off" note vanished. kevin-push is the one route to Kevin (11-15: Dash notes are useless).
    seen = tmp_path / "argv"
    push = tmp_path / "kevin-push"
    push.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {seen}\n')
    push.chmod(push.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("KEVIN_PUSH", str(push))
    pw = load()
    pw.notify("S25 worker off", "Worker mode ended")
    assert seen.read_text().splitlines() == ["phone-worker", "S25 worker off", "Worker mode ended"]
    assert "/z0-wt/" not in (ROOT / "scripts/phone-worker").read_text()  # no worktree paths in shipped code
