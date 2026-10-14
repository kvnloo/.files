from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import workspace_flow as wf  # noqa: E402


def _db(topk, status="idle", prepare=None):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    wf.ensure_flow_schema(db)
    db.execute(
        """INSERT INTO shadow_predictions(
               pred_id, schema_name, ts, trigger_event_id, context_id, state_json,
               topk_json, latency_ms, confidence, margin, entropy, receipt_json
           ) VALUES ('p1',?,?,NULL,'c',?,?,0,0,0,0,'{}')""",
        (wf.SCHEMA, wf._now(), "{}", json.dumps(topk)),
    )
    db.execute(
        "UPDATE next_action_surface SET pred_id='p1', status=?, prepare_json=? WHERE id=1",
        (status, json.dumps(prepare or {})),
    )
    return db


def _item(op, target, p):
    return {"operator_family": op, "family": "harness", "target": target, "p": p, "context_id": "c"}


def test_ghost_tier_and_candidates_skip_noop():
    db = _db([_item("open_context", "a", 0.41), _item("noop", "", 0.3), _item("run_test", "b", 0.2), _item("retrieve", "c", 0.05), _item("delegate", "d", 0.04)])
    out = wf.show_next_action(db)
    assert out["tier"] == "ghost"
    assert [c["target"] for c in out["candidates"]] == ["a", "b", "c"]
    assert out["bar"]["text"].endswith("41%")
    assert "Super+BackSpace" in out["bar"]["tooltip"]


def test_none_tier_when_noop_top_or_low_p():
    assert wf.show_next_action(_db([_item("noop", "", 0.5), _item("open_context", "a", 0.3)]))["tier"] == "none"
    low = wf.show_next_action(_db([_item("open_context", "a", wf.GHOST_MIN_P - 0.01)]))
    assert low["tier"] == "none" and low["bar"]["text"] == ""


def test_ready_tier_and_suppressed_none():
    assert wf.show_next_action(_db([_item("open_context", "a", 0.9)], status="ready"))["tier"] == "ready"
    assert wf.show_next_action(_db([_item("open_context", "a", 0.9)], status="suppressed"))["tier"] == "none"


def _commit(db):
    return wf.commit_next_action(db, run_fn=mock.Mock(), tmux_args_fn=mock.Mock())


def test_commit_refuses_idle_none_and_suppressed_even_with_prepare():
    prepare = {"cache_key": "k", "outcome": "prepare_created"}
    for db in (
        _db([_item("noop", "", 0.6)], prepare=prepare),
        _db([_item("open_context", "a", 0.1)], prepare=prepare),
        _db([_item("open_context", "a", 0.9)], status="suppressed", prepare=prepare),
    ):
        res = _commit(db)
        assert res["ok"] is False
