import importlib.machinery
import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/memory-recall-check"


def load():
    loader = importlib.machinery.SourceFileLoader("memory_recall_check", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def fake_run(payload, seen):
    def run(cmd, **kw):
        seen.update(kw["env"])
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
    return run


def test_unavailable_ctx_fails_instead_of_passing_blind(monkeypatch):
    mod = load()
    seen = {}
    monkeypatch.setattr(mod.subprocess, "run", fake_run({"ok": True, "unresolved": [], "ctx": "unavailable"}, seen))
    out = mod.source_coverage()
    assert out["ok"] is False
    assert any("ctx unavailable" in u for u in out["unresolved"])
    assert seen["PATH"].split(":")[0] == str(mod.HOME / ".local/bin")


def test_available_ctx_keeps_the_z0int_verdict(monkeypatch):
    mod = load()
    monkeypatch.setattr(mod.subprocess, "run", fake_run({"ok": True, "unresolved": [], "ctx": "22 roots"}, {}))
    assert mod.source_coverage()["ok"] is True
