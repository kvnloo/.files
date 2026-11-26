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


def test_incoming_sets_every_paired_device_and_keeps_other_keys(tmp_path, monkeypatch):
    module = load_module()
    root = tmp_path / "kdeconnect"
    (root / "e899270776ad459aafb65eefeeab1001/kdeconnect_share").mkdir(parents=True)
    (root / "e899270776ad459aafb65eefeeab1001/kdeconnect_share/config").write_text("other=1\n")
    (root / "0123456789abcdef0123456789abcdef").mkdir()
    (root / "not-a-device").mkdir()
    monkeypatch.setattr(module, "CONFIG", root / "config")
    incoming = tmp_path / "Recvd"

    assert module.set_incoming(incoming) == 2
    assert incoming.is_dir()
    first = root / "e899270776ad459aafb65eefeeab1001/kdeconnect_share/config"
    assert first.read_text() == f"incoming_path={incoming}\nother=1\n"
    assert (root / "0123456789abcdef0123456789abcdef/kdeconnect_share/config").read_text() == f"incoming_path={incoming}\n"
    assert not (root / "not-a-device/kdeconnect_share").exists()
