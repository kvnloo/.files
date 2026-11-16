"""Only the type-level hooks may route failures to service-watch.

{service,timer,socket}.d/90-service-watch.conf give every user unit
OnFailure=service-watch-failure@%n.service (.files@73837607). A unit that also names the watcher itself
starts a second handler per failure: escaped (host\\x2ddrift.service) and unescaped (host-drift.service)
instance names differ, so systemd does not merge them and every failure counted twice (seen live on
host-drift 2026-11-16). Before the type hooks, unescaped inline names also started a broken watcher for
"host/optimizer.service" (10-27, again 11-15). Leave failure routing to the type hooks.

The type hooks pass %n unescaped on purpose: the failure template only spools to intake/%I, and
drain_spool maps the nested path back ('/' -> '-'; test_failure_hook_intake_is_drained_without_python_in_the_hook),
proven live with a failing zprobe-type-hook@a-b.service recorded under its real name.
"""

import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"
WATCH = re.compile(r"^OnFailure=.*service-watch-failure@", re.M)
TYPE_HOOKS = {f"{kind}.d/90-service-watch.conf" for kind in ("service", "timer", "socket")}


def test_only_type_level_hooks_route_failures_to_service_watch():
    bad = [str(path.relative_to(UNITS)) for path in sorted(UNITS.rglob("*"))
           if path.is_file() and str(path.relative_to(UNITS)) not in TYPE_HOOKS
           and WATCH.search(path.read_text(errors="replace"))]
    assert not bad, "drop the inline OnFailure=service-watch-failure@...; the type-level hook covers it:\n" + "\n".join(bad)
