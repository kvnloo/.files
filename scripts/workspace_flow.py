#!/usr/bin/env python3
"""Flow predictor substrate for workspace-copilot.

OS branch-predictor layer with four separate gates:

  PREDICT  — always, <1ms, produces training data
  PREPARE  — often, discardable, no side effects
  SURFACE  — rarely, user-visible, never steals focus
  COMMIT   — explicit only (keyboard/mouse/voice/flow)

Privacy contract inherited from workspace-copilot:
  semantic events only; no keystrokes, titles, pane text, clipboard, screenshots.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

SCHEMA = "os.next_context.v0"
OPERATOR_SCHEMA = "os.next_operator.v0"
RECEIPT_SCHEMA = "flow_prediction.v1"
SURFACE_ID = 1

OPERATOR_FAMILIES = (
    "inspect_result",
    "run_test",
    "open_context",
    "delegate",
    "retrieve",
    "resume_previous",
    "noop",
)

# Censored horizons: label noop if no relevant action within window.
HORIZONS_MS = (500, 2000, 10000, 60000)

CONTEXT_TRIGGER_KINDS = frozenset(
    {
        "activewindow",
        "activewindowv2",
        "workspace",
        "workspacev2",
        "openwindow",
        "movewindow",
        "movewindowv2",
        "after-select-pane",
        "after-select-window",
        "client-session-changed",
        "harness",
        "task-sync",
        "task-update",
        "keybind",
    }
)

STATE_KEYS = (
    "app",
    "workspace",
    "monitor",
    "session",
    "window",
    "pane",
    "project",
    "harness",
    "harness_state",
    "task_phase",
    "task_status",
    "task",
)

PRED_TOP_K = 5
LOOKBACK_DAYS = 21
MIN_TRANSITIONS = 3

# Four gates — deliberately different thresholds.
PREPARE_MIN_P = 0.28          # prepare often (cheap)
PREPARE_MIN_MARGIN = 0.02
SURFACE_MIN_P = 0.82          # surface rarely
SURFACE_MIN_MARGIN = 0.12     # top1 - top2
SURFACE_MAX_ENTROPY = 1.35    # nats over top-k; high entropy → silence
WITHHOLD_RATE = 0.10          # eligible surface → 10% silent counterfactual arm
PREPARE_TTL_S = 180.0

STAY_LABEL = "stay"
NOOP_LABEL = "noop"
Z0INT_STREAM_NAME = "os_next_context.jsonl"
Z0INT_RECEIPT_NAME = "flow_predictions.jsonl"
Z0INT_HORIZON_NAME = "flow_horizons.jsonl"


def _now() -> float:
    return time.time()


def _json_text(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _entropy(probs: list[float]) -> float:
    s = 0.0
    for p in probs:
        if p > 0:
            s -= p * math.log(p)
    return s


def _margin(topk: list[dict[str, Any]]) -> float:
    if not topk:
        return 0.0
    if len(topk) == 1:
        return float(topk[0].get("p") or 0.0)
    return float(topk[0].get("p") or 0.0) - float(topk[1].get("p") or 0.0)


def ensure_flow_schema(db: Any) -> None:
    """Idempotent tables for episodes, shadow preds, horizons, receipts, gates."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS context_episodes (
            id INTEGER PRIMARY KEY,
            context_id TEXT NOT NULL,
            open_event_id INTEGER,
            close_event_id INTEGER,
            ts_before REAL NOT NULL,
            ts_after REAL,
            state_before_json TEXT NOT NULL,
            action_family TEXT NOT NULL DEFAULT '',
            action_target TEXT NOT NULL DEFAULT '',
            state_after_json TEXT NOT NULL DEFAULT '{}',
            horizon_ms REAL,
            closed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS context_episodes_open
            ON context_episodes(closed, ts_before);
        CREATE INDEX IF NOT EXISTS context_episodes_ctx
            ON context_episodes(context_id, ts_before);

        CREATE TABLE IF NOT EXISTS shadow_predictions (
            id INTEGER PRIMARY KEY,
            pred_id TEXT NOT NULL UNIQUE,
            schema_name TEXT NOT NULL,
            ts REAL NOT NULL,
            trigger_event_id INTEGER,
            context_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            topk_json TEXT NOT NULL,
            latency_ms REAL NOT NULL,
            actual_context_id TEXT,
            actual_family TEXT,
            actual_target TEXT,
            ranked INTEGER,
            manual_equivalent INTEGER,
            matched_at REAL,
            horizon_ms REAL,
            confidence REAL NOT NULL DEFAULT 0,
            margin REAL NOT NULL DEFAULT 0,
            entropy REAL NOT NULL DEFAULT 0,
            receipt_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS shadow_predictions_open
            ON shadow_predictions(matched_at, ts);
        CREATE INDEX IF NOT EXISTS shadow_predictions_schema
            ON shadow_predictions(schema_name, ts);

        CREATE TABLE IF NOT EXISTS prediction_horizons (
            id INTEGER PRIMARY KEY,
            pred_id TEXT NOT NULL,
            horizon_ms INTEGER NOT NULL,
            opened_at REAL NOT NULL,
            closed_at REAL,
            actual_family TEXT,
            actual_target TEXT,
            actual_context_id TEXT,
            ranked INTEGER,
            manual_equivalent INTEGER,
            UNIQUE(pred_id, horizon_ms)
        );
        CREATE INDEX IF NOT EXISTS prediction_horizons_open
            ON prediction_horizons(closed_at, opened_at, horizon_ms);

        CREATE TABLE IF NOT EXISTS next_action_surface (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            updated_at REAL NOT NULL,
            pred_id TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            action_family TEXT NOT NULL DEFAULT '',
            action_target TEXT NOT NULL DEFAULT '',
            target_context_id TEXT NOT NULL DEFAULT '',
            prepare_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'idle',
            suppress_fingerprint TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0,
            surface_arm TEXT NOT NULL DEFAULT 'ineligible',
            surface_reason TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO next_action_surface(id, updated_at, status)
            VALUES(1, 0, 'idle');

        CREATE TABLE IF NOT EXISTS prepare_cache (
            cache_key TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS prepare_cache_exp ON prepare_cache(expires_at);

        CREATE TABLE IF NOT EXISTS flow_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    # Additive migrations for older v4 installs.
    cols = {row[1] for row in db.execute("PRAGMA table_info(shadow_predictions)")}
    for col, ddl in (
        ("confidence", "ALTER TABLE shadow_predictions ADD COLUMN confidence REAL NOT NULL DEFAULT 0"),
        ("margin", "ALTER TABLE shadow_predictions ADD COLUMN margin REAL NOT NULL DEFAULT 0"),
        ("entropy", "ALTER TABLE shadow_predictions ADD COLUMN entropy REAL NOT NULL DEFAULT 0"),
        ("receipt_json", "ALTER TABLE shadow_predictions ADD COLUMN receipt_json TEXT NOT NULL DEFAULT '{}'"),
    ):
        if col not in cols:
            db.execute(ddl)
    scols = {row[1] for row in db.execute("PRAGMA table_info(next_action_surface)")}
    for col, ddl in (
        ("surface_arm", "ALTER TABLE next_action_surface ADD COLUMN surface_arm TEXT NOT NULL DEFAULT 'ineligible'"),
        ("surface_reason", "ALTER TABLE next_action_surface ADD COLUMN surface_reason TEXT NOT NULL DEFAULT ''"),
    ):
        if col not in scols:
            db.execute(ddl)


def context_id_of(state: dict[str, Any]) -> str:
    blob = "|".join(f"{k}={state.get(k, '')}" for k in STATE_KEYS)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def action_from_transition(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[str, str]:
    if before.get("app") and after.get("app") and before["app"] != after["app"]:
        return "switch_app", str(after["app"])
    if before.get("workspace") != after.get("workspace"):
        return "switch_workspace", str(after.get("workspace") or "")
    if (
        before.get("session") != after.get("session")
        or before.get("pane") != after.get("pane")
        or before.get("window") != after.get("window")
    ):
        target = after.get("pane") or after.get("window") or after.get("session") or ""
        return "switch_pane", str(target)
    if before.get("harness_state") != after.get("harness_state") or before.get("harness") != after.get("harness"):
        return "harness", str(after.get("harness_state") or after.get("harness") or "")
    if before.get("task") != after.get("task") or before.get("task_phase") != after.get("task_phase"):
        return "task", str(after.get("task") or after.get("task_phase") or "")
    if before.get("project") != after.get("project"):
        return "switch_project", str(after.get("project") or "")
    return STAY_LABEL, str(after.get("app") or "")


def semantic_state(
    db: Any,
    *,
    tmux_focus_fn: Callable[[], dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a privacy-safe semantic state vector for prediction."""
    focused = db.execute(
        """SELECT app, workspace, monitor, process
           FROM hypr_windows WHERE focused=1
           ORDER BY last_seen DESC LIMIT 1"""
    ).fetchone()
    app = focused["app"] if focused else ""
    workspace = focused["workspace"] if focused else ""
    monitor = focused["monitor"] if focused else ""

    focus: dict[str, str] = {}
    if tmux_focus_fn is not None:
        try:
            focus = tmux_focus_fn() or {}
        except Exception:
            focus = {}

    harness = db.execute(
        """SELECT harness, state, project, label, session, window, pane_id
           FROM harness_context ORDER BY updated_at DESC LIMIT 1"""
    ).fetchone()
    task = db.execute(
        """SELECT session, phase, task, status, project
           FROM task_context
           WHERE status IN ('in_progress','pending')
           ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                    updated_at DESC LIMIT 1"""
    ).fetchone()
    session_row = db.execute(
        """SELECT session, project, objective
           FROM task_session_context ORDER BY updated_at DESC LIMIT 1"""
    ).fetchone()
    prev = db.execute(
        """SELECT context_id FROM context_episodes
           WHERE closed=1 ORDER BY id DESC LIMIT 1"""
    ).fetchone()

    objective = ""
    if session_row and session_row["objective"]:
        objective = str(session_row["objective"])[:80]

    state = {
        "app": app or "",
        "workspace": workspace or "",
        "monitor": monitor or "",
        "session": (
            focus.get("session")
            or (harness["session"] if harness else "")
            or (task["session"] if task else "")
            or ""
        ),
        "window": focus.get("window") or (harness["window"] if harness else "") or "",
        "pane": focus.get("pane") or (harness["pane_id"] if harness else "") or "",
        "project": (
            (task["project"] if task and task["project"] else "")
            or (harness["project"] if harness and harness["project"] else "")
            or (session_row["project"] if session_row else "")
            or ""
        ),
        "harness": harness["harness"] if harness else "",
        "harness_state": harness["state"] if harness else "",
        "task_phase": task["phase"] if task else "",
        "task_status": task["status"] if task else "",
        "task": task["task"] if task else "",
        "objective": objective,
        "prev_context_id": prev["context_id"] if prev else "",
    }
    state["context_id"] = context_id_of(state)
    return state


def _candidate_contexts(db: Any, state: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(partial: dict[str, Any], family: str, target: str) -> None:
        merged = dict(state)
        merged.update({k: v for k, v in partial.items() if v is not None})
        merged.pop("context_id", None)
        cid = context_id_of(merged)
        if cid in seen:
            return
        seen.add(cid)
        out.append(
            {
                "context_id": cid,
                "family": family,
                "target": target,
                "state": {k: merged.get(k, "") for k in STATE_KEYS},
            }
        )

    add({}, STAY_LABEL, state.get("app") or "")

    if state.get("prev_context_id"):
        row = db.execute(
            """SELECT state_before_json FROM context_episodes
               WHERE context_id=? ORDER BY id DESC LIMIT 1""",
            (state["prev_context_id"],),
        ).fetchone()
        if row:
            try:
                prev_state = json.loads(row["state_before_json"])
            except json.JSONDecodeError:
                prev_state = {}
            add(
                prev_state,
                "resume_previous",
                prev_state.get("app") or state["prev_context_id"],
            )

    for row in db.execute(
        """SELECT app, workspace, monitor FROM hypr_windows
           WHERE app<>'' ORDER BY focused DESC, last_seen DESC LIMIT 24"""
    ):
        if row["app"] == state.get("app") and row["workspace"] == state.get("workspace"):
            continue
        add(
            {"app": row["app"], "workspace": row["workspace"], "monitor": row["monitor"]},
            "switch_app" if row["app"] != state.get("app") else "switch_workspace",
            row["app"] if row["app"] != state.get("app") else row["workspace"],
        )

    for row in db.execute(
        """SELECT harness, state, project, session, window, pane_id, label
           FROM harness_context
           WHERE state IN ('working','waiting','completed','blocked')
           ORDER BY updated_at DESC LIMIT 8"""
    ):
        add(
            {
                "harness": row["harness"],
                "harness_state": row["state"],
                "project": row["project"] or state.get("project") or "",
                "session": row["session"] or state.get("session") or "",
                "window": row["window"] or "",
                "pane": row["pane_id"] or "",
            },
            "inspect_result"
            if row["state"] in {"completed", "waiting", "blocked"}
            else "open_context",
            row["label"] or row["harness"] or row["project"] or "",
        )

    for row in db.execute(
        """SELECT state_after_json, action_family, action_target FROM context_episodes
           WHERE closed=1 AND state_after_json<>'{}'
           ORDER BY id DESC LIMIT 40"""
    ):
        try:
            after = json.loads(row["state_after_json"])
        except json.JSONDecodeError:
            continue
        add(
            after,
            row["action_family"] or "open_context",
            row["action_target"] or after.get("app") or "",
        )

    return out


def predict_next_context_v0(
    db: Any,
    state: dict[str, Any],
    *,
    top_k: int = PRED_TOP_K,
) -> tuple[list[dict[str, Any]], float]:
    """Transition-table predictor. Returns (topk, latency_ms)."""
    t0 = time.perf_counter()
    cid = state.get("context_id") or context_id_of(state)
    cutoff = _now() - LOOKBACK_DAYS * 86400

    next_ids: Counter[str] = Counter()
    after_states: dict[str, dict[str, Any]] = {}
    family_for: dict[str, Counter[str]] = defaultdict(Counter)
    target_for: dict[str, Counter[str]] = defaultdict(Counter)

    # Empirical transitions — also count explicit noop horizons as stay mass.
    rows = db.execute(
        """SELECT action_family, action_target, state_after_json
           FROM context_episodes
           WHERE closed=1 AND ts_after>=? AND context_id=?""",
        (cutoff, cid),
    ).fetchall()
    for row in rows:
        try:
            after = json.loads(row["state_after_json"] or "{}")
        except json.JSONDecodeError:
            after = {}
        nid = context_id_of(after) if after else cid
        next_ids[nid] += 1
        after_states[nid] = after or {k: state.get(k, "") for k in STATE_KEYS}
        fam = row["action_family"] or STAY_LABEL
        family_for[nid][fam] += 1
        target_for[nid][row["action_target"] or after.get("app") or ""] += 1

    # Horizon noop labels feed stay prior.
    noop_n = db.execute(
        """SELECT COUNT(*) AS n FROM prediction_horizons h
           JOIN shadow_predictions p ON p.pred_id=h.pred_id
           WHERE h.closed_at IS NOT NULL AND h.actual_family=?
             AND p.context_id=? AND h.opened_at>=?""",
        (NOOP_LABEL, cid, cutoff),
    ).fetchone()["n"]
    if noop_n:
        next_ids[cid] += int(noop_n)
        after_states.setdefault(cid, {k: state.get(k, "") for k in STATE_KEYS})
        family_for[cid][STAY_LABEL] += int(noop_n)
        target_for[cid][state.get("app") or ""] += int(noop_n)

    candidates = _candidate_contexts(db, state)
    cand_by_id = {c["context_id"]: c for c in candidates}
    vocab = set(next_ids) | set(cand_by_id)
    if not vocab:
        vocab = {cid}
        cand_by_id[cid] = {
            "context_id": cid,
            "family": STAY_LABEL,
            "target": state.get("app") or "",
            "state": {k: state.get(k, "") for k in STATE_KEYS},
        }

    total = sum(next_ids.values())
    alpha = 1.0
    scores: list[tuple[float, str]] = []
    for nid in vocab:
        count = next_ids.get(nid, 0)
        prior = 1.5 if nid == cid else 1.0
        if total >= MIN_TRANSITIONS:
            denom = total + alpha * sum(1.5 if x == cid else 1.0 for x in vocab)
            p = (count + alpha * prior) / denom
        else:
            p = prior / sum(1.5 if x == cid else 1.0 for x in vocab)
        scores.append((p, nid))

    scores.sort(key=lambda item: (-item[0], item[1]))
    topk: list[dict[str, Any]] = []
    for p, nid in scores[:top_k]:
        base = cand_by_id.get(nid)
        if base is None and nid in after_states:
            st = after_states[nid]
            fam_c = family_for[nid].most_common(1)
            tgt_c = target_for[nid].most_common(1)
            base = {
                "context_id": nid,
                "family": fam_c[0][0] if fam_c else "open_context",
                "target": tgt_c[0][0] if tgt_c else st.get("app") or "",
                "state": {k: st.get(k, "") for k in STATE_KEYS},
            }
        if base is None:
            continue
        op = _operator_family(base["family"], base.get("state") or {}, state)
        topk.append(
            {
                "context_id": nid,
                "p": round(float(p), 6),
                "family": base["family"],
                "target": base["target"],
                "operator_family": op,
                "state": base.get("state") or {},
            }
        )

    mass = sum(item["p"] for item in topk) or 1.0
    for item in topk:
        item["p"] = round(item["p"] / mass, 6)

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return topk, latency_ms


def _operator_family(context_family: str, target_state: dict[str, Any], current: dict[str, Any]) -> str:
    if context_family in {STAY_LABEL, NOOP_LABEL}:
        return "noop"
    if context_family == "resume_previous":
        return "resume_previous"
    if context_family == "harness" or target_state.get("harness_state") in {
        "completed",
        "waiting",
        "blocked",
    }:
        return "inspect_result"
    if context_family == "task":
        return "open_context"
    if target_state.get("harness") and target_state.get("harness") != current.get("harness"):
        return "inspect_result"
    if context_family in {"switch_app", "switch_workspace", "switch_pane", "switch_project"}:
        return "open_context"
    return "open_context"


def _z0int_dir(*parts: str) -> Path:
    root = Path(os.environ.get("Z0INT_HOME", Path.home() / ".z0int")).expanduser()
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_json_text(row) + "\n")
    except OSError:
        return


def build_receipt(
    *,
    pred_id: str,
    context_id: str,
    head: str,
    ts: float,
    topk: list[dict[str, Any]],
    latency_ms: float,
    confidence: float,
    margin: float,
    entropy: float,
    prepare: dict[str, Any] | None = None,
    surface: dict[str, Any] | None = None,
    commit: dict[str, Any] | None = None,
    actual: dict[str, Any] | None = None,
    horizons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Canonical flow_prediction.v1 receipt — enough to compute FlowGain later."""
    return {
        "schema": RECEIPT_SCHEMA,
        "prediction_id": pred_id,
        "context_id": context_id,
        "head": head,
        "timestamp": ts,
        "horizons_ms": list(HORIZONS_MS),
        "distribution": [
            {
                "candidate": item.get("context_id"),
                "family": item.get("family"),
                "target": item.get("target"),
                "operator_family": item.get("operator_family"),
                "probability": item.get("p"),
            }
            for item in topk
        ],
        "top_candidate": (topk[0].get("context_id") if topk else None),
        "confidence": confidence,
        "margin": margin,
        "entropy": entropy,
        "prediction_latency_ms": round(float(latency_ms), 3),
        "prepare": prepare
        or {
            "eligible": False,
            "kind": None,
            "started_at": None,
            "ready_at": None,
            "cost_ms": None,
            "bytes": None,
            "cache_hit": False,
        },
        "surface": surface
        or {
            "eligible": False,
            "arm": "ineligible",
            "reason": "",
            "surfaced_at": None,
            "dismissed_at": None,
        },
        "commit": commit
        or {
            "committed": False,
            "source": None,
            "committed_at": None,
        },
        "actual": actual
        or {
            "family": None,
            "target": None,
            "occurred_at": None,
            "rank": None,
            "manual_equivalent": None,
        },
        "horizon_labels": horizons or [],
        "post": {
            "reversal": None,
            "downstream_outcome": None,
            "verified_success": None,
        },
        "utility": {"pending": True},
    }


def gate_prepare(topk: list[dict[str, Any]]) -> tuple[bool, str]:
    """PREPARE gate: often. Stay/noop never prepares."""
    if not topk:
        return False, "empty"
    top = topk[0]
    if top.get("family") in {STAY_LABEL, NOOP_LABEL} or top.get("operator_family") == "noop":
        return False, "noop_top"
    conf = float(top.get("p") or 0.0)
    mar = _margin(topk)
    if conf < PREPARE_MIN_P:
        return False, f"p<{PREPARE_MIN_P}"
    if mar < PREPARE_MIN_MARGIN and conf < 0.55:
        return False, "low_margin"
    return True, "eligible"


def gate_surface(topk: list[dict[str, Any]], *, suppress_fp: str = "") -> tuple[bool, str, str]:
    """SURFACE gate: rare. Returns (eligible, arm, reason).

    arm: shown | withheld | ineligible
    """
    if not topk:
        return False, "ineligible", "empty"
    top = topk[0]
    if top.get("family") in {STAY_LABEL, NOOP_LABEL} or top.get("operator_family") == "noop":
        return False, "ineligible", "noop_top"
    conf = float(top.get("p") or 0.0)
    mar = _margin(topk)
    ent = _entropy([float(x.get("p") or 0.0) for x in topk])
    fp = f"{top.get('family')}|{top.get('target')}|{top.get('context_id')}"
    if suppress_fp and suppress_fp == fp:
        return False, "ineligible", "suppressed"
    if conf < SURFACE_MIN_P:
        return False, "ineligible", f"p<{SURFACE_MIN_P}"
    if mar < SURFACE_MIN_MARGIN:
        return False, "ineligible", "low_margin"
    if ent > SURFACE_MAX_ENTROPY:
        return False, "ineligible", "high_entropy"
    # Counterfactual withhold arm — still eligible, just not shown.
    if random.random() < WITHHOLD_RATE:
        return True, "withheld", "withhold_arm"
    return True, "shown", "eligible"


def _rank_actual(topk: list[dict[str, Any]], actual_cid: str, family: str, target: str) -> int | None:
    ranked = None
    for idx, item in enumerate(topk):
        if item.get("context_id") == actual_cid:
            return idx
        if (
            ranked is None
            and item.get("family") == family
            and item.get("target") == target
            and family
            and family not in {STAY_LABEL, NOOP_LABEL}
        ):
            ranked = idx
    # noop / stay match stay candidate
    if family in {STAY_LABEL, NOOP_LABEL}:
        for idx, item in enumerate(topk):
            if item.get("family") in {STAY_LABEL, NOOP_LABEL} or item.get("operator_family") == "noop":
                return idx
    return ranked


def _close_horizon_row(
    db: Any,
    *,
    pred_id: str,
    horizon_ms: int,
    actual_family: str,
    actual_target: str,
    actual_context_id: str,
    ranked: int | None,
    manual_equivalent: int,
    closed_at: float,
) -> None:
    db.execute(
        """UPDATE prediction_horizons SET
               closed_at=?, actual_family=?, actual_target=?, actual_context_id=?,
               ranked=?, manual_equivalent=?
           WHERE pred_id=? AND horizon_ms=? AND closed_at IS NULL""",
        (
            closed_at,
            actual_family,
            actual_target,
            actual_context_id,
            ranked,
            manual_equivalent,
            pred_id,
            horizon_ms,
        ),
    )
    _append_jsonl(
        _z0int_dir("stream", Z0INT_HORIZON_NAME),
        {
            "schema": "flow_horizon.v1",
            "pred_id": pred_id,
            "horizon_ms": horizon_ms,
            "closed_at": closed_at,
            "actual_family": actual_family,
            "actual_target": actual_target,
            "actual_context_id": actual_context_id,
            "ranked": ranked,
            "manual_equivalent": manual_equivalent,
        },
    )


def label_horizons_on_action(
    db: Any,
    *,
    pred_context_id: str,
    actual_state: dict[str, Any],
    action_family: str,
    action_target: str,
    occurred_at: float | None = None,
) -> int:
    """When a real transition happens, close open horizons for preds from prior context.

    horizon H:
      age_ms <= H → actual = action (action fell inside horizon)
      age_ms >  H → actual = noop   (missed sweep; action outside horizon)
    """
    stamp = occurred_at if occurred_at is not None else _now()
    actual_cid = actual_state.get("context_id") or context_id_of(actual_state)
    # Only label predictions made in the context we're leaving.
    rows = db.execute(
        """SELECT h.pred_id, h.horizon_ms, h.opened_at, p.topk_json
           FROM prediction_horizons h
           JOIN shadow_predictions p ON p.pred_id = h.pred_id
           WHERE h.closed_at IS NULL AND p.context_id=?""",
        (pred_context_id,),
    ).fetchall()
    n = 0
    for row in rows:
        age_ms = max(0.0, (stamp - float(row["opened_at"])) * 1000.0)
        try:
            topk = json.loads(row["topk_json"])
        except json.JSONDecodeError:
            topk = []
        if age_ms <= float(row["horizon_ms"]):
            fam, tgt, acid = action_family, action_target, actual_cid
        else:
            fam, tgt, acid = NOOP_LABEL, "", pred_context_id
        ranked = _rank_actual(topk, acid, fam, tgt)
        manual_eq = 1 if ranked == 0 else 0
        _close_horizon_row(
            db,
            pred_id=row["pred_id"],
            horizon_ms=int(row["horizon_ms"]),
            actual_family=fam,
            actual_target=tgt,
            actual_context_id=acid,
            ranked=ranked,
            manual_equivalent=manual_eq,
            closed_at=stamp,
        )
        n += 1
    return n


def horizon_sweep(db: Any, *, now_ts: float | None = None) -> dict[str, Any]:
    """Close due horizons as noop when still in the same predicted context."""
    stamp = now_ts if now_ts is not None else _now()
    open_rows = db.execute(
        """SELECT h.pred_id, h.horizon_ms, h.opened_at, p.context_id, p.topk_json, p.state_json
           FROM prediction_horizons h
           JOIN shadow_predictions p ON p.pred_id = h.pred_id
           WHERE h.closed_at IS NULL"""
    ).fetchall()
    closed = 0
    for row in open_rows:
        age_ms = (stamp - float(row["opened_at"])) * 1000.0
        if age_ms < float(row["horizon_ms"]):
            continue
        # Still same context? Check live focus against pred state app/workspace lightly.
        try:
            topk = json.loads(row["topk_json"])
        except json.JSONDecodeError:
            topk = []
        ranked = _rank_actual(topk, row["context_id"], NOOP_LABEL, "")
        manual_eq = 1 if ranked == 0 else 0
        _close_horizon_row(
            db,
            pred_id=row["pred_id"],
            horizon_ms=int(row["horizon_ms"]),
            actual_family=NOOP_LABEL,
            actual_target="",
            actual_context_id=row["context_id"],
            ranked=ranked,
            manual_equivalent=manual_eq,
            closed_at=stamp,
        )
        closed += 1

        # If all horizons for this pred closed and no transition matched_at, mark shadow as noop.
        remaining = db.execute(
            "SELECT COUNT(*) AS n FROM prediction_horizons WHERE pred_id=? AND closed_at IS NULL",
            (row["pred_id"],),
        ).fetchone()["n"]
        if remaining == 0:
            sh = db.execute(
                "SELECT matched_at FROM shadow_predictions WHERE pred_id=?",
                (row["pred_id"],),
            ).fetchone()
            if sh and sh["matched_at"] is None:
                db.execute(
                    """UPDATE shadow_predictions SET
                           actual_context_id=?, actual_family=?, actual_target=?,
                           ranked=?, manual_equivalent=?, matched_at=?, horizon_ms=?
                       WHERE pred_id=? AND matched_at IS NULL""",
                    (
                        row["context_id"],
                        NOOP_LABEL,
                        "",
                        ranked,
                        manual_eq,
                        stamp,
                        float(max(HORIZONS_MS)),
                        row["pred_id"],
                    ),
                )
    return {"closed_horizons": closed, "ts": stamp}


def record_shadow_prediction(
    db: Any,
    *,
    state: dict[str, Any],
    topk: list[dict[str, Any]],
    latency_ms: float,
    trigger_event_id: int | None,
    schema_name: str = SCHEMA,
) -> dict[str, Any]:
    pred_id = uuid.uuid4().hex
    ts = _now()
    cid = state.get("context_id") or context_id_of(state)
    conf = float(topk[0]["p"]) if topk else 0.0
    mar = _margin(topk)
    ent = _entropy([float(x.get("p") or 0.0) for x in topk])
    receipt = build_receipt(
        pred_id=pred_id,
        context_id=cid,
        head=schema_name,
        ts=ts,
        topk=topk,
        latency_ms=latency_ms,
        confidence=conf,
        margin=mar,
        entropy=ent,
        horizons=[{"horizon_ms": h, "status": "open"} for h in HORIZONS_MS],
    )
    db.execute(
        """INSERT INTO shadow_predictions(
               pred_id, schema_name, ts, trigger_event_id, context_id,
               state_json, topk_json, latency_ms, confidence, margin, entropy, receipt_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pred_id,
            schema_name,
            ts,
            trigger_event_id,
            cid,
            _json_text(
                {
                    k: state.get(k, "")
                    for k in (*STATE_KEYS, "context_id", "prev_context_id", "objective")
                }
            ),
            _json_text(topk),
            float(latency_ms),
            conf,
            mar,
            ent,
            _json_text(receipt),
        ),
    )
    for h in HORIZONS_MS:
        db.execute(
            """INSERT OR IGNORE INTO prediction_horizons(
                   pred_id, horizon_ms, opened_at
               ) VALUES (?,?,?)""",
            (pred_id, int(h), ts),
        )
    row = {
        "schema": schema_name,
        "pred_id": pred_id,
        "ts": ts,
        "context_id": cid,
        "topk": topk,
        "latency_ms": round(float(latency_ms), 3),
        "confidence": conf,
        "margin": mar,
        "entropy": ent,
        "trigger_event_id": trigger_event_id,
        "receipt": receipt,
    }
    _append_jsonl(_z0int_dir("stream", Z0INT_STREAM_NAME), row)
    _append_jsonl(_z0int_dir("receipts", Z0INT_RECEIPT_NAME), receipt)
    return row


def score_open_predictions(
    db: Any,
    *,
    pred_context_id: str,
    actual_state: dict[str, Any],
    action_family: str,
    action_target: str,
    horizon_ms: float | None,
) -> int:
    """Label unmatched shadow rows for the context being left (transition path)."""
    actual_cid = actual_state.get("context_id") or context_id_of(actual_state)
    stamp = _now()
    open_rows = db.execute(
        """SELECT id, pred_id, topk_json, ts, receipt_json FROM shadow_predictions
           WHERE matched_at IS NULL AND context_id=? ORDER BY id ASC""",
        (pred_context_id,),
    ).fetchall()
    scored = 0
    for row in open_rows:
        try:
            topk = json.loads(row["topk_json"])
        except json.JSONDecodeError:
            topk = []
        ranked = _rank_actual(topk, actual_cid, action_family, action_target)
        manual_eq = 1 if ranked == 0 else 0
        hz = horizon_ms if horizon_ms is not None else max(0.0, (stamp - float(row["ts"])) * 1000.0)
        # Update receipt actual block
        try:
            receipt = json.loads(row["receipt_json"] or "{}")
        except json.JSONDecodeError:
            receipt = {}
        receipt["actual"] = {
            "family": action_family,
            "target": action_target,
            "occurred_at": stamp,
            "rank": ranked,
            "manual_equivalent": manual_eq,
        }
        db.execute(
            """UPDATE shadow_predictions SET
                   actual_context_id=?, actual_family=?, actual_target=?,
                   ranked=?, manual_equivalent=?, matched_at=?, horizon_ms=?,
                   receipt_json=?
               WHERE id=?""",
            (
                actual_cid,
                action_family,
                action_target,
                ranked,
                manual_eq,
                stamp,
                hz,
                _json_text(receipt),
                row["id"],
            ),
        )
        _append_jsonl(_z0int_dir("receipts", Z0INT_RECEIPT_NAME), receipt)
        scored += 1
    # Also close horizons under the survival rule.
    label_horizons_on_action(
        db,
        pred_context_id=pred_context_id,
        actual_state=actual_state,
        action_family=action_family,
        action_target=action_target,
        occurred_at=stamp,
    )
    return scored


def close_open_episode(
    db: Any,
    *,
    after_state: dict[str, Any],
    close_event_id: int | None,
) -> dict[str, Any] | None:
    open_ep = db.execute(
        """SELECT id, context_id, ts_before, state_before_json
           FROM context_episodes WHERE closed=0
           ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    if not open_ep:
        return None
    try:
        before = json.loads(open_ep["state_before_json"])
    except json.JSONDecodeError:
        before = {}
    family, target = action_from_transition(before, after_state)
    ts_after = _now()
    horizon_ms = max(0.0, (ts_after - float(open_ep["ts_before"])) * 1000.0)
    db.execute(
        """UPDATE context_episodes SET
               close_event_id=?, ts_after=?, action_family=?, action_target=?,
               state_after_json=?, horizon_ms=?, closed=1
           WHERE id=?""",
        (
            close_event_id,
            ts_after,
            family,
            target,
            _json_text({k: after_state.get(k, "") for k in (*STATE_KEYS, "context_id")}),
            horizon_ms,
            open_ep["id"],
        ),
    )
    score_open_predictions(
        db,
        pred_context_id=open_ep["context_id"],
        actual_state=after_state,
        action_family=family,
        action_target=target,
        horizon_ms=horizon_ms,
    )
    return {
        "episode_id": open_ep["id"],
        "context_id": open_ep["context_id"],
        "action_family": family,
        "action_target": target,
        "horizon_ms": horizon_ms,
    }


def open_episode(
    db: Any,
    *,
    state: dict[str, Any],
    open_event_id: int | None,
) -> dict[str, Any]:
    cid = state.get("context_id") or context_id_of(state)
    ts = _now()
    cur = db.execute(
        """INSERT INTO context_episodes(
               context_id, open_event_id, ts_before, state_before_json, closed
           ) VALUES (?,?,?,?,0)""",
        (
            cid,
            open_event_id,
            ts,
            _json_text(
                {
                    k: state.get(k, "")
                    for k in (*STATE_KEYS, "context_id", "prev_context_id", "objective")
                }
            ),
        ),
    )
    return {"episode_id": int(cur.lastrowid), "context_id": cid, "ts_before": ts}


def speculative_prepare(
    db: Any,
    *,
    prediction: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Cheap prepare-only work. Never focuses, never mutates the desktop."""
    stamp = _now()
    t0 = time.perf_counter()
    db.execute("DELETE FROM prepare_cache WHERE expires_at<?", (stamp,))
    target_state = prediction.get("state") or {}
    family = prediction.get("family") or ""
    target = prediction.get("target") or ""
    cid = prediction.get("context_id") or ""

    payload: dict[str, Any] = {
        "kind": "context_resolve",
        "context_id": cid,
        "family": family,
        "target": target,
        "operator_family": prediction.get("operator_family") or "",
        "resolved": {},
        "task_summary": None,
        "harness": None,
        "eligible": True,
        "started_at": stamp,
        "cache_hit": False,
    }

    app = target_state.get("app") or (target if family == "switch_app" else "")
    workspace = target_state.get("workspace") or (target if family == "switch_workspace" else "")
    if app:
        row = db.execute(
            """SELECT app, workspace, monitor, process, focus_count, last_seen
               FROM hypr_windows WHERE app=?
               ORDER BY focused DESC, last_seen DESC LIMIT 1""",
            (app,),
        ).fetchone()
        if row:
            payload["resolved"]["hypr"] = dict(row)
            payload["resolved"]["dispatch"] = {
                "action": "focus_app",
                "app": row["app"],
                "workspace": row["workspace"],
            }

    if workspace and "dispatch" not in payload["resolved"]:
        payload["resolved"]["dispatch"] = {
            "action": "focus_workspace",
            "workspace": workspace,
        }

    session = target_state.get("session") or ""
    pane = target_state.get("pane") or ""
    if session or pane:
        q = "SELECT pane_id, session, window_id, window_index, window_name, command, project, active FROM tmux_panes WHERE 1=1"
        params: list[Any] = []
        if pane:
            q += " AND pane_id=?"
            params.append(pane)
        elif session:
            q += " AND session=? AND active=1"
            params.append(session)
        q += " ORDER BY last_seen DESC LIMIT 1"
        row = db.execute(q, params).fetchone()
        if row:
            payload["resolved"]["tmux"] = dict(row)
            payload["resolved"]["dispatch"] = {
                "action": "select_tmux_pane",
                "pane_id": row["pane_id"],
                "session": row["session"],
            }

    if current.get("task") or target_state.get("task"):
        task_row = db.execute(
            """SELECT session, phase, task, status, project, updated_at
               FROM task_context
               ORDER BY updated_at DESC LIMIT 3"""
        ).fetchall()
        payload["task_summary"] = [dict(r) for r in task_row]

    harness_rows = db.execute(
        """SELECT pane_id, harness, state, session, project, label, updated_at
           FROM harness_context ORDER BY updated_at DESC LIMIT 5"""
    ).fetchall()
    if harness_rows:
        payload["harness"] = [dict(r) for r in harness_rows]

    cost_ms = (time.perf_counter() - t0) * 1000.0
    ready_at = _now()
    blob = _json_text(payload)
    payload["ready_at"] = ready_at
    payload["cost_ms"] = round(cost_ms, 3)
    payload["bytes"] = len(blob)

    key = f"prep:{cid}:{family}:{target}"[:200]
    db.execute(
        """INSERT INTO prepare_cache(cache_key, kind, created_at, expires_at, payload_json)
           VALUES (?,?,?,?,?)
           ON CONFLICT(cache_key) DO UPDATE SET
               created_at=excluded.created_at,
               expires_at=excluded.expires_at,
               payload_json=excluded.payload_json""",
        (key, "context_resolve", stamp, stamp + PREPARE_TTL_S, blob),
    )
    payload["cache_key"] = key
    payload["expires_at"] = stamp + PREPARE_TTL_S
    return payload


def _surface_summary(pred: dict[str, Any]) -> str:
    op = pred.get("operator_family") or pred.get("family") or "open_context"
    target = pred.get("target") or pred.get("context_id") or "context"
    labels = {
        "inspect_result": f"Inspect {target}",
        "resume_previous": f"Resume previous · {target}",
        "open_context": f"Open {target}",
        "switch_app": f"Switch to {target}",
        "switch_workspace": f"Workspace {target}",
        "switch_pane": f"Pane {target}",
        "run_test": f"Run tests · {target}",
        "delegate": f"Delegate · {target}",
        "retrieve": f"Retrieve · {target}",
        "noop": "Stay",
        STAY_LABEL: "Stay",
        NOOP_LABEL: "Stay",
    }
    return labels.get(op) or labels.get(pred.get("family") or "") or f"{op} · {target}"


def update_next_action_surface(
    db: Any,
    *,
    pred_row: dict[str, Any],
    topk: list[dict[str, Any]],
    prepare: dict[str, Any] | None,
) -> dict[str, Any]:
    """SURFACE gate only. Never steals focus. Withhold arm for counterfactuals."""
    surface = db.execute("SELECT * FROM next_action_surface WHERE id=1").fetchone()
    suppress = surface["suppress_fingerprint"] if surface else ""
    eligible, arm, reason = gate_surface(topk, suppress_fp=suppress)
    conf = float(topk[0]["p"]) if topk else 0.0
    top = topk[0] if topk else {}
    stamp = _now()

    # Update receipt surface block on the prediction.
    pred_id = pred_row.get("pred_id") or ""
    if pred_id:
        row = db.execute(
            "SELECT receipt_json FROM shadow_predictions WHERE pred_id=?", (pred_id,)
        ).fetchone()
        if row:
            try:
                receipt = json.loads(row["receipt_json"] or "{}")
            except json.JSONDecodeError:
                receipt = {}
            receipt["prepare"] = prepare or receipt.get("prepare")
            receipt["surface"] = {
                "eligible": eligible,
                "arm": arm,
                "reason": reason,
                "surfaced_at": stamp if arm == "shown" else None,
                "dismissed_at": None,
            }
            db.execute(
                "UPDATE shadow_predictions SET receipt_json=? WHERE pred_id=?",
                (_json_text(receipt), pred_id),
            )
            _append_jsonl(_z0int_dir("receipts", Z0INT_RECEIPT_NAME), receipt)

    if arm != "shown":
        # Keep prepare payload for withhold/ineligible so commit path can still
        # be studied offline; UI stays idle/empty.
        db.execute(
            """UPDATE next_action_surface SET
                   updated_at=?, pred_id=?, summary='', action_family='',
                   action_target='', target_context_id='', prepare_json=?,
                   status=?, suppress_fingerprint=?, confidence=?,
                   surface_arm=?, surface_reason=?
               WHERE id=1""",
            (
                stamp,
                pred_id,
                _json_text(prepare or {}),
                "suppressed" if (surface and surface["status"] == "suppressed" and suppress) else "idle",
                suppress or "",
                conf,
                arm,
                reason,
            ),
        )
        return show_next_action(db)

    summary = _surface_summary(top)
    db.execute(
        """UPDATE next_action_surface SET
               updated_at=?, pred_id=?, summary=?, action_family=?,
               action_target=?, target_context_id=?, prepare_json=?,
               status='ready', suppress_fingerprint='', confidence=?,
               surface_arm=?, surface_reason=?
           WHERE id=1""",
        (
            stamp,
            pred_id,
            summary,
            top.get("operator_family") or top.get("family") or "",
            top.get("target") or "",
            top.get("context_id") or "",
            _json_text(prepare or {}),
            conf,
            arm,
            reason,
        ),
    )
    return show_next_action(db)


def show_next_action(db: Any) -> dict[str, Any]:
    row = db.execute("SELECT * FROM next_action_surface WHERE id=1").fetchone()
    if not row:
        return {"status": "idle", "summary": "", "contract": _contract()}
    prepare = {}
    try:
        prepare = json.loads(row["prepare_json"] or "{}")
    except json.JSONDecodeError:
        prepare = {}
    arm = row["surface_arm"] if "surface_arm" in row.keys() else "ineligible"
    reason = row["surface_reason"] if "surface_reason" in row.keys() else ""
    return {
        "status": row["status"],
        "summary": row["summary"],
        "action_family": row["action_family"],
        "action_target": row["action_target"],
        "target_context_id": row["target_context_id"],
        "pred_id": row["pred_id"],
        "confidence": row["confidence"],
        "updated_at": row["updated_at"],
        "prepare": prepare,
        "surface_arm": arm,
        "surface_reason": reason,
        "commit_binding": "Super+Space",
        "dismiss_binding": "Esc",
        "contract": _contract(),
        "gates": {
            "predict": "always",
            "prepare_min_p": PREPARE_MIN_P,
            "surface_min_p": SURFACE_MIN_P,
            "surface_min_margin": SURFACE_MIN_MARGIN,
            "withhold_rate": WITHHOLD_RATE,
            "commit": "explicit-only",
        },
    }


def _contract() -> dict[str, Any]:
    return {
        "focus_policy": "never-steal-focus",
        "open_budget_ms": 150,
        "duplicate_controls": "forbidden",
        "interaction": "explicit-invocation",
        "dismissal": "dont-remind-until-evidence-changes",
        "mode": "predict-prepare-surface-commit",
        "horizons_ms": list(HORIZONS_MS),
        "receipt_schema": RECEIPT_SCHEMA,
    }


def dismiss_next_action(db: Any) -> dict[str, Any]:
    row = db.execute("SELECT * FROM next_action_surface WHERE id=1").fetchone()
    if not row:
        return {"status": "idle"}
    fingerprint = f"{row['action_family']}|{row['action_target']}|{row['target_context_id']}"
    stamp = _now()
    db.execute(
        """UPDATE next_action_surface SET
               status='suppressed', suppress_fingerprint=?, updated_at=?,
               surface_arm='ineligible', surface_reason='dismissed'
           WHERE id=1""",
        (fingerprint, stamp),
    )
    if row["pred_id"]:
        r = db.execute(
            "SELECT receipt_json FROM shadow_predictions WHERE pred_id=?",
            (row["pred_id"],),
        ).fetchone()
        if r:
            try:
                receipt = json.loads(r["receipt_json"] or "{}")
            except json.JSONDecodeError:
                receipt = {}
            surface = receipt.get("surface") or {}
            surface["dismissed_at"] = stamp
            surface["arm"] = "ineligible"
            surface["reason"] = "dismissed"
            receipt["surface"] = surface
            db.execute(
                "UPDATE shadow_predictions SET receipt_json=? WHERE pred_id=?",
                (_json_text(receipt), row["pred_id"]),
            )
            _append_jsonl(_z0int_dir("receipts", Z0INT_RECEIPT_NAME), receipt)
    return show_next_action(db)


def commit_next_action(
    db: Any,
    *,
    run_fn: Callable[[list[str]], Any],
    tmux_args_fn: Callable[..., list[str]],
    source: str = "flow",
) -> dict[str, Any]:
    """COMMIT gate: explicit only. Reversible navigation from prepared surface."""
    surface = show_next_action(db)
    if surface.get("status") != "ready":
        return {"ok": False, "error": "no ready next-action", "surface": surface}

    prepare = surface.get("prepare") or {}
    resolved = prepare.get("resolved") or {}
    dispatch = resolved.get("dispatch") or {}
    action = dispatch.get("action")
    message = ""
    undo: dict[str, Any] = {"action": "none"}

    cur = db.execute(
        """SELECT app, workspace FROM hypr_windows WHERE focused=1
           ORDER BY last_seen DESC LIMIT 1"""
    ).fetchone()
    if cur:
        undo = {"action": "focus_app", "app": cur["app"], "workspace": cur["workspace"]}

    if action == "focus_workspace":
        ws = str(dispatch.get("workspace") or "")
        if not ws:
            return {"ok": False, "error": "missing workspace", "surface": surface}
        result = run_fn(["hyprctl", "dispatch", "workspace", ws])
        if getattr(result, "returncode", 1) != 0:
            return {
                "ok": False,
                "error": getattr(result, "stderr", "") or "hyprctl failed",
                "surface": surface,
            }
        message = f"focused workspace {ws}"
    elif action == "focus_app":
        app = str(dispatch.get("app") or "")
        ws = str(dispatch.get("workspace") or "")
        if ws:
            run_fn(["hyprctl", "dispatch", "workspace", ws])
        if app:
            result = run_fn(["hyprctl", "dispatch", "focuswindow", f"class:^{app}$"])
            if getattr(result, "returncode", 1) != 0 and not ws:
                return {
                    "ok": False,
                    "error": getattr(result, "stderr", "") or "focuswindow failed",
                    "surface": surface,
                }
            message = f"focused {app}" + (f" on workspace {ws}" if ws else "")
        else:
            return {"ok": False, "error": "missing app", "surface": surface}
    elif action == "select_tmux_pane":
        pane = str(dispatch.get("pane_id") or "")
        if not pane:
            return {"ok": False, "error": "missing pane", "surface": surface}
        result = run_fn(tmux_args_fn("select-pane", "-t", pane))
        if getattr(result, "returncode", 1) != 0:
            return {
                "ok": False,
                "error": getattr(result, "stderr", "") or "tmux select-pane failed",
                "surface": surface,
            }
        message = f"selected tmux pane {pane}"
    else:
        return {
            "ok": False,
            "error": f"action not allowlisted for commit: {action or 'none'}",
            "surface": surface,
        }

    stamp = _now()
    db.execute(
        """UPDATE next_action_surface SET status='committed', updated_at=? WHERE id=1""",
        (stamp,),
    )
    pred_id = surface.get("pred_id") or ""
    if pred_id:
        r = db.execute(
            "SELECT receipt_json FROM shadow_predictions WHERE pred_id=?", (pred_id,)
        ).fetchone()
        if r:
            try:
                receipt = json.loads(r["receipt_json"] or "{}")
            except json.JSONDecodeError:
                receipt = {}
            receipt["commit"] = {
                "committed": True,
                "source": source,
                "committed_at": stamp,
            }
            db.execute(
                "UPDATE shadow_predictions SET receipt_json=? WHERE pred_id=?",
                (_json_text(receipt), pred_id),
            )
            _append_jsonl(_z0int_dir("receipts", Z0INT_RECEIPT_NAME), receipt)

    return {
        "ok": True,
        "result": message,
        "undo": undo,
        "source": source,
        "surface": show_next_action(db),
        "pred_id": pred_id,
    }


def on_context_event(
    db: Any,
    *,
    event_id: int | None,
    kind: str,
    tmux_focus_fn: Callable[[], dict[str, str]] | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    """Core tick: horizons, episode join, PREDICT→PREPARE→SURFACE gates."""
    # Always sweep due horizons (noop labels) even on non-trigger events.
    sweep = horizon_sweep(db)

    if not force and kind not in CONTEXT_TRIGGER_KINDS and not kind.startswith("activewindow"):
        return {"horizon_sweep": sweep} if sweep.get("closed_horizons") else None

    state = semantic_state(db, tmux_focus_fn=tmux_focus_fn)
    last = db.execute("SELECT value FROM flow_meta WHERE key='last_context_id'").fetchone()
    last_cid = last["value"] if last else ""
    cid = state["context_id"]

    transitioned = force or (last_cid and last_cid != cid) or not last_cid
    result: dict[str, Any] = {
        "context_id": cid,
        "transitioned": bool(transitioned),
        "kind": kind,
        "horizon_sweep": sweep,
        "gates": {},
    }

    if transitioned and last_cid and last_cid != cid:
        closed = close_open_episode(db, after_state=state, close_event_id=event_id)
        result["closed_episode"] = closed

    if transitioned:
        open_row = db.execute(
            "SELECT id, context_id FROM context_episodes WHERE closed=0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not open_row or open_row["context_id"] != cid:
            if open_row:
                close_open_episode(db, after_state=state, close_event_id=event_id)
            opened = open_episode(db, state=state, open_event_id=event_id)
            result["opened_episode"] = opened

        # PREDICT — always
        topk, latency_ms = predict_next_context_v0(db, state)
        pred = record_shadow_prediction(
            db,
            state=state,
            topk=topk,
            latency_ms=latency_ms,
            trigger_event_id=event_id,
            schema_name=SCHEMA,
        )
        result["gates"]["predict"] = {
            "ran": True,
            "latency_ms": pred["latency_ms"],
            "confidence": pred["confidence"],
            "margin": pred["margin"],
            "entropy": pred["entropy"],
        }

        # PREPARE — often
        prep_ok, prep_reason = gate_prepare(topk)
        prepare = None
        if prep_ok:
            prepare = speculative_prepare(db, prediction=topk[0], current=state)
        result["gates"]["prepare"] = {
            "eligible": prep_ok,
            "reason": prep_reason,
            "cost_ms": (prepare or {}).get("cost_ms"),
        }

        # SURFACE — rarely (+ withhold arm)
        surface = update_next_action_surface(
            db, pred_row=pred, topk=topk, prepare=prepare
        )
        result["gates"]["surface"] = {
            "arm": surface.get("surface_arm"),
            "reason": surface.get("surface_reason"),
            "status": surface.get("status"),
        }
        result["gates"]["commit"] = {"policy": "explicit-only"}

        result["prediction"] = {
            "pred_id": pred["pred_id"],
            "latency_ms": pred["latency_ms"],
            "topk": topk,
            "confidence": pred["confidence"],
            "margin": pred["margin"],
            "entropy": pred["entropy"],
        }
        result["surface"] = {
            "status": surface.get("status"),
            "summary": surface.get("summary"),
            "confidence": surface.get("confidence"),
            "arm": surface.get("surface_arm"),
            "reason": surface.get("surface_reason"),
        }
        db.execute(
            "INSERT OR REPLACE INTO flow_meta(key,value) VALUES('last_context_id',?)",
            (cid,),
        )
        db.execute(
            "INSERT OR REPLACE INTO flow_meta(key,value) VALUES('last_pred_id',?)",
            (pred["pred_id"],),
        )
    return result


def shadow_stats(db: Any, *, limit_hours: float = 24.0) -> dict[str, Any]:
    cutoff = _now() - limit_hours * 3600.0
    total = db.execute(
        "SELECT COUNT(*) AS n FROM shadow_predictions WHERE ts>=?", (cutoff,)
    ).fetchone()["n"]
    matched = db.execute(
        """SELECT COUNT(*) AS n FROM shadow_predictions
           WHERE ts>=? AND matched_at IS NOT NULL""",
        (cutoff,),
    ).fetchone()["n"]
    top1 = db.execute(
        """SELECT COUNT(*) AS n FROM shadow_predictions
           WHERE ts>=? AND manual_equivalent=1""",
        (cutoff,),
    ).fetchone()["n"]
    topk_hit = db.execute(
        """SELECT COUNT(*) AS n FROM shadow_predictions
           WHERE ts>=? AND ranked IS NOT NULL""",
        (cutoff,),
    ).fetchone()["n"]
    noop_n = db.execute(
        """SELECT COUNT(*) AS n FROM shadow_predictions
           WHERE ts>=? AND actual_family=?""",
        (cutoff, NOOP_LABEL),
    ).fetchone()["n"]
    lat = db.execute(
        """SELECT AVG(latency_ms) AS avg_ms, MAX(latency_ms) AS max_ms,
                  MIN(latency_ms) AS min_ms
           FROM shadow_predictions WHERE ts>=?""",
        (cutoff,),
    ).fetchone()
    horizons = [
        dict(r)
        for r in db.execute(
            """SELECT horizon_ms,
                      SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END) AS closed,
                      SUM(CASE WHEN actual_family=? THEN 1 ELSE 0 END) AS noop,
                      SUM(CASE WHEN manual_equivalent=1 THEN 1 ELSE 0 END) AS top1,
                      COUNT(*) AS n
               FROM prediction_horizons
               WHERE opened_at>=?
               GROUP BY horizon_ms ORDER BY horizon_ms""",
            (NOOP_LABEL, cutoff),
        )
    ]
    surface_arms = [
        dict(r)
        for r in db.execute(
            """SELECT
                  json_extract(receipt_json, '$.surface.arm') AS arm,
                  COUNT(*) AS n
               FROM shadow_predictions
               WHERE ts>=?
               GROUP BY arm""",
            (cutoff,),
        )
    ]
    episodes = db.execute(
        """SELECT COUNT(*) AS n FROM context_episodes
           WHERE ts_before>=? AND closed=1""",
        (cutoff,),
    ).fetchone()["n"]
    by_family = [
        dict(r)
        for r in db.execute(
            """SELECT action_family AS family, COUNT(*) AS n
               FROM context_episodes
               WHERE ts_before>=? AND closed=1
               GROUP BY action_family ORDER BY n DESC""",
            (cutoff,),
        )
    ]
    return {
        "schema": SCHEMA,
        "receipt_schema": RECEIPT_SCHEMA,
        "operator_schema": OPERATOR_SCHEMA,
        "operator_families": list(OPERATOR_FAMILIES),
        "horizons_ms": list(HORIZONS_MS),
        "window_hours": limit_hours,
        "predictions": total,
        "matched": matched,
        "noop_matched": noop_n,
        "top1_manual_equivalent": top1,
        "topk_hit": topk_hit,
        "top1_rate": round(top1 / matched, 4) if matched else None,
        "topk_rate": round(topk_hit / matched, 4) if matched else None,
        "noop_rate": round(noop_n / matched, 4) if matched else None,
        "latency_ms": {
            "avg": round(float(lat["avg_ms"] or 0.0), 3),
            "min": round(float(lat["min_ms"] or 0.0), 3),
            "max": round(float(lat["max_ms"] or 0.0), 3),
        },
        "horizon_labels": horizons,
        "surface_arms": surface_arms,
        "closed_episodes": episodes,
        "action_families": by_family,
        "gates": {
            "prepare_min_p": PREPARE_MIN_P,
            "surface_min_p": SURFACE_MIN_P,
            "surface_min_margin": SURFACE_MIN_MARGIN,
            "surface_max_entropy": SURFACE_MAX_ENTROPY,
            "withhold_rate": WITHHOLD_RATE,
        },
        "surface": show_next_action(db),
    }


def export_episodes_jsonl(db: Any, dest: Path, *, limit: int = 50000) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", encoding="utf-8") as fh:
        rows = db.execute(
            """SELECT id, context_id, ts_before, ts_after, action_family, action_target,
                      state_before_json, state_after_json, horizon_ms, closed
               FROM context_episodes
               WHERE closed=1
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
        for row in rows:
            try:
                before = json.loads(row["state_before_json"])
                after = json.loads(row["state_after_json"] or "{}")
            except json.JSONDecodeError:
                continue
            rec = {
                "schema": "os.context_episode.v0",
                "episode_id": row["id"],
                "context_id": row["context_id"],
                "ts_before": row["ts_before"],
                "ts_after": row["ts_after"],
                "action_family": row["action_family"],
                "action_target": row["action_target"],
                "horizon_ms": row["horizon_ms"],
                "state_before": before,
                "state_after": after,
            }
            fh.write(_json_text(rec) + "\n")
            n += 1
    return {"path": str(dest), "n": n, "schema": "os.context_episode.v0"}


def export_shadow_jsonl(db: Any, dest: Path, *, limit: int = 50000) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", encoding="utf-8") as fh:
        rows = db.execute(
            """SELECT pred_id, schema_name, ts, context_id, state_json, topk_json,
                      latency_ms, confidence, margin, entropy, receipt_json,
                      actual_context_id, actual_family, actual_target,
                      ranked, manual_equivalent, matched_at, horizon_ms
               FROM shadow_predictions
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
        for row in rows:
            try:
                state = json.loads(row["state_json"])
                topk = json.loads(row["topk_json"])
                receipt = json.loads(row["receipt_json"] or "{}")
            except json.JSONDecodeError:
                continue
            hz = [
                dict(h)
                for h in db.execute(
                    """SELECT horizon_ms, closed_at, actual_family, actual_target,
                              actual_context_id, ranked, manual_equivalent
                       FROM prediction_horizons WHERE pred_id=? ORDER BY horizon_ms""",
                    (row["pred_id"],),
                )
            ]
            rec = {
                "schema": row["schema_name"],
                "receipt_schema": RECEIPT_SCHEMA,
                "pred_id": row["pred_id"],
                "ts": row["ts"],
                "context_id": row["context_id"],
                "state": state,
                "topk": topk,
                "latency_ms": row["latency_ms"],
                "confidence": row["confidence"],
                "margin": row["margin"],
                "entropy": row["entropy"],
                "actual_context_id": row["actual_context_id"],
                "actual_family": row["actual_family"],
                "actual_target": row["actual_target"],
                "ranked": row["ranked"],
                "manual_equivalent": row["manual_equivalent"],
                "matched_at": row["matched_at"],
                "horizon_ms": row["horizon_ms"],
                "horizons": hz,
                "receipt": receipt,
            }
            fh.write(_json_text(rec) + "\n")
            n += 1
    return {"path": str(dest), "n": n, "schema": SCHEMA}


def cleanup_flow(db: Any, cutoff: float) -> None:
    db.execute("DELETE FROM context_episodes WHERE ts_before<?", (cutoff,))
    # orphan horizons first
    db.execute(
        """DELETE FROM prediction_horizons WHERE pred_id IN (
               SELECT pred_id FROM shadow_predictions WHERE ts<?
           )""",
        (cutoff,),
    )
    db.execute("DELETE FROM shadow_predictions WHERE ts<?", (cutoff,))
    db.execute("DELETE FROM prepare_cache WHERE expires_at<?", (_now(),))
