import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "scripts" / "install-fonts.sh"


def test_print_selects_nerd_and_named_base_families() -> None:
    completed = subprocess.run(
        [str(INSTALL), "--print"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    selected = set(completed.stdout.split())
    assert {
        "ttf-jetbrains-mono-nerd",
        "ttf-roboto-mono-nerd",
        "ttf-firacode-nerd",
        "ttf-iosevka-nerd",
        "ttf-meslo-nerd",
        "ttf-fantasque-nerd",
        "ttf-jetbrains-mono",
        "ttf-roboto-mono",
    } <= selected
    assert "papirus-icon-theme" not in selected
    assert "ibus" not in selected
