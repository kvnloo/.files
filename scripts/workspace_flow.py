#!/usr/bin/env python3
"""Flow predictor substrate for workspace-copilot.

OS branch-predictor layer:
  event → update state → shadow-predict next context → speculative prepare → user commits

Privacy contract inherited from workspace-copilot:
  semantic events only; no keystrokes, titles, pane text, clipboard, screenshots.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

SCHEMA = "os.next_context.v0"
OPERATOR_SCHEMA = "os.next_operator.v0"
SURFACE_ID = 1

# Families for the second head (operator intents). Factor family × target later.
OPERATOR_FAMILIES = (
    "inspect_result",
    "run_test",
    "open_context",
    "delegate",
    "retrieve",
    "resume_previous",
    "noop",
)

# Context transitions that close/open episodes (identity change only).
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
HISTORY_EVENTS = 8
LOOKBACK_DAYS = 21
MIN_TRANSITIONS = 3
SURFACE_MIN_P = 0.42
PREPARE_TTL_S = 180.0
STAY_LABEL = "stay"
Z0INT_STREAM_NAME = "os_next_context.jsonl"


def _now() -> float:
    return time.time()


def _json_text(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def ensure_flow_schema(db: Any) -> None:
    """Idempotent tables for episodes, shadow preds, surface, prepare cache."""
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
            horizon_ms REAL
        );
        CREATE INDEX IF NOT EXISTS shadow_predictions_open
            ON shadow_predictions(matched_at, ts);
        CREATE INDEX IF NOT EXISTS shadow_predictions_schema
            ON shadow_predictions(schema_name, ts);

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
            confidence REAL NOT NULL DEFAULT 0
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
    if before.get("session") != after.get("session") or before.get("pane") != after.get("pane") or before.get("window") != after.get("window"):
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
        # Keep short; already published as semantic task state.
        objective = str(session_row["objective"])[:80]

    state = {
        "app": app or "",
        "workspace": workspace or "",
        "monitor": monitor or "",
        "session": (focus.get("session") or (harness["session"] if harness else "") or (task["session"] if task else "") or ""),
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
    """Enumerate likely next contexts without raw private content."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(partial: dict[str, Any], family: str, target: str) -> None:
        merged = dict(state)
        merged.update({k: v for k, v in partial.items() if v is not None})
        # Drop identity-derived fields that must recompute.
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

    # Stay
    add({}, STAY_LABEL, state.get("app") or "")

    # Previous context (resume)
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
            add(prev_state, "resume_previous", prev_state.get("app") or state["prev_context_id"])

    # Live hypr windows
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

    # Active harness targets
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
            "inspect_result" if row["state"] in {"completed", "waiting", "blocked"} else "open_context",
            row["label"] or row["harness"] or row["project"] or "",
        )

    # Recent distinct destinations from episodes
    for row in db.execute(
        """SELECT state_after_json, action_family, action_target FROM context_episodes
           WHERE closed=1 AND state_after_json<>'{}'
           ORDER BY id DESC LIMIT 40"""
    ):
        try:
            after = json.loads(row["state_after_json"])
        except json.JSONDecodeError:
            continue
        add(after, row["action_family"] or "open_context", row["action_target"] or after.get("app") or "")

    return out


