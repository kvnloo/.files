import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "scripts" / "phone-setup-handoff"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_handoff_from_fresh_home_and_repeat(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for relative in ("docs/phone-setup/README.md", "scripts/phone-setup"):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    _git("init", "-b", "master", cwd=source)
    _git("add", ".", cwd=source)
    _git(
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "phone setup handoff fixture",
        cwd=source,
    )

    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Keep adb and Hermes out of PATH: this exercise must not touch a real phone.
    for name in ("bash", "cat", "dirname", "git", "mkdir", "readlink"):
        executable = shutil.which(name)
        assert executable is not None
        (bin_dir / name).symlink_to(executable)

    checkout = home / "new" / "nested" / "files"
    env = os.environ | {
        "HOME": str(home),
        "PATH": str(bin_dir),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "PHONE_SETUP_REPO": str(source),
        "PHONE_SETUP_DIR": str(checkout),
        "PHONE_SETUP_BRANCH": "master",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    assert not checkout.parent.exists()
    for _ in range(2):
        completed = subprocess.run(
            [str(HANDOFF)],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        assert f"map:     {checkout}/docs/phone-setup/README.md" in completed.stdout
        assert "no adb, phone not checked" in completed.stdout
        assert "Paste this into Hermes" in completed.stdout
        assert (checkout / "scripts/phone-setup").is_file()
