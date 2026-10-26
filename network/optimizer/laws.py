"""Network meta-optimizer laws (Python twin).

These are the invariants the optimizer must preserve every cycle. They are the
Python form of the laws in META-OPTIMIZER-SPEC.md section 6, corrected by the
Revisions (R1, R3, R9):

  - R3: the Bend twin and its CI are CUT from v1. Only the Python predicates plus
    a fixture test ship. There is no second runtime to keep byte-equivalent.
  - R1: L-P1 (Headroom floor) is DELETED here. The optimizer does not own the
    admission math; it CALLS the existing gate (agent-oom-guard / groot-admit).
    Keeping a second copy of the admission predicate only lets the two drift.
  - R9: L-P5 (single kill owner) is REPLACED. The stack legitimately runs several
    killers (earlyoom, systemd-oomd, agent-oom-guard) with layered roles. The
    real invariant is: the optimizer adds NO killer of its own, and every existing
    killer has is-enabled == is-active.

Every predicate is pure: no clock, no RNG, no hidden reads. Same inputs -> same
result. That is what makes decisions reproducible (L-P6).
"""

from __future__ import annotations

# --- L-P2  UI protection always holds (L12 acceptance metric) ---------------
# Measured on the UI cgroup under <=5 min of batch load. If this fails the
# optimizer sheds batch in the UI's pressure domain by routing NEW work away
# (R9: it never issues a kill and never writes memory.* / oom_score_adj).

UI_SWAP_GROWTH_MIB_MAX = 16
UI_PGMAJFAULT_MAX = 2000
UI_PSI_FULL_AVG10_MAX = 1.0  # percent
HYPR_P99_MS_MAX = 50


def ui_ok(ui_swap_growth_mib: float, ui_pgmajfault: float,
          ui_psi_full_avg10: float, hypr_p99_ms: float) -> bool:
    return (ui_swap_growth_mib <= UI_SWAP_GROWTH_MIB_MAX
            and ui_pgmajfault <= UI_PGMAJFAULT_MAX
            and ui_psi_full_avg10 <= UI_PSI_FULL_AVG10_MAX
            and hypr_p99_ms <= HYPR_P99_MS_MAX)


# --- L-P3  Anti-thrash: never move a job more than N times/hour -------------
N_MOVES_PER_HOUR = 2


def may_move(moves_last_hour: int, n: int = N_MOVES_PER_HOUR) -> bool:
    return moves_last_hour < n


# --- L-P4  mbp lag guard: no non-interactive work on a lagging mbp ----------
# Host-wide guard (distinct from L-P2, which measures the UI cgroup only).
# OR of three thresholds; crossing any one means the host is lagging.
LAG_PSI_MEM_FULL_AVG60 = 5.0   # percent
LAG_PSI_CPU_SOME_AVG10 = 60.0  # percent
LAG_SWAP_FRAC = 0.6


def host_is_lagging(psi_mem_full_avg60: float, psi_cpu_some_avg10: float,
                    swap_frac: float) -> bool:
    return (psi_mem_full_avg60 > LAG_PSI_MEM_FULL_AVG60
            or psi_cpu_some_avg10 > LAG_PSI_CPU_SOME_AVG10
            or swap_frac > LAG_SWAP_FRAC)


def mbp_accepts(job_class: str, psi_mem_full_avg60: float,
                psi_cpu_some_avg10: float, swap_frac: float) -> bool:
    if job_class.startswith("interactive"):
        return True  # D2: interactive-* is pinned to the human's host, never guarded off
    return not host_is_lagging(psi_mem_full_avg60, psi_cpu_some_avg10, swap_frac)


# --- L-P5 (R9-corrected)  Kill-owner sanity -------------------------------
# The optimizer must not appear among the kill owners, and each existing killer
# must have is-enabled == is-active (the single-owner check lives in S4).

OPTIMIZER_KILLER_NAMES = {"network-optimizer"}


def kill_owner_sane(enabled_killers: set[str],
                    killer_enabled_active: dict[str, tuple[bool, bool]]) -> bool:
    if OPTIMIZER_KILLER_NAMES & set(enabled_killers):
        return False  # optimizer added itself as a killer -> forbidden
    return all(en == act for (en, act) in killer_enabled_active.values())


# --- L-P6  Reproducibility: a decision replays from its recorded state ------
def reproducible(decision, place_fn, load_state_fn) -> bool:
    replay = place_fn(decision["job"], load_state_fn(decision["networkState_ref"]))
    return (replay["verdict"] == decision["verdict"]
            and replay.get("host") == decision.get("host"))


# --- L-P7  Reuse gate: build/fine-tune refused without a reuse receipt ------
def reuse_ok(job: dict) -> bool:
    if job.get("cls") in ("build/test", "fine-tune"):
        return job.get("reuse_packet_receipt") is not None
    return True


# --- L-P8  Terminal honesty: completed requires a verified receipt ----------
def may_mark_completed(job: dict) -> bool:
    r = job.get("receipt")
    return bool(r) and bool(r.get("verified_from_running_source"))


ALL_LAWS = [
    "L-P2 ui_ok", "L-P3 may_move", "L-P4 mbp_accepts",
    "L-P5 kill_owner_sane", "L-P6 reproducible", "L-P7 reuse_ok",
    "L-P8 may_mark_completed",
]
