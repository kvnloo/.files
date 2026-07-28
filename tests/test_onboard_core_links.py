import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ONBOARD = REPO / "scripts" / "onboard"


def test_core_links_install_service_executable_aliases(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    env = os.environ | {
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "ONBOARD_NONINTERACTIVE": "1",
        "ONBOARD_ASSUME_YES": "1",
    }

    completed = subprocess.run(
        [str(ONBOARD), "run", "core-links", "--noninteractive", "--yes"],
        cwd=REPO,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    for name in ("performance-pressure", "taildrop-portal"):
        installed = home / ".local" / "bin" / name
        assert installed.is_symlink(), f"missing service executable alias: {installed}"
        assert installed.resolve().is_file()
