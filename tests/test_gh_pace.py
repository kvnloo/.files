import importlib.machinery
import importlib.util
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_gh_pace(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_PACE_STATE", str(tmp_path / "posture"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = REPO / "scripts" / "gh-pace"
    loader = importlib.machinery.SourceFileLoader("gh_pace", str(path))
    spec = importlib.util.spec_from_loader("gh_pace", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def rate(used, reset=10_000, limit=5000):
    return {"core": {"limit": limit, "remaining": limit - used, "used": used, "reset": reset},
            "graphql": {"limit": 5000, "remaining": 5000, "used": 0, "reset": reset},
            "search": {"limit": 30, "remaining": 30, "used": 0, "reset": reset}}


def test_split_charges_external_with_the_remainder_of_githubs_counter(tmp_path, monkeypatch):
    g = load_gh_pace(tmp_path, monkeypatch)
    rows = [{"t": 1000, "rate": rate(100)},
            {"t": 1120, "rate": rate(400), "core_delta": 300, "ghcache_delta": 50, "host_gh": 20,
             "host_by": {"bash gh api in ~": 20}}]
    r = g.report(rows)
    assert r["split"] == {"total": 300, "ghcache": 50, "host_gh": 20, "external": 230}
    assert r["observed_per_min"] == 150.0
    assert r["window_min"] == 2.0


def test_hold_below_reserve_and_throttle_when_burning_faster_than_sustainable(tmp_path, monkeypatch):
    g = load_gh_pace(tmp_path, monkeypatch)
    held = g.report([{"t": 0, "rate": rate(4600)},
                     {"t": 120, "rate": rate(4700), "core_delta": 100}])
    assert held["band"] == "hold"
    # 3000 left - 500 reserve over 10 min = 250/min sustainable; burning 450/min runs out first.
    hot = g.report([{"t": 9280, "rate": rate(1100)},
                    {"t": 9400, "rate": rate(2000), "core_delta": 900}])
    assert hot["band"] in ("throttle", "hard-throttle")
    assert hot["exhausts_at"] is not None


def test_graphql_porcelain_is_not_counted_against_core(tmp_path, monkeypatch):
    g = load_gh_pace(tmp_path, monkeypatch)
    assert g.pool_of("api", "graphql") == "graphql"
    assert g.pool_of("pr", "view") == "graphql"
    assert g.pool_of("api", "repos/o/r/pulls") == "core"
    assert g.pool_of("run", "list") == "core"
    g.CALLS.parent.mkdir(parents=True)
    g.CALLS.write_text("".join([
        "110\t1\tbash\tapi\trepos/o/r\t/w\n",
        "111\t1\tbash\tpr\tlist\t/w\n",
        "112\t1\tbash\tauth\ttoken\t/w\n",   # free
        "90\t1\tbash\tapi\trepos/o/r\t/w\n",  # before the interval
    ]))
    pools, by = g.host_calls(100, 200)
    assert pools == {"core": 1, "graphql": 1}
    assert by == {"bash gh api in /w": 1}


def test_counter_reset_between_samples_counts_only_the_new_window(tmp_path, monkeypatch):
    g = load_gh_pace(tmp_path, monkeypatch)
    calls = iter([rate(4900, reset=100), rate(30, reset=3700)])
    monkeypatch.setattr(g, "rate_limit", lambda: next(calls))
    monkeypatch.setattr(g, "ghcache_charged", lambda: None)
    g.sample()
    rows = g.sample()
    assert rows[-1]["core_delta"] == 30
    assert json.loads(g.REPORT.read_text())["core"]["used"] == 30


def test_shim_logs_and_passes_arguments_through(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    shim = (REPO / "scripts" / "gh-shim").read_text().replace("/usr/bin/gh", str(fake / "real-gh"))
    (fake / "gh").write_text(shim)
    (fake / "real-gh").write_text("#!/bin/sh\necho \"real:$*\"\n")
    for f in ("gh", "real-gh"):
        (fake / f).chmod(0o755)
    (tmp_path / "state" / "gh-pace").mkdir(parents=True)
    env = dict(os.environ, XDG_STATE_HOME=str(tmp_path / "state"))
    out = subprocess.run([str(fake / "gh"), "api", "repos/o/r", "--jq", ".x y"],
                         capture_output=True, text=True, env=env, cwd=tmp_path, check=True)
    assert out.stdout.strip() == "real:api repos/o/r --jq .x y"
    line = (tmp_path / "state" / "gh-pace" / "calls.tsv").read_text().strip().split("\t")
    assert line[3:] == ["api", "repos/o/r", str(tmp_path)]
