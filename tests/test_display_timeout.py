import json
import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "config/noctalia/plugins/monitor-layout/scripts/display-timeout.sh"


def write_fake_hyprcaffeine(tmp_path: Path) -> Path:
    binary = tmp_path / "hyprcaffeine"
    binary.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
state=${FAKE_HYPRCAFFEINE_STATE:?}
case "${1:-}" in
  waybar)
    if [[ -f $state ]]; then class=hc-monitor; else class=hc-off; fi
    printf '{"class":"%s"}\\n' "$class"
    ;;
  monitor)
    case "${2:-}" in
      on) touch "$state" ;;
      off) rm -f "$state" ;;
      *) exit 2 ;;
    esac
    ;;
  *) exit 2 ;;
esac
"""
    )
    binary.chmod(0o755)
    return binary


def write_hypridle_config(tmp_path: Path, timeout: int = 720) -> Path:
    config = tmp_path / "hypridle.conf"
    config.write_text(
        f"""listener {{
  timeout = 300
  on-timeout = brightnessctl -s set 10
}}
listener {{
  timeout = {timeout}
  on-timeout = hyprctl dispatch dpms off
  on-resume = hyprctl dispatch dpms on
}}
"""
    )
    return config


def run_adapter(tmp_path: Path, action: str, *, config: Path | None = None, binary: Path | None = None):
    state = tmp_path / "monitor-state"
    env = os.environ.copy()
    env["HYPRIDLE_CONFIG"] = str(config or write_hypridle_config(tmp_path))
    env["HYPRCAFFEINE_BIN"] = str(binary or write_fake_hyprcaffeine(tmp_path))
    env["FAKE_HYPRCAFFEINE_STATE"] = str(state)
    completed = subprocess.run(
        [str(SCRIPT), action],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.count("\n") == 1
    return completed, json.loads(completed.stdout), state


def test_status_reports_configured_timeout(tmp_path: Path):
    completed, payload, _ = run_adapter(tmp_path, "status")
    assert completed.returncode == 0
    assert payload == {
        "available": True,
        "infinite": False,
        "timeoutSeconds": 720,
        "label": "12m",
        "error": "",
    }


def test_status_reports_monitor_inhibitor_as_infinite(tmp_path: Path):
    binary = write_fake_hyprcaffeine(tmp_path)
    state = tmp_path / "monitor-state"
    state.touch()
    env = os.environ.copy()
    env.update(
        HYPRIDLE_CONFIG=str(write_hypridle_config(tmp_path)),
        HYPRCAFFEINE_BIN=str(binary),
        FAKE_HYPRCAFFEINE_STATE=str(state),
    )
    completed = subprocess.run([str(SCRIPT), "status"], capture_output=True, text=True, env=env)
    payload = json.loads(completed.stdout)
    assert payload["infinite"] is True
    assert payload["label"] == "INF"


def test_enable_and_disable_requery_real_application_state(tmp_path: Path):
    binary = write_fake_hyprcaffeine(tmp_path)
    completed, payload, state = run_adapter(tmp_path, "enable", binary=binary)
    assert completed.returncode == 0
    assert state.exists()
    assert payload["infinite"] is True
    assert payload["label"] == "INF"

    completed, payload, state = run_adapter(tmp_path, "disable", binary=binary)
    assert completed.returncode == 0
    assert not state.exists()
    assert payload["infinite"] is False
    assert payload["label"] == "12m"


def test_unavailable_hyprcaffeine_is_explicit(tmp_path: Path):
    completed, payload, _ = run_adapter(tmp_path, "status", binary=tmp_path / "missing")
    assert completed.returncode != 0
    assert payload["available"] is False
    assert payload["infinite"] is False
    assert payload["label"] == "12m"
    assert "not installed" in payload["error"]


def test_missing_dpms_timeout_is_explicit(tmp_path: Path):
    config = tmp_path / "hypridle.conf"
    config.write_text("listener {\n  timeout = 600\n  on-timeout = loginctl lock-session\n}\n")
    completed, payload, _ = run_adapter(tmp_path, "status", config=config)
    assert completed.returncode != 0
    assert payload["timeoutSeconds"] == 0
    assert payload["label"] == "?"
    assert "DPMS timeout" in payload["error"]


def test_dpms_timeout_parses_when_action_precedes_timeout(tmp_path: Path):
    config = tmp_path / "hypridle.conf"
    config.write_text(
        "listener {\n"
        "  on-timeout = hyprctl dispatch dpms off\n"
        "  timeout = 900\n"
        "}\n"
    )
    completed, payload, _ = run_adapter(tmp_path, "status", config=config)
    assert completed.returncode == 0
    assert payload["timeoutSeconds"] == 900
    assert payload["label"] == "15m"


def test_dpms_timeout_parses_single_line_listener(tmp_path: Path):
    config = tmp_path / "hypridle.conf"
    config.write_text(
        "listener { on-timeout = hyprctl dispatch dpms off; timeout = 3600 }\n"
    )
    completed, payload, _ = run_adapter(tmp_path, "status", config=config)
    assert completed.returncode == 0
    assert payload["timeoutSeconds"] == 3600
    assert payload["label"] == "1h"
