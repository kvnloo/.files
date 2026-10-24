from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
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
        CREATE TABLE IF NOT EXISTS hypr_windows (
            app TEXT, workspace TEXT, focused INTEGER, last_seen REAL
        );
        CREATE TABLE IF NOT EXISTS tmux_panes (
            pane_id TEXT, session TEXT, window_id TEXT, window_index TEXT,
            window_name TEXT, command TEXT, project TEXT, active INTEGER,
            dead INTEGER, width INTEGER, height INTEGER, left INTEGER, top INTEGER,
            last_seen REAL
        );
        """
    )
    db.commit()
    return db


def test_commit_consumes_prepare_without_surface():
    db = _mem_db()
    pred_id = "pred-e2e-1"
    prepare = {
        "kind": "inspect_result",
        "provider": "inspect_result",
        "operator_family": "inspect_result",
        "context_id": "ctx123",
        "family": "harness",
        "target": "omp",
        "eligible": True,
        "outcome": "prepare_created",
        "prepare_arm": "prepared",
        "started_at": wf._now(),
        "ready_at": wf._now(),
        "cost_ms": 2.5,
        "cache_key": "prep:inspect_result:ctx123:harness:omp",
        "resolved": {
            "dispatch": {"action": "inspect_harness", "harness": "omp"},
            "inspect": {"action": "inspect_harness", "harness": "omp"},
        },
        "artifacts": {"recap": {"state": "completed"}},
        "horizon_ms": wf.PRIMARY_HORIZON_MS,
    }
    db.execute(
        """INSERT INTO shadow_predictions(
               pred_id, schema_name, ts, trigger_event_id, context_id,
               state_json, topk_json, latency_ms, confidence, margin, entropy, receipt_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pred_id,
            wf.SCHEMA,
            wf._now(),
            None,
            "ctx123",
            json.dumps({"context_id": "ctx123", "project": "/tmp/p"}),
            json.dumps(
                [
                    {
                        "family": "harness",
                        "target": "omp",
                        "p": 0.48,
                        "operator_family": "inspect_result",
                        "context_id": "ctx123",
                    }
                ]
            ),
            0.5,
            0.48,
            0.1,
            0.2,
            json.dumps({"context_id": "ctx123", "prepare": prepare}),
        ),
    )
    db.execute(
        """UPDATE next_action_surface SET
               updated_at=?, pred_id=?, summary='', action_family='', action_target='',
               target_context_id='ctx123', prepare_json=?, status='idle',
               surface_arm='ineligible', surface_reason='p<0.82'
           WHERE id=1""",
        (wf._now(), pred_id, json.dumps(prepare)),
    )
    db.execute(
        """INSERT INTO prepare_cache(cache_key, kind, created_at, expires_at, payload_json)
           VALUES (?,?,?,?,?)""",
        (
            prepare["cache_key"],
            "inspect_result",
            wf._now(),
            wf._now() + 100,
            json.dumps(prepare),
        ),
    )
    db.commit()

    with tempfile.TemporaryDirectory() as tmp:
        old = __import__("os").environ.get("Z0INT_HOME")
        __import__("os").environ["Z0INT_HOME"] = tmp
        try:
            out = wf.commit_next_action(
                db,
                run_fn=lambda cmd: SimpleNamespace(returncode=0, stderr=""),
                tmux_args_fn=lambda *a: list(a),
                source="test",
            )
            assert out["ok"] is True
            assert out.get("prepare_consumed") is True
            events_path = Path(tmp) / "tokenomics" / wf.PREPARE_EVENTS_NAME
            assert events_path.is_file()
            lines = [json.loads(x) for x in events_path.read_text().splitlines() if x.strip()]
            consumed = [r for r in lines if r.get("prepare_outcome") == "prepare_consumed"]
            assert consumed
            assert consumed[-1].get("latency_hidden_ms") == 2.5
        finally:
            if old is None:
                __import__("os").environ.pop("Z0INT_HOME", None)
            else:
                __import__("os").environ["Z0INT_HOME"] = old


def test_prepare_withhold_records_would_prepare():
    db = _mem_db()
    topk = [
        {
            "family": "harness",
            "target": "omp",
            "p": 0.5,
            "operator_family": "inspect_result",
            "context_id": "ctxw",
        }
    ]
    with mock.patch.object(wf.random, "random", return_value=0.0):
        ok, reason, arm = wf.gate_prepare(topk)
    assert ok and arm == "withheld" and reason == "withhold_arm"
    state = {"context_id": "ctxw", "project": "/tmp/p", "harness_state": "completed"}
    payload = wf.record_would_prepare(db, prediction=topk[0], current=state, pred_id="pw1")
    assert payload["outcome"] == "would_prepare"
    assert payload["prepare_arm"] == "withheld"


def test_run_test_prepare_builds_command_metadata():
    db = _mem_db()
    payload = {
        "resolved": {},
        "artifacts": {},
    }
    wf._prepare_run_test(
        db,
        prediction={"target": str(Path(__file__).resolve().parent.parent), "state": {}},
        current={"project": str(Path(__file__).resolve().parents[1])},
        payload=payload,
    )
    plan = payload["artifacts"].get("test_plan") or {}
    assert payload.get("kind") == "run_test"
    assert plan.get("command", "").startswith("pytest")
    assert plan.get("verifier") == "pytest_exit_and_assertions"
    assert payload["resolved"]["dispatch"]["action"] == "run_test"
