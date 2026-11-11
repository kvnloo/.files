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


def test_crashloop_pods(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch)
    now = time.time()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    def pod(ns, name, restarts, waiting=None, ended=None, code=137, reason="Error"):
        last = {"terminated": {"exitCode": code, "reason": reason, "finishedAt": iso(ended)}} if ended else {}
        return {"metadata": {"namespace": ns, "name": name}, "status": {"containerStatuses": [
            {"name": "c", "restartCount": restarts, "state": {"waiting": {"reason": waiting}} if waiting else {"running": {}},
             "lastState": last}]}}
    pods = {"items": [pod("local-llm", "qwen", 135, ended=now - 60),             # flapping, Running now
                      pod("a", "backoff", 2, waiting="CrashLoopBackOff", ended=now - 30, code=1),
                      pod("b", "old-restarts", 813, ended=now - 7200),         # quiet for 2 h
                      pod("c", "healthy", 0),
                      pod("d", "oom", 9, ended=now - 10, reason="OOMKilled")]}
    got = {x["pod"]: x for x in m.crashloop_pods(pods, now)}
    assert set(got) == {"local-llm/qwen", "a/backoff", "d/oom"}
    assert got["local-llm/qwen"]["cause"].startswith("SIGKILL from outside")
    assert got["d/oom"]["cause"] == "container memory limit"
    assert m.crashloop_pods(None, now) is None


def test_listen_addr():
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("mh2", str(ROOT / "scripts/mesh-healer"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("mh2", loader)); loader.exec_module(mod)
    assert mod.listen_addr("{ path=/x ; argv[]=/x --host 100.1.2.3 --port 11530 -t 4 ; }") == ("100.1.2.3", 11530)
    assert mod.listen_addr("argv[]=/x -m y --port 11531") == ("127.0.0.1", 11531)
    assert mod.listen_addr("argv[]=/x -m y") is None


def test_evict_only_idle_model_servers_after_two_ticks(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch)
    cpu = {"z0-farm-llama.service": 10**9, "busy-llama.service": 10**9, "young-llama.service": 10**9}
    up = {"young-llama.service": 9_800}
    def props(name, *p):
        return {"ActiveState": "active", "CPUUsageNSec": str(cpu[name]),
                "ActiveEnterTimestampMonotonic": str(int(up.get(name, 1) * 1e6)),
                "ExecStart": "argv[]=/llama-server --host 127.0.0.1 --port 11530"}
    monkeypatch.setattr(m, "unit_props", props)
    gap = {"slos": [{"name": "gpu_busy_when_vram_held", "met": False}], "gpu_holders": [
        {"pid": 1, "vram_mib": 300, "unit": "z0-farm-llama.service", "slice": "model-servers.slice"},
        {"pid": 2, "vram_mib": 4000, "unit": "busy-llama.service", "slice": "model-servers.slice"},
        {"pid": 3, "vram_mib": 5000, "unit": "young-llama.service", "slice": "model-servers.slice"},
        {"pid": 4, "vram_mib": 9000, "unit": "neuroskill-daemon.service", "slice": "app.slice"},
        {"pid": 5, "vram_mib": 4600, "unit": None, "slice": "kubepods-burstable.slice"}]}
    state = {}
    m.gpu_idle_ticks(gap, state)
    assert m.plan_evict(gap, state, now_mono=10_000) == []        # tick 1: no CPU baseline, 1 idle tick
    cpu["busy-llama.service"] += 30 * 10**9                       # busy one served requests
    m.gpu_idle_ticks(gap, state)
    acts = m.plan_evict(gap, state, now_mono=10_300)
    assert [a["unit"] for a in acts] == ["z0-farm-llama.service"]
    assert acts[0]["cmds"] == [["stop", "z0-farm-llama.service"]]
    assert acts[0]["wake"] == {"host": "127.0.0.1", "port": 11530}
    ok = {"slos": [{"name": "gpu_busy_when_vram_held", "met": True}], "gpu_holders": gap["gpu_holders"]}
    m.gpu_idle_ticks(ok, state)
    assert state["gpu_idle_ticks"] == 0 and m.plan_evict(ok, state, now_mono=10_600) == []


def test_wake_listener_starts_unit_on_first_connection(tmp_path, monkeypatch):
    import socket, threading
    m = load(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(m, "sh", lambda *a, **k: (calls.append(a), (0, "inactive\n"))[1])
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    t = threading.Thread(target=m.wake_listen, args=("x.service", "127.0.0.1", port, 0.2)); t.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close(); break
        except OSError:
            time.sleep(0.05)
    t.join(5)
    assert not t.is_alive()
    assert ("systemctl", "--user", "--no-block", "start", "x.service") in calls
    rec = json.loads(next((tmp_path / "out/receipts").glob("*-wake.json")).read_text())
    assert rec["unit"] == "x.service" and rec["start_rc"] == 0
