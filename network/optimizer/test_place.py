"""Fixture tests for the meta-optimizer policy + laws (R3: Python-only, no Bend).

Run:  python3 -m pytest test_place.py -q     (or: python3 test_place.py)

Covers:
  - the hard gate ordering in place() (D2/D3/L-P4/L-P7 and the Wait path),
  - that place() is PURE / reproducible on a recorded state (L-P6),
  - the law predicates (L-P2..L-P8, R9-corrected L-P5).
"""

from __future__ import annotations

import laws
import place as place_mod

# --- fixtures ---------------------------------------------------------------

LAGGING_MBP = {
    "hosts": {
        "mbp": {"reachable": True, "psi_cpu_some_avg10": 85.0,
                "psi_mem_full_avg60": 1.24, "swap_frac": 0.78},
        "groot": {"reachable": True, "mem_available_mib": 7500,
                  "kills_last_10min": 0},
    }
}
CALM_MBP = {
    "hosts": {
        "mbp": {"reachable": True, "psi_cpu_some_avg10": 10.0,
                "psi_mem_full_avg60": 0.2, "swap_frac": 0.1},
        "groot": {"reachable": True, "mem_available_mib": 7500,
                  "kills_last_10min": 0},
    }
}
GROOT_STORM = {
    "hosts": {
        "mbp": {"reachable": True, "psi_cpu_some_avg10": 85.0,
                "psi_mem_full_avg60": 6.0, "swap_frac": 0.78},
        "groot": {"reachable": True, "mem_available_mib": 7500,
                  "kills_last_10min": 3},
    }
}
GROOT_TIGHT = {
    "hosts": {
        "mbp": {"reachable": True, "psi_cpu_some_avg10": 85.0,
                "psi_mem_full_avg60": 6.0, "swap_frac": 0.78},
        "groot": {"reachable": True, "mem_available_mib": 1000,
                  "kills_last_10min": 0},
    }
}

BUILD = {"cls": "build/test", "memory_cap_mib": 2048,
         "reuse_packet_receipt": "r", "origin_host": "mbp", "started": False}


def _c(job, **over):
    j = dict(job)
    j.update(over)
    return j


def test_build_on_lagging_mbp_routes_to_groot():
    d = place_mod.place(_c(BUILD), LAGGING_MBP)
    assert d["verdict"] == "Route" and d["host"] == "groot", d
    assert d["engine"] == "remote-exec"


def test_build_on_calm_mbp_stays_local():
    d = place_mod.place(_c(BUILD), CALM_MBP)
    assert d["verdict"] == "AdmitHere" and d["host"] == "mbp", d


def test_running_build_is_never_migrated():
    d = place_mod.place(_c(BUILD, started=True), LAGGING_MBP)
    assert d["verdict"] == "AdmitHere", d  # R5: start-time only


def test_interactive_is_pinned_and_never_routed():
    for cls in ("interactive-UI", "interactive-agent"):
        d = place_mod.place(_c(BUILD, cls=cls), LAGGING_MBP)
        assert d["verdict"] == "AdmitHere" and d["slice"] == "ui", (cls, d)


def test_unbounded_cap_refused():
    d = place_mod.place(_c(BUILD, memory_cap_mib=None), LAGGING_MBP)
    assert d["verdict"] == "Refuse", d
    d2 = place_mod.place(_c(BUILD, memory_cap_mib=float("inf")), LAGGING_MBP)
    assert d2["verdict"] == "Refuse", d2


def test_build_without_reuse_receipt_refused():
    d = place_mod.place(_c(BUILD, reuse_packet_receipt=None), LAGGING_MBP)
    assert d["verdict"] == "Refuse", d


def test_groot_kill_storm_forces_wait_not_fallback():
    d = place_mod.place(_c(BUILD), GROOT_STORM)
    assert d["verdict"] == "Wait", d  # never route into a storm; never silent fallback


def test_groot_too_tight_forces_wait():
    d = place_mod.place(_c(BUILD), GROOT_TIGHT)
    assert d["verdict"] == "Wait", d


def test_place_is_pure_reproducible():
    # L-P6: same state -> same verdict, no hidden reads / clock / RNG.
    a = place_mod.place(_c(BUILD), LAGGING_MBP)
    b = place_mod.place(_c(BUILD), LAGGING_MBP)
    assert a == b, (a, b)


# --- law predicates ---------------------------------------------------------

def test_lp2_ui_ok():
    assert laws.ui_ok(10, 1500, 0.8, 40) is True
    assert laws.ui_ok(20, 1500, 0.8, 40) is False      # swap growth over 16MiB
    assert laws.ui_ok(10, 1500, 1.5, 40) is False      # psi full avg10 over 1.0
    assert laws.ui_ok(10, 1500, 0.8, 80) is False      # hypr p99 over 50ms


def test_lp3_anti_thrash():
    assert laws.may_move(0) and laws.may_move(1)
    assert not laws.may_move(2)


def test_lp4_mbp_lag_guard():
    assert laws.mbp_accepts("interactive-agent", 99, 99, 0.99) is True  # never guarded off
    assert laws.mbp_accepts("build/test", 1.0, 10, 0.1) is True
    assert laws.mbp_accepts("build/test", 1.0, 85, 0.1) is False        # cpu
    assert laws.mbp_accepts("build/test", 1.0, 10, 0.7) is False        # swap
    assert laws.mbp_accepts("build/test", 6.0, 10, 0.1) is False        # mem full


def test_lp5_kill_owner_corrected():
    killers = {"earlyoom": (True, True), "systemd-oomd": (True, True),
               "agent-oom-guard": (True, True)}
    assert laws.kill_owner_sane(set(killers), killers) is True
    # optimizer must never appear as a killer
    assert laws.kill_owner_sane({"network-optimizer"}, killers) is False
    # a killer whose enabled != active fails the invariant
    bad = dict(killers, earlyoom=(True, False))
    assert laws.kill_owner_sane(set(bad), bad) is False


def test_lp6_reproducible_helper():
    recorded = {"job": _c(BUILD), "verdict": "Route", "host": "groot",
                "networkState_ref": "x"}
    ok = laws.reproducible(recorded, place_mod.place, lambda _ref: LAGGING_MBP)
    assert ok is True


def test_lp7_reuse_gate():
    assert laws.reuse_ok({"cls": "eval"}) is True
    assert laws.reuse_ok({"cls": "build/test", "reuse_packet_receipt": "r"}) is True
    assert laws.reuse_ok({"cls": "fine-tune", "reuse_packet_receipt": None}) is False


def test_lp8_terminal_honesty():
    assert laws.may_mark_completed({"receipt": {"verified_from_running_source": True}})
    assert not laws.may_mark_completed({"receipt": None})
    assert not laws.may_mark_completed({"receipt": {"verified_from_running_source": False}})


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"PASS {fn.__name__}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
