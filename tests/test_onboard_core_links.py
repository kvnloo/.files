import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ONBOARD = REPO / "scripts" / "onboard"


def test_core_links_install_service_executable_aliases(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    backend = tmp_path / "backend"
    module = backend / "src/z0int/fsm/guard.py"
    module.parent.mkdir(parents=True)
    module.write_text("print('fixture-backend')\n")
    for args in (
        ("init", "-b", "main"),
        ("add", "."),
        ("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "-m", "test backend"),
    ):
        subprocess.run(
            ["git", "-C", str(backend), *args],
            check=True, capture_output=True, text=True,
        )
    env = os.environ | {
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "ONBOARD_NONINTERACTIVE": "1",
        "ONBOARD_ASSUME_YES": "1",
        "Z0INT_BACKEND_REPO": str(backend),
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
    assert (home / "Downloads" / "Taildrop").is_dir()
    for name in (
        "performance-pressure",
        "taildrop-portal",
        "tmux-agent-launcher",
        "tmux-fleet-switcher",
        "tmux-task-menu",
        "tmux-widget-grid",
    ):
        installed = home / ".local" / "bin" / name
        assert installed.is_symlink(), f"missing service executable alias: {installed}"
        assert installed.resolve().is_file()
