import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ONBOARD = REPO / "scripts" / "onboard"
BUNDLE = REPO / "artifacts" / "hermes-portable"


def test_native_skill_snapshot_has_only_reinstallable_public_sources() -> None:
    snapshot = json.loads((BUNDLE / "skills.snapshot.json").read_text())
    assert snapshot["skills"]
    for skill in snapshot["skills"]:
        assert skill["source"] in {"official", "url", "clawhub"}
        identifier = skill["identifier"]
        assert not identifier.startswith(("/", "file:"))
        assert "/home/" not in identifier
        assert "/workspace/" not in identifier


def test_onboard_module_symlinks_bundle_and_uses_native_skill_import(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "hermes.calls"
    fake_hermes = fake_bin / "hermes"
    fake_hermes.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$HERMES_CALL_LOG\"\n"
    )
    fake_hermes.chmod(0o755)
    env = os.environ | {
        "HOME": str(home),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HERMES_CALL_LOG": str(call_log),
    }

    completed = subprocess.run(
        [str(ONBOARD), "run", "hermes-portable", "--yes"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    linked = home / ".config" / "hermes-portable" / "kvnloo"
    assert linked.is_symlink()
    assert linked.resolve() == BUNDLE.resolve()
    assert call_log.read_text().splitlines() == [
        f"skills snapshot import {linked / 'skills.snapshot.json'}"
    ]


def test_onboard_refuses_import_when_link_does_not_resolve_to_bundle(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "hermes.calls"
    fake_hermes = fake_bin / "hermes"
    fake_hermes.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$HERMES_CALL_LOG\"\n")
    fake_hermes.chmod(0o755)
    fake_ln = fake_bin / "ln"
    fake_ln.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_ln.chmod(0o755)
    env = os.environ | {
        "HOME": str(home),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HERMES_CALL_LOG": str(call_log),
    }

    completed = subprocess.run(
        [str(ONBOARD), "run", "hermes-portable", "--yes"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "did not resolve to the sanitized bundle" in completed.stderr
    assert not call_log.exists()
