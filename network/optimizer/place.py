"""place(job, networkState) -> decision   (pure policy; WP1 scope).

A pure function: the same inputs always yield the same decision (L-P6). It never
reads the clock, the network, or a file; everything it needs is in `state`.

WP1 scope, per the Revisions (R1/R4/R9):
  - No cost/fit score and no lmfit model (R4). The hard gate plus the single
    mbp->groot build rule is the whole policy for v1.
  - The optimizer does NOT own admission math (R1). For a groot candidate it
    reads two gate signals that the sampler already collected -- groot headroom
    and groot kill-rate -- and treats them as a yes/no from the existing gate.
    It never writes limits or cgroups.
  - Only `build/test` is auto-routable, and only a NEW invocation (R5). Stateful
    or already-running work is never moved here; the loop only PROPOSES those.

verdict in {AdmitHere, Route(host), Wait, Refuse}
"""

from __future__ import annotations

import laws

# Classes the optimizer may auto-route in WP1. Everything else is AdmitHere
# (leave it where it is) or, for stateful work, a PROPOSE handled by the loop.
STATELESS_ROUTABLE = {"build/test"}
INTERACTIVE = {"interactive-UI", "interactive-agent"}

# groot gate signals (read-only; the real gate stays in agent-oom-guard).
# A build job needs this much headroom on the target before we route to it.
GROOT_MIN_AVAIL_MIB = 3072          # conservative; calibrated later from data
GROOT_KILL_STORM_WINDOW_S = 600     # 10 min
GROOT_KILL_STORM_MAX = 0            # any kill in the window -> target is unsafe


def _verdict(kind: str, host: str | None = None) -> dict:
    return {"verdict": kind, "host": host}


def groot_admits(state: dict, job: dict) -> tuple[bool, str]:
    """Read-only query of the target gate. Returns (admit, reason).

    This is NOT the admission math -- it is a conservative pre-check that mirrors
    what the existing gate would refuse, so we never route into an OOM storm
    (Revisions Q2: sending work to a memory-tight / flapping groot cascades).
    """
    g = state["hosts"].get("groot")
    if not g or not g.get("reachable"):
        return False, "groot unreachable"
    avail = g.get("mem_available_mib", 0)
    cap = job.get("memory_cap_mib")
    need = GROOT_MIN_AVAIL_MIB if cap is None else max(GROOT_MIN_AVAIL_MIB, cap)
    if avail < need:
        return False, f"groot headroom {avail}MiB < need {need}MiB"
    if g.get("kills_last_10min", 0) > GROOT_KILL_STORM_MAX:
        return False, f"groot kill-storm ({g['kills_last_10min']} in 10min)"
    return True, f"groot admits (avail={avail}MiB, kills10m=0)"


def place(job: dict, state: dict) -> dict:
    """Pure placement. `job` has: cls, memory_cap_mib, reuse_packet_receipt,
    origin_host, started (bool). `state` is the sampled networkState."""
    cls = job.get("cls", "")

    # --- 2a Hard gate, in order; first failure decides ---------------------

    # 1. UI/agent protection (D2): pin to the human's host, never migrate.
    if cls in INTERACTIVE:
        return {**_verdict("AdmitHere", job.get("origin_host")),
                "engine": "native", "slice": "ui",
                "reason": "interactive-* pinned to human host (D2)"}

    # 2. Reuse receipt (D8 / L-P7): build & fine-tune need a receipt.
    if not laws.reuse_ok(job):
        return {**_verdict("Refuse"), "reason": "no reuse_packet receipt (L-P7)"}

    # 3. Declared cap (D3): missing / infinite cap counts as all of RAM.
    cap = job.get("memory_cap_mib")
    if cap is None or cap == float("inf"):
        return {**_verdict("Refuse"),
                "reason": "memory_cap missing/infinite -> never admitted (D3)"}

    # WP1 only auto-routes build/test. Anything else stays where it is.
    if cls not in STATELESS_ROUTABLE:
        return {**_verdict("AdmitHere", job.get("origin_host")),
                "reason": f"class '{cls}' not auto-routed in WP1"}

    # R5: never move a job that has already started. Route only NEW invocations.
    if job.get("started"):
        return {**_verdict("AdmitHere", job.get("origin_host")),
                "reason": "already running -> never migrated (R5); propose only"}

    origin = job.get("origin_host", "mbp")
    mbp = state["hosts"].get(origin, {})

    # 4. mbp lag guard (L-P4): if the origin host is lagging, drop it.
    lagging = laws.host_is_lagging(
        mbp.get("psi_mem_full_avg60", 0.0),
        mbp.get("psi_cpu_some_avg10", 0.0),
        mbp.get("swap_frac", 0.0),
    )
    if not lagging:
        return {**_verdict("AdmitHere", origin), "engine": "native",
                "slice": "batch",
                "reason": f"{origin} not lagging -> run build locally"}

    # Origin lags -> route the NEW build to groot IF groot's gate admits.
    admit, why = groot_admits(state, job)
    if not admit:
        # 5. NEVER silently fall back; WAIT (bounded) then OwnerDecision.
        return {**_verdict("Wait"),
                "reason": f"{origin} lags but {why} -> Wait (bounded 10min)"}

    return {**_verdict("Route", "groot"),
            "engine": "remote-exec", "slice": "batch",
            "limits": {"parallelism": "nproc/2"},
            "reason": f"{origin} lags ({_lag_detail(mbp)}); {why}"}


def _lag_detail(h: dict) -> str:
    return (f"cpu_some10={h.get('psi_cpu_some_avg10', 0):.0f} "
            f"mem_full60={h.get('psi_mem_full_avg60', 0):.1f} "
            f"swap={h.get('swap_frac', 0):.2f}")
