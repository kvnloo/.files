"""OnFailure=service-watch-failure@<unit>.service must name the unit systemd-escaped.

The watcher reads its instance with %I, which turns "-" into "/". An inline
OnFailure=service-watch-failure@host-optimizer.service.service therefore starts a second
watcher for "host/optimizer.service" that dies with "Invalid unit". The failure is reported
by the working drop-in at best, and not at all where there is none. It was fixed once
(memory-recall-check, 10-27) and came back in host-drift and host-optimizer by 11-15.
"""

import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"
WATCH = re.compile(r"^OnFailure=.*?service-watch-failure@(\S+?)\.service(?:\s|$)", re.M)


def test_service_watch_onfailure_instances_are_escaped():
    bad = []
    for path in sorted(UNITS.rglob("*")):
        if path.is_file():
            for instance in WATCH.findall(path.read_text(errors="replace")):
                if "-" in instance or "%n" in instance:
                    bad.append(f"{path.relative_to(UNITS)}: {instance}")
    assert not bad, "use systemd-escape (\\x2d) or leave it to the 90-service-watch.conf drop-in:\n" + "\n".join(bad)
