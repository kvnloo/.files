from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import workspace_flow as wf  # noqa: E402
import workspace_rerank as rr  # noqa: E402

APPS = ("zen", "so.stencil.tern", "discord")


def _state(app: str) -> dict[str, str]:
    return {k: "" for k in wf.STATE_KEYS} | {"app": app, "workspace": "1", "monitor": "0"}


def _cand(app: str, p: float, family: str = "switch_app") -> dict:
    st = _state(app)
    return {"context_id": wf.context_id_of(st), "family": family, "target": app, "p": p, "state": st}


def _pingpong_db(n: int = 400) -> sqlite3.Connection:
    """User bounces between the last two apps; the engine always guesses discord."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    wf.ensure_flow_schema(db)
    t0 = time.time() - n * 30
    seq = [APPS[0], APPS[1]] * (n // 2)
    for i in range(1, len(seq)):
        ts = t0 + i * 30
        prev, cur = seq[i - 1], seq[i]
        db.execute(
            """INSERT INTO context_episodes(context_id, ts_before, ts_after, state_before_json, closed)
               VALUES (?,?,?,?,1)""",
            (wf.context_id_of(_state(prev)), ts - 30, ts, json.dumps(_state(prev))),
        )
        topk = [_cand("discord", 0.6), _cand(prev, 0.3), _cand(cur, 0.1, family="stay")]
        pid = f"p{i}"
        db.execute(
            """INSERT INTO shadow_predictions(pred_id, schema_name, ts, context_id, state_json, topk_json, latency_ms)
               VALUES (?,?,?,?,?,?,0)""",
            (pid, wf.SCHEMA, ts, wf.context_id_of(_state(cur)), json.dumps(_state(cur)), json.dumps(topk)),
        )
        db.execute(
            """INSERT INTO prediction_horizons(pred_id, horizon_ms, opened_at, closed_at, actual_family, actual_target)
               VALUES (?,?,?,?,?,?)""",
            (pid, rr.HORIZON_MS, ts, ts + 20, "switch_app", prev),
        )
    return db


def test_train_beats_engine_and_reranks_previous_app_first(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "MIN_TRAIN_ROWS", 50)
    monkeypatch.setattr(rr, "SESSION_GAP_S", 1)  # every row its own session for a clean holdout
    db = _pingpong_db()
    path = tmp_path / "m.json"
    out = rr.train(db, path=path)
    assert out["ok"] and out["promoted"]
    assert out["holdout"]["model_top1"] > out["holdout"]["engine_top1"]
    assert (path.stat().st_mode & 0o077) == 0

    # Live: current app is tern, previous was zen; the engine still says discord.
    db.execute(
        """INSERT INTO context_episodes(context_id, ts_before, ts_after, state_before_json, closed)
           VALUES (?,?,?,?,1)""",
        ("z", time.time() - 40, time.time() - 5, json.dumps(_state("zen"))),
    )
    engine = [_cand("discord", 0.6), _cand("so.stencil.tern", 0.4, family="stay")]
    ranked = rr.apply(
        db, _state("so.stencil.tern"), engine,
        candidates_fn=lambda _db, _st: [_cand("zen", 0.0)],
        operator_fn=wf._operator_family,
        path=path,
    )
    assert ranked[0]["target"] == "zen" and ranked[0]["source"] == rr.SOURCE
    assert ranked[0]["incumbent_keys"][0] == "switch_app:discord"
    assert abs(sum(i["p"] for i in ranked) - 1.0) < 1e-3


def test_passthrough_without_model_or_when_not_promoted(tmp_path):
    db = _pingpong_db(20)
    engine = [_cand("discord", 0.6)]
    kw = dict(candidates_fn=lambda _db, _st: [], operator_fn=wf._operator_family)
    assert rr.apply(db, _state("zen"), engine, path=tmp_path / "missing.json", **kw) is engine
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"schema": rr.MODEL_SCHEMA, "trained_at": time.time(), "promoted": False,
                             "classes": ["noop"], "vocab": {}, "W": [], "b": [0.0, 0.0]}))
    assert rr.apply(db, _state("zen"), engine, path=p, **kw) is engine
    stale = tmp_path / "s.json"
    stale.write_text(json.dumps({"schema": rr.MODEL_SCHEMA, "trained_at": time.time() - rr.MAX_MODEL_AGE_S - 1,
                                 "promoted": True, "classes": ["noop"], "vocab": {}, "W": [], "b": [0.0, 0.0]}))
    assert rr.apply(db, _state("zen"), engine, path=stale, **kw) is engine


def test_training_rows_have_no_future_history():
    db = _pingpong_db(60)
    for r in rr.training_rows(db):
        # prev0 is the most recent closed episode, which must be the label's own target here
        prev = [f for f in r["x"] if f.startswith("prev0=")]
        assert prev and prev[0] == "prev0=" + r["label"].split(":", 1)[1]


def test_engine_hook_can_be_disabled(monkeypatch):
    monkeypatch.setenv("WORKSPACE_RERANK", "0")
    topk = [_cand("discord", 1.0)]
    assert wf.rerank_topk(None, _state("zen"), topk) is topk
