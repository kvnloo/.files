import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "iac" / "collect.py"

spec = importlib.util.spec_from_file_location("iac_collect", MODULE_PATH)
iac = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(iac)


def test_command_inventory_is_observational():
    forbidden = {
        "install", "remove", "enable", "disable", "start", "stop", "restart",
        "mount", "umount", "mkfs", "migrate", "migrate-superblock",
    }
    words = {part for argv in iac.COMMANDS.values() for part in argv}
    assert forbidden.isdisjoint(words)


def test_collector_does_not_serialize_secret_environment(monkeypatch, tmp_path):
    marker = "THIS-MUST-NOT-APPEAR-IN-IAC-OUTPUT"
    monkeypatch.setenv("OPENROUTER_API_KEY", marker)
    monkeypatch.setenv("BWS_ACCESS_TOKEN", marker)

    monkeypatch.setattr(iac, "COMMANDS", {})
    monkeypatch.setattr(iac.Path, "home", classmethod(lambda cls: tmp_path))

    data = iac.collect(tmp_path)
    encoded = json.dumps(data)

    assert marker not in encoded
    assert data["safety"]["secret_values_collected"] is False


def test_default_state_path_is_outside_repo(monkeypatch, tmp_path):
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    out = iac.default_output("groot")
    assert out == state / "dotfiles" / "iac" / "groot" / "observed.json"


def test_write_observed_is_atomic_enough_for_single_writer(tmp_path):
    out = tmp_path / "observed.json"
    payload = {"schema_version": 1, "host": {"hostname": "test"}}
    iac.write_observed(payload, out)
    assert json.loads(out.read_text()) == payload
    assert not out.with_suffix(".json.tmp").exists()
