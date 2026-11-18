"""offsite-blobs runs as its own unit (offsite-sync was removed 11-18: it snapshotted dirty trees into git)."""
import configparser
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"


def _unit(name):
    p = configparser.ConfigParser(strict=False, interpolation=None)
    p.optionxform = str
    p.read_string((UNITS / name).read_text())
    return p


def test_blobs_unit_stands_alone():
    assert not (UNITS / "offsite.service").exists()
    assert "offsite-blobs" in _unit("offsite-blobs.service")["Service"]["ExecStart"]
    assert _unit("offsite-blobs.timer")["Timer"]["Persistent"] == "true"
    assert _unit("offsite-blobs.timer")["Install"]["WantedBy"] == "timers.target"