def predict_next_context_v0(
    db: Any,
    state: dict[str, Any],
    *,
    top_k: int = PRED_TOP_K,
) -> tuple[list[dict[str, Any]], float]:
    """Embarrassingly simple transition-table predictor. Returns (topk, latency_ms)."""
    t0 = time.perf_counter()
    cid = state.get("context_id") or context_id_of(state)
    cutoff = _now() - LOOKBACK_DAYS * 86400

    # Empirical P(next_context_id | current_context_id)
    transitions: Counter[str] = Counter()
    family_for: dict[str, Counter[str]] = defaultdict(Counter)
    target_for: dict[str, Counter[str]] = defaultdict(Counter)
    rows = db.execute(
        """SELECT context_id,
                  json_extract(state_after_json, '$.app') AS after_app,
                  action_family, action_target, state_after_json
           FROM context_episodes
           WHERE closed=1 AND ts_after>=? AND context_id=?""",
        (cutoff, cid),
    ).fetchall()

    next_ids: Counter[str] = Counter()
    after_states: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            after = json.loads(row["state_after_json"] or "{}")
        except json.JSONDecodeError:
            after = {}
        nid = context_id_of(after) if after else ""
        if not nid:
            continue
        next_ids[nid] += 1
        after_states[nid] = after
        fam = row["action_family"] or STAY_LABEL
        family_for[nid][fam] += 1
        target_for[nid][row["action_target"] or after.get("app") or ""] += 1

    candidates = _candidate_contexts(db, state)
    cand_by_id = {c["context_id"]: c for c in candidates}

    # Laplace-smoothed scores over observed + live candidates
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
    n = len(vocab)
    for nid in vocab:
        count = next_ids.get(nid, 0)
        # Prefer empirical mass; give stay a mild prior when data is thin
        prior = 1.5 if nid == cid else 1.0
        if total >= MIN_TRANSITIONS:
            p = (count + alpha * prior) / (total + alpha * sum(1.5 if x == cid else 1.0 for x in vocab))
        else:
            # Cold start: recency/heuristic — stay + live windows roughly equal
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
        # Operator family head (coarse): map context family → operator family
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

    # Renormalize displayed top-k for readability
    mass = sum(item["p"] for item in topk) or 1.0
    for item in topk:
        item["p"] = round(item["p"] / mass, 6)

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return topk, latency_ms


def _operator_family(context_family: str, target_state: dict[str, Any], current: dict[str, Any]) -> str:
    if context_family == STAY_LABEL:
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


