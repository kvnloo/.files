from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import workspace_flow as wf  # noqa: E402


def _mem_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    wf.ensure_flow_schema(db)
    db.executescript(
        """
        CREATE TABLE hypr_windows (
            app TEXT, workspace TEXT, monitor TEXT, focused INTEGER, last_seen REAL
        );
        CREATE TABLE harness_context (
            harness TEXT, state TEXT, project TEXT, session TEXT,
            window TEXT, pane_id TEXT, label TEXT, updated_at REAL
        );
        """
    )
    return db


def test_short_horizon_noops_do_not_outvote_a_60s_next_context():
    db = _mem_db()
    now = wf._now()
    current = {key: "" for key in wf.STATE_KEYS}
    current.update(app="source-app", workspace="1", monitor="monitor-1")
    current["context_id"] = wf.context_id_of(current)
    after = {key: current.get(key, "") for key in wf.STATE_KEYS}
    after["app"] = "target-app"
    target_context_id = wf.context_id_of(after)

    # Twelve independent predictions each transition inside 60s, but only after
    # the shorter censored windows. Their short-window noop labels are correlated
    # measurements of the same outcomes, not twelve extra kinds of stay evidence.
    for index in range(12):
        opened_at = now - 50 + index * 0.01
        transition_at = opened_at + 15
        pred_id = f"horizon-pred-{index}"
        db.execute(
            """INSERT INTO context_episodes(
                   context_id, ts_before, ts_after, state_before_json,
                   action_family, action_target, state_after_json, closed
               ) VALUES (?,?,?,?,?,?,?,1)""",
            (
                current["context_id"],
                opened_at,
                transition_at,
                json.dumps(current),
                "switch_app",
                "target-app",
                json.dumps({**after, "context_id": target_context_id}),
            ),
        )
        db.execute(
            """INSERT INTO shadow_predictions(
                   pred_id, schema_name, ts, context_id, state_json, topk_json, latency_ms
               ) VALUES (?,?,?,?,?,?,?)""",
            (
                pred_id,
                wf.SCHEMA,
                opened_at,
                current["context_id"],
                json.dumps(current),
                "[]",
                0.0,
            ),
        )
        for horizon_ms in wf.HORIZONS_MS:
            family = "switch_app" if horizon_ms == 60000 else wf.NOOP_LABEL
            db.execute(
                """INSERT INTO prediction_horizons(
                       pred_id, horizon_ms, opened_at, closed_at, actual_family
                   ) VALUES (?,?,?,?,?)""",
                (pred_id, horizon_ms, opened_at, transition_at, family),
            )

    topk, _ = wf.predict_next_context_v0(db, current)

    assert topk[0]["context_id"] == target_context_id
    assert topk[0]["family"] == "switch_app"
    assert topk[0]["operator_family"] == "open_context"
    assert topk[0]["p"] >= wf.SURFACE_MIN_P
    with mock.patch.object(wf.random, "random", return_value=1.0):
        assert wf.gate_surface(topk) == (True, "shown", "eligible")
