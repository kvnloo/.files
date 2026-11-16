"""offsite-blobs runs as its own unit: chained behind offsite-sync it never ran when the sync was killed."""
import configparser
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"


def _unit(name):
    p = configparser.ConfigParser(strict=False, interpolation=None)
    p.optionxform = str
    p.read_string((UNITS / name).read_text())
    return p


def test_blobs_not_chained_behind_sync():
    sync = (UNITS / "offsite.service").read_text()
    assert "offsite-blobs" not in sync.split("[Service]")[1]
    assert "offsite-blobs" in _unit("offsite-blobs.service")["Service"]["ExecStart"]
    assert _unit("offsite-blobs.timer")["Timer"]["Persistent"] == "true"
    assert _unit("offsite-blobs.timer")["Install"]["WantedBy"] == "timers.target"
