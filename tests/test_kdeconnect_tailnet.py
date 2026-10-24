from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "kdeconnect-tailnet.py"


def load_module():
    spec = spec_from_file_location("kdeconnect_tailnet", SCRIPT)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_configure_writes_qsettings_root_keys_without_ini_group(tmp_path, monkeypatch):
    module = load_module()
    config = tmp_path / "kdeconnect" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("keyAlgorithm=EC\nname=workstation\n")
    monkeypatch.setattr(module, "CONFIG", config)
    monkeypatch.setattr(module, "tailnet_ipv4", lambda: ["100.64.0.2", "100.64.0.3"])

    assert module.configure() == 2
    assert config.read_text() == (
        "customDevices=100.64.0.2,100.64.0.3\n"
        "keyAlgorithm=EC\n"
        "name=workstation\n"
    )
    assert config.stat().st_mode & 0o777 == 0o600
