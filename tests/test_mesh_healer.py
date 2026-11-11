import importlib.machinery
import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("MESH_HEALER_DIR", str(tmp_path / "out"))
    loader = importlib.machinery.SourceFileLoader("mesh_healer", str(ROOT / "scripts/mesh-healer"))
    spec = importlib.util.spec_from_loader("mesh_healer", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def unit(name, result="exit-code", age=7200, trig=(), cpu=10**8, io="3"):
    return {"unit": name, "result": result, "triggered_by": list(trig), "age_s": age, "cpu_ns": cpu,
            "io_class": io, "timeout": "2min"}


def test_plan_is_allowlisted_and_bounded(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch)
    units = [unit("host-optimizer.path"),
             unit("host-optimizer.service", "timeout", age=900, trig=["host-optimizer.path"]),
             unit("night-filter.service", trig=["night-filter.timer"]),
             unit("orphan.service"),                      # no trigger: report, never touch
             unit("young.service", age=60, trig=["x.timer"]),
             unit("cpu-bound.service", "timeout", cpu=60 * 10**9, trig=["x.timer"], age=4000)]
    units += [unit(f"service-watch-failure@u{i}.service.service", "timeout") for i in range(20)]
    acts = m.plan({"failed_units": units, "io_full_avg300": 20.0})
    kinds = {a["unit"]: a["kind"] for a in acts}
    assert len(acts) == m.MAX_ACTIONS
    assert kinds["host-optimizer.path"] == "restart_trigger"
    assert kinds["host-optimizer.service"] == "runtime_timeout_dropin"
    assert "IOSchedulingClass=best-effort" in next(a for a in acts if a["unit"] == "host-optimizer.service")["dropin"]
    assert "orphan.service" not in kinds and "young.service" not in kinds
    allowed = {("reset-failed",), ("start",), ("daemon-reload",)}
    for a in acts:
        for c in a["cmds"]:
            assert (c[0],) in allowed
            if c[0] == "start":
                assert c[1].endswith((".path", ".timer"))


def test_timeout_dropin_needs_io_pressure_and_is_once(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch)
    u = [unit("slow.service", "timeout", trig=["slow.timer"])]
    assert m.plan({"failed_units": u, "io_full_avg300": 2.0})[0]["kind"] == "reset_failed"
    d = tmp_path / "run/systemd/user/slow.service.d"
    d.mkdir(parents=True)
    (d / "60-mesh-healer.conf").write_text("x")
    assert m.plan({"failed_units": u, "io_full_avg300": 30.0})[0]["kind"] == "reset_failed"


def test_measure_unknown_is_none_not_zero(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "SNAPSHOT", tmp_path / "missing.json")
    monkeypatch.setattr(m, "LEDGER", tmp_path / "missing.jsonl")
    monkeypatch.setattr(m, "sh", lambda *a, **k: (1, ""))
    s = {x["name"]: x for x in m.measure()["slos"]}
    assert s["capacity_snapshot_fresh"]["met"] is False
    assert s["groot_mem_available_gb"]["value"] is None and s["groot_mem_available_gb"]["met"] is None
    assert s["kueue_pending_over_30m"]["value"] is None
    assert s["phone_keep_revert_share"]["value"] is None


def test_measure_reads_snapshot_and_ledger(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch)
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"generated_at": time.time(), "hosts": [{"label": "groot", "resources": {
        "ram_available_bytes": 1 * 2**30, "gpus": [{"memory_total_bytes": 100, "memory_free_bytes": 20,
                                                     "utilization_pct": 0.0, "name": "g"}]}}]}))
    led = tmp_path / "l.jsonl"
    led.write_text("\n".join(json.dumps({"device": d, "decision": x}) for d, x in
                             [("s25", "KEEP"), ("s22", "NOISE"), ("tab", "REVERT"), ("groot-gpu", "NOISE")]))
    monkeypatch.setattr(m, "SNAPSHOT", snap)
    monkeypatch.setattr(m, "LEDGER", led)
    monkeypatch.setattr(m, "sh", lambda *a, **k: (1, ""))
    s = {x["name"]: x for x in m.measure()["slos"]}
    assert s["groot_mem_available_gb"]["met"] is False
    assert s["gpu_busy_when_vram_held"]["met"] is False
    assert s["phone_keep_revert_share"]["value"] == round(2 / 3, 3)
