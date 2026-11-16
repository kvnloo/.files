"""gh-feedback-watch: the 60 s poll must never queue behind the slow followups command.

2026-11-15: `followups` held the one shared lock for 20+ min while its model call hung on a
router address that no longer existed, so 318 polls in 3 days died at their 240 s limit."""
import fcntl
import importlib.machinery
import importlib.util
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/gh-feedback-watch"


def load(tmp_path, monkeypatch):
    loader = importlib.machinery.SourceFileLoader("gh_feedback_watch", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    monkeypatch.setattr(mod, "DIR", tmp_path)
    return mod


def finishes(fn, secs=3.0) -> bool:
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    t.join(secs)
    return not t.is_alive()


def test_poll_runs_while_followups_holds_its_lock(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    ran = []
    monkeypatch.setattr(mod, "cmd_poll", lambda: ran.append("poll"))
    monkeypatch.setattr(mod, "cmd_followups", lambda: ran.append("followups"))
    mod.main(["followups"])  # creates whichever lock followups uses
    held = [p for p in tmp_path.iterdir() if p.name.endswith(".lock")]
    assert held, "followups takes a lock"
    with open(held[0], "w") as f:  # a long followups run in progress
        fcntl.flock(f, fcntl.LOCK_EX)
        assert finishes(lambda: mod.main(["poll"])), "poll waited on the followups lock"
    assert ran == ["followups", "poll"]


def test_two_polls_still_serialise(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "cmd_poll", lambda: None)
    mod.main(["poll"])
    with open(tmp_path / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        assert not finishes(lambda: mod.main(["poll"]), 0.5), "timer and manual polls must not interleave"


def test_free_pool_comes_from_the_live_checkout():
    """The side worktree it imported from kept a dead ClusterIP after the k3s rebuild."""
    text = SCRIPT.read_text()
    assert "z0int-vllm-sr-turbo" not in text
    assert "/mnt/zer0models/z0-wt/z0int-sr-lanes/deploy/vllm-sr" in text


def test_followups_skips_a_line_poll_is_still_appending(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    log = tmp_path / "feedback.jsonl"
    log.write_text('{"repo": "x/y", "number": 1, "at": "2026-11-15T00:00:00Z", "author": "a"}\n{"repo": "x/')
    monkeypatch.setattr(mod, "LOG", log)
    monkeypatch.setattr(mod, "FU_SEEN", tmp_path / "seen.json")
    monkeypatch.setattr(mod, "FU_UP", "none/none")  # no row matches: no API or model calls
    import sys, types
    monkeypatch.setitem(sys.modules, "free_pool", types.SimpleNamespace(FAST=[], fanout=None))
    mod.cmd_followups()  # must not raise on the torn last line
