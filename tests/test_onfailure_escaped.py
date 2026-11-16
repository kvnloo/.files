"""OnFailure=service-watch-failure@<unit>.service must name the unit systemd-escaped.

The watcher reads its instance with %I, which turns "-" into "/". An inline
OnFailure=service-watch-failure@host-optimizer.service.service therefore starts a second
watcher for "host/optimizer.service" that dies with "Invalid unit". The failure is reported
by the working drop-in at best, and not at all where there is none. It was fixed once
(memory-recall-check, 10-27) and came back in host-drift and host-optimizer by 11-15.

Exception: the type-level hooks ({service,timer,socket}.d/90-service-watch.conf) pass %n unescaped on
purpose. The failure template now only spools to intake/%I, and drain_spool maps the nested path back
('/' -> '-'; test_failure_hook_intake_is_drained_without_python_in_the_hook), proven live 2026-11-16 with
a failing zprobe-type-hook@a-b.service recorded under its real name.
"""

import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"
WATCH = re.compile(r"^OnFailure=.*?service-watch-failure@(\S+?)\.service(?:\s|$)", re.M)
TYPE_HOOKS = {f"{kind}.d/90-service-watch.conf" for kind in ("service", "timer", "socket")}


def test_service_watch_onfailure_instances_are_escaped():
    bad = []
    for path in sorted(UNITS.rglob("*")):
        if path.is_file() and str(path.relative_to(UNITS)) not in TYPE_HOOKS:
            for instance in WATCH.findall(path.read_text(errors="replace")):
                if "-" in instance or "%n" in instance:
                    bad.append(f"{path.relative_to(UNITS)}: {instance}")
    assert not bad, "use systemd-escape (\\x2d) or leave it to the 90-service-watch.conf drop-in:\n" + "\n".join(bad)