def _append_z0int_shadow(row: dict[str, Any]) -> None:
    """Best-effort dual-write into ~/.z0int/stream (local vault only)."""
    root = Path(os.environ.get("Z0INT_HOME", Path.home() / ".z0int")).expanduser()
    stream = root / "stream"
    try:
        stream.mkdir(parents=True, exist_ok=True)
        path = stream / Z0INT_STREAM_NAME
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_json_text(row) + "\n")
    except OSError:
        return


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
    db.execute(
        """INSERT INTO shadow_predictions(
               pred_id, schema_name, ts, trigger_event_id, context_id,
               state_json, topk_json, latency_ms
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            pred_id,
            schema_name,
            ts,
            trigger_event_id,
            cid,
            _json_text({k: state.get(k, "") for k in (*STATE_KEYS, "context_id", "prev_context_id", "objective")}),
            _json_text(topk),
            float(latency_ms),
        ),
    )
    row = {
        "schema": schema_name,
        "pred_id": pred_id,
        "ts": ts,
        "context_id": cid,
        "topk": topk,
        "latency_ms": round(float(latency_ms), 3),
        "trigger_event_id": trigger_event_id,
    }
    _append_z0int_shadow(row)
    return row


def score_open_predictions(
    db: Any,
    *,
    actual_state: dict[str, Any],
    action_family: str,
    action_target: str,
    horizon_ms: float | None,
) -> int:
    """Label unmatched shadow rows against the observed next context."""
    actual_cid = actual_state.get("context_id") or context_id_of(actual_state)
    open_rows = db.execute(
        """SELECT id, pred_id, topk_json, ts FROM shadow_predictions
           WHERE matched_at IS NULL ORDER BY id ASC"""
    ).fetchall()
    scored = 0
    stamp = _now()
    for row in open_rows:
        try:
            topk = json.loads(row["topk_json"])
        except json.JSONDecodeError:
            topk = []
        ranked = None
        for idx, item in enumerate(topk):
            if item.get("context_id") == actual_cid:
                ranked = idx
                break
            # Soft match: same family+target
            if (
                ranked is None
                and item.get("family") == action_family
                and item.get("target") == action_target
                and action_family
            ):
                ranked = idx
        manual_eq = 1 if ranked == 0 else 0
        hz = horizon_ms if horizon_ms is not None else max(0.0, (stamp - float(row["ts"])) * 1000.0)
        db.execute(
            """UPDATE shadow_predictions SET
                   actual_context_id=?, actual_family=?, actual_target=?,
                   ranked=?, manual_equivalent=?, matched_at=?, horizon_ms=?
               WHERE id=?""",
            (
                actual_cid,
                action_family,
                action_target,
                ranked,
                manual_eq,
                stamp,
                hz,
                row["id"],
            ),
        )
        scored += 1
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
            _json_text({k: state.get(k, "") for k in (*STATE_KEYS, "context_id", "prev_context_id", "objective")}),
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
    }

    # Pre-resolve matching hypr window row (hashed identity only).
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

    # Tmux pane pre-resolve (ids only).
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

    # Task / harness packets (already semantic).
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

    key = f"prep:{cid}:{family}:{target}"[:200]
    db.execute(
        """INSERT INTO prepare_cache(cache_key, kind, created_at, expires_at, payload_json)
           VALUES (?,?,?,?,?)
           ON CONFLICT(cache_key) DO UPDATE SET
               created_at=excluded.created_at,
               expires_at=excluded.expires_at,
               payload_json=excluded.payload_json""",
        (key, "context_resolve", stamp, stamp + PREPARE_TTL_S, _json_text(payload)),
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
    }
    return labels.get(op) or labels.get(pred.get("family") or "") or f"{op} · {target}"


def update_next_action_surface(
    db: Any,
    *,
    pred_row: dict[str, Any],
    topk: list[dict[str, Any]],
    prepare: dict[str, Any] | None,
) -> dict[str, Any]:
    """Single global prediction surface. Never steals focus."""
    surface = db.execute("SELECT * FROM next_action_surface WHERE id=1").fetchone()
    suppress = surface["suppress_fingerprint"] if surface else ""
    status = surface["status"] if surface else "idle"

    top = topk[0] if topk else None
    if not top or top.get("family") == STAY_LABEL or top.get("operator_family") == "noop":
        # Nothing useful to show.
        if status not in {"suppressed"}:
            db.execute(
                """UPDATE next_action_surface SET
                       updated_at=?, pred_id=?, summary='', action_family='',
                       action_target='', target_context_id='', prepare_json='{}',
                       status='idle', confidence=0
                   WHERE id=1""",
                (_now(), pred_row.get("pred_id") or ""),
            )
        return show_next_action(db)

    fingerprint = f"{top.get('family')}|{top.get('target')}|{top.get('context_id')}"
    if status == "suppressed" and suppress == fingerprint:
        return show_next_action(db)

    conf = float(top.get("p") or 0.0)
    if conf < SURFACE_MIN_P:
        db.execute(
            """UPDATE next_action_surface SET
                   updated_at=?, pred_id=?, summary='', action_family='',
                   action_target='', target_context_id='', prepare_json=?,
                   status='idle', confidence=?
               WHERE id=1""",
            (
                _now(),
                pred_row.get("pred_id") or "",
                _json_text(prepare or {}),
                conf,
            ),
        )
        return show_next_action(db)

    summary = _surface_summary(top)
    db.execute(
        """UPDATE next_action_surface SET
               updated_at=?, pred_id=?, summary=?, action_family=?,
               action_target=?, target_context_id=?, prepare_json=?,
               status='ready', suppress_fingerprint='', confidence=?
           WHERE id=1""",
        (
            _now(),
            pred_row.get("pred_id") or "",
            summary,
            top.get("operator_family") or top.get("family") or "",
            top.get("target") or "",
            top.get("context_id") or "",
            _json_text(prepare or {}),
            conf,
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
        "commit_binding": "Super+Space",
        "dismiss_binding": "Esc",
        "contract": _contract(),
    }


def _contract() -> dict[str, Any]:
    return {
        "focus_policy": "never-steal-focus",
        "open_budget_ms": 150,
        "duplicate_controls": "forbidden",
        "interaction": "explicit-invocation",
        "dismissal": "dont-remind-until-evidence-changes",
        "mode": "prepare-then-commit",
    }


def dismiss_next_action(db: Any) -> dict[str, Any]:
    row = db.execute("SELECT * FROM next_action_surface WHERE id=1").fetchone()
    if not row:
        return {"status": "idle"}
    fingerprint = f"{row['action_family']}|{row['action_target']}|{row['target_context_id']}"
    db.execute(
        """UPDATE next_action_surface SET
               status='suppressed', suppress_fingerprint=?, updated_at=?
           WHERE id=1""",
        (fingerprint, _now()),
    )
    return show_next_action(db)


def commit_next_action(
    db: Any,
    *,
    run_fn: Callable[[list[str]], Any],
    tmux_args_fn: Callable[..., list[str]],
) -> dict[str, Any]:
    """Execute only reversible navigation from the prepared surface."""
    surface = show_next_action(db)
    if surface.get("status") != "ready":
        return {"ok": False, "error": "no ready next-action", "surface": surface}

    prepare = surface.get("prepare") or {}
    resolved = prepare.get("resolved") or {}
    dispatch = resolved.get("dispatch") or {}
    action = dispatch.get("action")
    message = ""
    undo: dict[str, Any] = {"action": "none"}

    # Capture current focus for undo.
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
            return {"ok": False, "error": getattr(result, "stderr", "") or "hyprctl failed", "surface": surface}
        message = f"focused workspace {ws}"
    elif action == "focus_app":
        app = str(dispatch.get("app") or "")
        ws = str(dispatch.get("workspace") or "")
        if ws:
            run_fn(["hyprctl", "dispatch", "workspace", ws])
        if app:
            # class match only — no titles.
            result = run_fn(["hyprctl", "dispatch", "focuswindow", f"class:^{app}$"])
            if getattr(result, "returncode", 1) != 0:
                # Fallback: workspace only still counts as partial success if ws set.
                if not ws:
                    return {"ok": False, "error": getattr(result, "stderr", "") or "focuswindow failed", "surface": surface}
            message = f"focused {app}" + (f" on workspace {ws}" if ws else "")
        else:
            return {"ok": False, "error": "missing app", "surface": surface}
    elif action == "select_tmux_pane":
        pane = str(dispatch.get("pane_id") or "")
        if not pane:
            return {"ok": False, "error": "missing pane", "surface": surface}
        result = run_fn(tmux_args_fn("select-pane", "-t", pane))
        if getattr(result, "returncode", 1) != 0:
            return {"ok": False, "error": getattr(result, "stderr", "") or "tmux select-pane failed", "surface": surface}
        message = f"selected tmux pane {pane}"
    else:
        return {"ok": False, "error": f"action not allowlisted for commit: {action or 'none'}", "surface": surface}

    db.execute(
        """UPDATE next_action_surface SET status='committed', updated_at=? WHERE id=1""",
        (_now(),),
    )
    return {
        "ok": True,
        "result": message,
        "undo": undo,
        "surface": show_next_action(db),
        "pred_id": surface.get("pred_id"),
    }


def on_context_event(
    db: Any,
    *,
    event_id: int | None,
    kind: str,
    tmux_focus_fn: Callable[[], dict[str, str]] | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    """Core tick: join episode, score shadow, predict, prepare. Shadow-only UI update."""
    if not force and kind not in CONTEXT_TRIGGER_KINDS and not kind.startswith("activewindow"):
        return None

    state = semantic_state(db, tmux_focus_fn=tmux_focus_fn)
    last = db.execute(
        "SELECT value FROM flow_meta WHERE key='last_context_id'"
    ).fetchone()
    last_cid = last["value"] if last else ""
    cid = state["context_id"]

    transitioned = force or (last_cid and last_cid != cid) or not last_cid
    result: dict[str, Any] = {
        "context_id": cid,
        "transitioned": bool(transitioned),
        "kind": kind,
    }

    if transitioned and last_cid and last_cid != cid:
        closed = close_open_episode(db, after_state=state, close_event_id=event_id)
        result["closed_episode"] = closed

    if transitioned:
        # Ensure a single open episode for the current context.
        open_row = db.execute(
            "SELECT id, context_id FROM context_episodes WHERE closed=0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not open_row or open_row["context_id"] != cid:
            if open_row:
                close_open_episode(db, after_state=state, close_event_id=event_id)
            opened = open_episode(db, state=state, open_event_id=event_id)
            result["opened_episode"] = opened

        topk, latency_ms = predict_next_context_v0(db, state)
        pred = record_shadow_prediction(
            db,
            state=state,
            topk=topk,
            latency_ms=latency_ms,
            trigger_event_id=event_id,
            schema_name=SCHEMA,
        )
        prepare = None
        if topk and topk[0].get("family") != STAY_LABEL:
            prepare = speculative_prepare(db, prediction=topk[0], current=state)
        surface = update_next_action_surface(db, pred_row=pred, topk=topk, prepare=prepare)
        result["prediction"] = {
            "pred_id": pred["pred_id"],
            "latency_ms": pred["latency_ms"],
            "topk": topk,
        }
        result["surface"] = {
            "status": surface.get("status"),
            "summary": surface.get("summary"),
            "confidence": surface.get("confidence"),
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
    lat = db.execute(
        """SELECT AVG(latency_ms) AS avg_ms, MAX(latency_ms) AS max_ms,
                  MIN(latency_ms) AS min_ms
           FROM shadow_predictions WHERE ts>=?""",
        (cutoff,),
    ).fetchone()
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
        "operator_schema": OPERATOR_SCHEMA,
        "operator_families": list(OPERATOR_FAMILIES),
        "window_hours": limit_hours,
        "predictions": total,
        "matched": matched,
        "top1_manual_equivalent": top1,
        "topk_hit": topk_hit,
        "top1_rate": round(top1 / matched, 4) if matched else None,
        "topk_rate": round(topk_hit / matched, 4) if matched else None,
        "latency_ms": {
            "avg": round(float(lat["avg_ms"] or 0.0), 3),
            "min": round(float(lat["min_ms"] or 0.0), 3),
            "max": round(float(lat["max_ms"] or 0.0), 3),
        },
        "closed_episodes": episodes,
        "action_families": by_family,
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
                      latency_ms, actual_context_id, actual_family, actual_target,
                      ranked, manual_equivalent, matched_at, horizon_ms
               FROM shadow_predictions
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
        for row in rows:
            try:
                state = json.loads(row["state_json"])
                topk = json.loads(row["topk_json"])
            except json.JSONDecodeError:
                continue
            rec = {
                "schema": row["schema_name"],
                "pred_id": row["pred_id"],
                "ts": row["ts"],
                "context_id": row["context_id"],
                "state": state,
                "topk": topk,
                "latency_ms": row["latency_ms"],
                "actual_context_id": row["actual_context_id"],
                "actual_family": row["actual_family"],
                "actual_target": row["actual_target"],
                "ranked": row["ranked"],
                "manual_equivalent": row["manual_equivalent"],
                "matched_at": row["matched_at"],
                "horizon_ms": row["horizon_ms"],
            }
            fh.write(_json_text(rec) + "\n")
            n += 1
    return {"path": str(dest), "n": n, "schema": SCHEMA}


def cleanup_flow(db: Any, cutoff: float) -> None:
    db.execute("DELETE FROM context_episodes WHERE ts_before<?", (cutoff,))
    db.execute("DELETE FROM shadow_predictions WHERE ts<?", (cutoff,))
    db.execute("DELETE FROM prepare_cache WHERE expires_at<?", (_now(),))
