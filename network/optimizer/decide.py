"""netopt-decide: groot-side one-shot verdict for a NEW job invocation.

Called by the mbp-side `route-build` wrapper over one ssh round trip. It reads
the latest cached networkState (kept fresh by the 60s timer -- it does NOT
re-sample, so it never ssh's back to the laptop and stays ~ms cheap), runs the
pure place() policy, and prints a single machine-readable verdict.

Output (stdout, first line is the token):
  LOCAL                      -> run the command on the origin host (fail-open default)
  ROUTE <json>               -> run via the plane in <json>.argv on the target
  WAIT                       -> origin lags but target gate refuses; caller runs LOCAL
Kill switch (OFF file) or stale/missing state -> LOCAL (never block the owner).
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import engine
import place as place_mod
import sampler

MAX_STALE_S = int(os.environ.get("NETOPT_MAX_STALE_S", "180"))


def decide(job_class: str, command: list[str]) -> tuple[str, dict]:
    if sampler.BASE.joinpath("network-optimizer.OFF").exists():
        return "LOCAL", {"reason": "kill switch ON"}
    latest = sampler.STATE_DIR / "latest.json"
    if not latest.exists():
        return "LOCAL", {"reason": "no state yet -> fail open"}
    try:
        state = json.loads(latest.read_text())
    except (OSError, ValueError):
        return "LOCAL", {"reason": "unreadable state -> fail open"}
    if time.time() - state.get("epoch", 0) > MAX_STALE_S:
        return "LOCAL", {"reason": "stale state -> fail open"}

    job = {
        "cls": job_class,
        "memory_cap_mib": int(os.environ.get("NETOPT_JOB_CAP_MIB", "2048")),
        "reuse_packet_receipt": os.environ.get("NETOPT_REUSE_RECEIPT", "wrapper"),
        "origin_host": sampler.PEER,
        "started": False,
        "job_id": f"wrapper:{job_class}@{sampler.PEER}",
    }
    d = place_mod.place(job, state)
    if d["verdict"] == "Route" and d.get("host") == "groot":
        groot = state["hosts"].get("groot", {})
        # groot nproc is not in state in WP1; default 20, capped to half downstream
        plan = engine.plan("build/test", command=command, target="groot",
                            groot_nproc=int(os.environ.get("NETOPT_GROOT_NPROC", "20")))
        if plan.get("exec"):
            return "ROUTE", {"plan": plan, "reason": d["reason"]}
        return "LOCAL", {"reason": "engine has no exec path -> fail open"}
    if d["verdict"] == "Wait":
        return "WAIT", {"reason": d["reason"]}
    return "LOCAL", {"reason": d["reason"]}


if __name__ == "__main__":
    cls = sys.argv[1] if len(sys.argv) > 1 else "build/test"
    cmd = sys.argv[2:]
    if cmd and cmd[0] == "--":   # tolerate a `--` separator from the wrapper
        cmd = cmd[1:]
    token, info = decide(cls, cmd)
    if token == "ROUTE":
        print("ROUTE " + json.dumps(info["plan"]))
    else:
        print(token)
    print("# " + info.get("reason", ""), file=sys.stderr)
