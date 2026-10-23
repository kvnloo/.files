"""Read-only fleet z0 intent/health contract (pytest, no subprocess execution)."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fleet_z0_health", ROOT / "scripts/iac/z0_health.py")
plan = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plan)


@pytest.fixture
def fleet():
    return plan.load_toml(ROOT / "fleet.toml")


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "fleet.toml"
    path.write_text("schema = 1\n")
    return path


def test_aliases_and_exact_profile_desired(fleet):
    for hostname in ("0", "groot", "desktop"):
        assert plan.resolve_host(fleet, hostname)[0] == "desktop"
        for profile in ("clean", "default", "chiefstaff"):
            assert plan.z0_components_for(fleet, hostname, "hermes", profile) == [
                "tencentdb-memory", "z0intelligence"
            ]
        assert plan.z0_components_for(fleet, hostname, "hermes", "unlisted") is None
        for harness in ("claude", "codex", "omp"):
            assert plan.z0_components_for(fleet, hostname, harness) == []
    for hostname in ("mbp", "phone", "omarchy-phone"):
        for harness in ("hermes", "claude", "codex", "omp"):
            assert plan.z0_components_for(fleet, hostname, harness, "clean") == []


def test_unknown_empty_and_profile_override():
    fleet = {"hosts": {"desktop": {
        "match_hostnames": ["0", "groot"],
        "z0_components": {"components": ["ctx"], "harnesses": {
            "hermes": {"components": [], "profiles": {
                "clean": {"components": ["z0intelligence"]}
            }},
            "claude": {},
        }}
    }}}
    assert plan.z0_components_for(fleet, "0", "hermes", "clean") == ["z0intelligence"]
    assert plan.z0_components_for(fleet, "groot", "hermes", "chiefstaff") == []
    assert plan.z0_components_for(fleet, "desktop", "claude") == ["ctx"]
    del fleet["hosts"]["desktop"]["z0_components"]["components"]
    assert plan.z0_components_for(fleet, "desktop", "claude") is None
    assert plan.z0_components_for({"hosts": {"x": {"match_hostnames": []}}}, "x", "omp") is None


def test_invalid_selection_and_harness_fail_closed():
    base = {"hosts": {"x": {"z0_components": {"harnesses": {"claude-code": {"components": []}}}}}}
    with pytest.raises(ValueError):
        plan.z0_components_for(base, "x", "claude")
    base["hosts"]["x"]["z0_components"] = {"components": ["z0intelligence", "z0intelligence"]}
    with pytest.raises(ValueError):
        plan.z0_components_for(base, "x", "omp")
    base["hosts"]["x"]["z0_components"] = {"harnesses": {"codex": {
        "profiles": {"clean": {"components": ["ctx"]}}
    }}}
    with pytest.raises(ValueError):
        plan.z0_components_for(base, "x", "codex")


def test_graphrag_never_desired(fleet):
    for hostname in ("desktop", "mbp", "phone"):
        for harness in ("hermes", "claude", "codex", "omp"):
            for profile in ("global", "clean", "default", "chiefstaff"):
                assert "graphrag" not in (plan.z0_components_for(fleet, hostname, harness, profile) or [])


def test_doctor_command_argv_and_drift_projection(monkeypatch, fleet, manifest):
    monkeypatch.setattr(plan.shutil, "which", lambda _: "/usr/local/bin/z0")
    called = []
    report = {
        "host": "0", "status": "DRIFT",
        "configs": [{"harness": "hermes", "profile": "clean",
                     "status": "DRIFT", "desired": ["z0intelligence", "tencentdb-memory"],
                     "bound": ["ctx", "noop"], "path": "/PRIVATE/secret/config.yaml",
                     "findings": [{"kind": "missing-desired-component",
                                   "component": "z0intelligence",
                                   "reason": "TOP-SECRET-STRING"}]}],
        "findings": [{"kind": "missing-desired-component",
                      "component": "tencentdb-memory", "env": "DO-NOT-EXPOSE"}],
    }

    def fake_run(argv, **opts):
        called.append((argv, opts))
        return subprocess.CompletedProcess(argv, 1, stdout=json.dumps(report), stderr="PRIVATE")

    result = plan.z0_binding_health(
        fleet, manifest, "groot", local_hostname="0", runner=fake_run
    )
    assert len(called) == 1
    argv, options = called[0]
    assert argv == ["/usr/local/bin/z0", "doctor", "--bindings", "--json",
                    "--host-profile", str(manifest.resolve())]
    assert options["timeout"] == 20
    assert options["stdin"] == subprocess.DEVNULL
    assert options["check"] is False
    assert result["status"] == "DRIFT" and not result["healthy"] and result["available"]
    assert result["configs"][0]["configured"] == ["ctx", "noop"]
    assert "PRIVATE" not in json.dumps(result) and "SECRET" not in json.dumps(result)
    assert result["host_id"] == "desktop"


def test_explicit_empty_selection_can_match(monkeypatch, fleet, manifest):
    monkeypatch.setattr(plan.shutil, "which", lambda _: "/usr/bin/z0")
    report = {"host": "mbp", "status": "MATCH", "configs": [
        {"harness": "codex", "profile": "global", "status": "MATCH", "desired": [],
         "bound": [], "findings": []}], "findings": []}
    result = plan.z0_binding_health(
        fleet, manifest, "mbp", local_hostname="mbp",
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
    )
    assert result["status"] == "MATCH" and result["healthy"] and result["available"]


def test_unselected_profile_prevents_global_match(monkeypatch, fleet, manifest):
    monkeypatch.setattr(plan.shutil, "which", lambda _: "/usr/bin/z0")
    report = {"host": "groot", "status": "MATCH", "configs": [
        {"harness": "hermes", "profile": "unlisted", "desired": None,
         "bound": ["ctx"], "findings": []}], "findings": []}
    result = plan.z0_binding_health(
        fleet, manifest, "0", local_hostname="groot",
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
    )
    assert result["status"] == "UNKNOWN" and not result["healthy"] and not result["available"]


def test_no_remote_doctor_and_no_ambiguous_identity(monkeypatch, fleet, manifest):
    def fail_run(*args, **kw):
        raise AssertionError("doctor should never execute")
    assert plan.z0_binding_health(
        fleet, manifest, "mbp", local_hostname="groot", runner=fail_run
    )["reason"] == "remote-host-not-probed"
    unknown = plan.z0_binding_health(
        fleet, manifest, "localhost", local_hostname="groot", runner=fail_run
    )
    assert unknown["status"] == "ERROR" and not unknown["healthy"]


@pytest.mark.parametrize("failure,expected_status,reason", [
    ("missing", "UNKNOWN", "z0-executable-unavailable"),
    ("timeout", "ERROR", "doctor-timeout"),
    ("oserror", "ERROR", "doctor-execution-failed"),
    ("nonzero", "ERROR", "doctor-exit-failure"),
    ("malformed", "ERROR", "doctor-malformed-json"),
    ("wrong-host", "ERROR", "doctor-host-mismatch"),
    ("unknown", "UNKNOWN", "doctor-reported-unknown"),
    ("empty-configs", "ERROR", "doctor-malformed-schema"),
    ("conflict", "ERROR", "doctor-exit-status-conflict"),
])
def test_subprocess_and_schema_fail_closed(
    monkeypatch, fleet, manifest, failure, expected_status, reason
):
    monkeypatch.setattr(plan.shutil, "which", lambda _: None if failure == "missing" else "/bin/z0")

    def runner(argv, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 20)
        if failure == "oserror":
            raise FileNotFoundError()
        if failure == "nonzero":
            return subprocess.CompletedProcess(argv, 7, "failed", "")
        if failure == "malformed":
            return subprocess.CompletedProcess(argv, 0, "NOT-JSON", "")
        data = {"host": "mbp" if failure == "wrong-host" else "groot",
                "status": "UNKNOWN" if failure == "unknown" else "MATCH",
                "configs": [] if failure == "empty-configs" else [
                    {"harness": "omp", "profile": "global",
                     "desired": [], "bound": [], "findings": []}],
                "findings": []}
        return subprocess.CompletedProcess(
            argv, 1 if failure == "conflict" else 0, json.dumps(data), ""
        )

    result = plan.z0_binding_health(
        fleet, manifest, "groot", local_hostname="groot", runner=runner
    )
    assert result["status"] == expected_status
    assert result["reason"] == reason
    assert result["available"] is False and result["healthy"] is False


def test_health_cli_reports_unavailable_without_touching_compute_health(monkeypatch, capsys):
    monkeypatch.setattr(plan, "z0_binding_health", lambda *args: {
        "status": "UNKNOWN", "available": False, "healthy": False,
        "host_id": "mbp", "configs": [], "findings": [], "reason": "z0-executable-unavailable"
    })
    assert plan.main(["--host-profile", str(ROOT / "fleet.toml"), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "UNKNOWN"
    assert not result["healthy"]


def test_disabled_desired_binding_cannot_be_reported_healthy(monkeypatch, fleet, manifest):
    """A disabled server is not a MATCH even if the doctor header is inconsistent."""
    monkeypatch.setattr(plan.shutil, "which", lambda _: "/usr/bin/z0")
    report = {
        "host": "groot", "status": "MATCH",
        "configs": [{
            "harness": "hermes", "profile": "clean", "status": "MATCH",
            "desired": ["tencentdb-memory"], "bound": [],
            "findings": [{
                "kind": "missing-desired-component", "status": "DRIFT",
                "component": "tencentdb-memory", "reason": "disabled",
            }],
        }],
        "findings": [],
    }
    result = plan.z0_binding_health(
        fleet, manifest, "groot", local_hostname="0",
        runner=lambda argv, **opts: subprocess.CompletedProcess(
            argv, 0, json.dumps(report), ""
        ),
    )
    assert result["status"] == "DRIFT"
    assert result["available"] is True and result["healthy"] is False
    assert result["configs"][0]["findings"] == [{
        "kind": "missing-desired-component", "component": "tencentdb-memory", "status": "DRIFT"
    }]


def test_informational_unselected_mismatch_does_not_invent_drift(monkeypatch, fleet, manifest):
    monkeypatch.setattr(plan.shutil, "which", lambda _: "/usr/bin/z0")
    info = {"kind": "binding-mismatch", "component": "ctx", "status": "INFO"}
    report = {"host": "groot", "status": "MATCH", "configs": [
        {"harness": "codex", "profile": "global", "status": "MATCH",
         "desired": [], "bound": [], "findings": [info]}], "findings": [info]}
    result = plan.z0_binding_health(
        fleet, manifest, "groot", local_hostname="groot",
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
    )
    assert result["status"] == "MATCH" and result["healthy"]
    assert result["configs"][0]["findings"][0]["status"] == "INFO"


def test_exact_logical_host_beats_alias_collision():
    fleet = {"hosts": {"mbp": {}, "other": {"match_hostnames": ["mbp"]}}}
    assert plan.resolve_host(fleet, "mbp") == ("mbp", {})


def test_unmanaged_native_server_ids_are_not_registry_ids(monkeypatch, fleet, manifest):
    monkeypatch.setattr(plan.shutil, "which", lambda _: "/usr/bin/z0")
    report = {"host": "groot", "status": "DRIFT", "configs": [
        {"harness": "codex", "profile": "global", "status": "MATCH", "desired": [],
         "bound": ["node_repl", "vendor.archive", "memory.provider:custom"], "findings": []},
        {"harness": "hermes", "profile": "clean", "status": "DRIFT",
         "desired": ["z0intelligence"], "bound": ["ctx"], "findings": []}],
        "findings": []}
    result = plan.z0_binding_health(
        fleet, manifest, "groot", local_hostname="groot",
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 1, json.dumps(report), "")
    )
    assert result["status"] == "DRIFT" and result["available"]
    assert result["configs"][0]["configured"] == report["configs"][0]["bound"]
