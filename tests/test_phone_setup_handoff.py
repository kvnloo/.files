import os
import shutil
import subprocess
from pathlib import Path

import pytest


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


@pytest.fixture
def sandbox(tmp_path: Path) -> tuple[Path, dict[str, str]]:
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
    return checkout, env


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(HANDOFF)], env=env, capture_output=True, text=True, timeout=30,
    )


def test_handoff_from_fresh_home_and_repeat(sandbox) -> None:
    checkout, env = sandbox
    assert not checkout.parent.exists()
    for attempt in range(2):
        completed = _run(env)
        if attempt == 0:
            print(completed.stdout)
        assert completed.returncode == 0, completed.stderr
        assert f"map:     {checkout}/docs/phone-setup/README.md" in completed.stdout
        assert "no adb, phone not checked" in completed.stdout
        assert "Paste this into Hermes" in completed.stdout
        assert (checkout / "scripts/phone-setup").is_file()


def test_repeat_preserves_local_commit_and_dirty_files(sandbox) -> None:
    checkout, env = sandbox
    assert _run(env).returncode == 0
    local_file = checkout / "friend-notes.txt"
    local_file.write_text("my setup\n")
    _git("add", ".", cwd=checkout)
    _git(
        "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "friend's local work", cwd=checkout,
    )
    before = (checkout / ".git/refs/heads/master").read_text()
    local_file.write_text("my unfinished setup\n")
    completed = _run(env)
    assert completed.returncode == 0, completed.stderr
    assert (checkout / ".git/refs/heads/master").read_text() == before
    assert local_file.read_text() == "my unfinished setup\n"


def test_existing_directory_is_not_adopted(sandbox) -> None:
    checkout, env = sandbox
    checkout.mkdir(parents=True)
    completed = _run(env)
    assert completed.returncode != 0
    assert "choose a new PHONE_SETUP_DIR" in completed.stderr
    assert not (checkout / ".git").exists()


def test_existing_clone_needs_the_guide_and_checker(sandbox) -> None:
    checkout, env = sandbox
    assert _run(env).returncode == 0
    (checkout / "docs/phone-setup/README.md").unlink()
    completed = _run(env)
    assert completed.returncode != 0
    assert "missing the phone setup guide or executable checker" in completed.stderr
    assert not (checkout / "docs/phone-setup/README.md").exists()


def test_missing_branch_reports_error_without_handoff_prompt(sandbox) -> None:
    _, env = sandbox
    completed = _run(env | {"PHONE_SETUP_BRANCH": "missing"})
    assert completed.returncode != 0
    assert "no branch" in completed.stderr
    assert "Paste this into Hermes" not in completed.stdout


def test_dev_fallback(sandbox) -> None:
    checkout, env = sandbox
    source = Path(env["PHONE_SETUP_REPO"])
    _git("branch", "-m", "dev", cwd=source)
    env.pop("PHONE_SETUP_BRANCH")
    completed = _run(env)
    assert completed.returncode == 0, completed.stderr
    assert "branch dev" in completed.stdout
    assert (checkout / "docs/phone-setup/README.md").is_file()
