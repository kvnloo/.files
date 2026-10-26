"""Meta-optimizer cycle -- runs ONE idempotent cycle, timer-driven, on groot.

Loop shape (spec 4a), WP1-A scope: SAMPLE -> DETECT -> DECIDE -> LOG.
It is OBSERVE-ONLY by default (NETOPT_DRYRUN=1): it records the decision it
WOULD make (`enacted:false`) and enacts nothing. Actual routing of NEW build
invocations is done by the mbp-side `route-build` wrapper (WP1-B), not by this
loop -- the loop never kills, moves, or restarts a running process (R5/R9a) and
never writes limits/cgroups/oom_score_adj.

Safety (spec 4b):
  - Kill switch: if ~/tmp/network/network-optimizer.OFF exists, sample+log only.
  - Dead-man: if the loop cannot sample, it logs a safe no-op, never acts blind.
  - Rate limit / hysteresis: a route decision requires sustained lag (>=5 min)
    before it is marked actionable; a global cap of 1 enacted move / 10 min.

One line per cycle is appended to ~/tmp/network/decisions.jsonl, carrying the
networkState hash + the snapshot ref, so every decision replays (L-P6).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time

import laws
import place as place_mod
import sampler

BASE = sampler.BASE
DECISIONS = BASE / "decisions.jsonl"
OFF = BASE / "network-optimizer.OFF"
DRYRUN = os.environ.get("NETOPT_DRYRUN", "1") != "0"
SUSTAINED_LAG_S = int(os.environ.get("NETOPT_SUSTAINED_LAG_S", "300"))  # 5 min (R7)
PEER = sampler.PEER


def _hash_state(state: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]


def _sustained_lag_seconds(now_epoch: int) -> int:
    """How long has the peer been continuously lagging across recent snapshots?"""
    snaps = sorted(sampler.STATE_DIR.glob("[0-9]*.json"))
    streak_start = None
    for s in snaps:
        try:
            st = json.loads(s.read_text())
        except (OSError, ValueError):
            continue
        h = st.get("hosts", {}).get(PEER, {})
        lag = laws.host_is_lagging(
            h.get("psi_mem_full_avg60", 0.0),
            h.get("psi_cpu_some_avg10", 0.0),
            h.get("swap_frac", 0.0))
        if lag:
            streak_start = streak_start if streak_start is not None else st.get("epoch", now_epoch)
        else:
            streak_start = None
    if streak_start is None:
        return 0
    return max(0, now_epoch - streak_start)


def _probe_job() -> dict:
    """The representative NEW build/test job the fleet keeps producing on mbp
    (tsc/web-export/Metro/typecheck). Used to DECIDE where such a job belongs
    this cycle. It is a probe, not a running process -- nothing is touched."""
    return {
        "cls": "build/test",
        "memory_cap_mib": 2048,
        "reuse_packet_receipt": "wp1-probe",  # the fleet's build jobs carry one
        "origin_host": PEER,
        "started": False,
        "job_id": "probe:build/test@" + PEER,
    }


def run_cycle(cycle: int = 0) -> dict:
    off = OFF.exists()
    try:
        state = sampler.sample()
        ref = sampler.write_state(state)
    except Exception as e:  # noqa: BLE001  -- dead-man: never act blind
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cycle": cycle,
               "verdict": "NoOp", "reason": f"sample failed: {e!r}",
               "enacted": False, "dryrun": DRYRUN}
        _append(rec)
        return rec

    job = _probe_job()
    decision = place_mod.place(job, state)
    sustained = _sustained_lag_seconds(state["epoch"])
    actionable = (decision["verdict"] == "Route"
                  and sustained >= SUSTAINED_LAG_S)

    rec = {
        "ts": state["ts"],
        "cycle": cycle,
        "job_id": job["job_id"],
        "class": job["cls"],
        "from": job["origin_host"],
        "verdict": _verdict_str(decision),
        "engine": decision.get("engine"),
        "slice": decision.get("slice"),
        "limits": decision.get("limits"),
        "reason": decision["reason"],
        "sustained_lag_s": sustained,
        "actionable": actionable,
        "networkState_hash": _hash_state(state),
        "networkState_ref": f"state/{state['epoch']}.json",
        "enacted": False,          # WP1-A observe-only; wrapper does WP1-B
        "dryrun": DRYRUN,
        "kill_switch": off,
        "note": ("kill switch ON -> sample+log only" if off else
                 "observe-only; new-build routing handled by route-build wrapper"),
    }
    _append(rec)
    return rec


def _verdict_str(d: dict) -> str:
    v = d["verdict"]
    return f"{v}({d['host']})" if v == "Route" and d.get("host") else v


def _append(rec: dict) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    with DECISIONS.open("a") as f:
        f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    out = run_cycle(cycle=int(os.environ.get("NETOPT_CYCLE", "0")))
    print(json.dumps(out, indent=2), flush=True)
