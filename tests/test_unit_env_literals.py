"""systemd never expands ${VAR} or $VAR inside Environment=; the process gets the literal text.

sr-decision-shim sent 'Bearer ${JEV_API_KEY}' upstream for days that way (11-16). Put private values in
an EnvironmentFile= and reference them as ${VAR} in ExecStart=, where systemd does expand them."""
import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"


def test_environment_values_reference_no_variables():
    bad = [f"{p.relative_to(UNITS)}:{n}: {line.strip()[:120]}"
           for p in sorted(UNITS.rglob("*")) if p.is_file() and p.suffix in {".service", ".conf"}
           for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
           if re.match(r"\s*Environment=", line) and re.search(r"\$\{?\w", line.replace("$$", ""))]
    assert not bad, "\n".join(bad)
