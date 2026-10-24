"""Learned re-ranker for the next-action chip (rerank-v1).

The transition-table engine in workspace_flow.predict_next_context_v0 counts
exact context transitions. On held-out sessions it gets the next action right
about a third of the time. A recency-weighted softmax regression over one-hot
features (current app/workspace, the last few focus moves, recent apps, switch
rate, hour) does much better, at numpy cost.

Label: the 60 s horizon outcome already recorded by the engine
(noop | switch_app:<app> | switch_workspace:<ws>). Features come only from
episodes closed at or before the prediction time, so training has no leak.

The model is retrained from workspace.db (`workspace-copilot rerank-train`,
run by a user timer) and evaluated on the newest sessions against the logged
engine predictions. It is used live only if it beat the engine on that
holdout. Otherwise, or if numpy or the model file is missing, the engine's
top-k passes through unchanged.
"""

from __future__ import annotations

import bisect
import datetime as _dt
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

MODEL_SCHEMA = "workspace-copilot.rerank.v1"
HORIZON_MS = 60000
HIST_K = 6
MRU_WINDOW_S = 7200
MRU_K = 8
HALF_LIFE_DAYS = 7.0
MIN_CLASS_COUNT = 8
MAX_CLASSES = 60
HOLDOUT_FRAC = 0.15
SESSION_GAP_S = 1800
MIN_TRAIN_ROWS = 500
MAX_MODEL_AGE_S = 3 * 86400
LAMBDAS = (1e-4, 1e-3, 1e-2)
EPOCHS = 300
LR = 0.5
SOURCE = "rerank-v1"

NOOP = "noop"
_STAY = {"noop", "stay", ""}


def model_path() -> Path:
    """Next to workspace.db (same resolution as the workspace-copilot CLI)."""
    if os.environ.get("WORKSPACE_RERANK_MODEL"):
        return Path(os.environ["WORKSPACE_RERANK_MODEL"])
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    state_dir = Path(os.environ.get("WORKSPACE_COPILOT_STATE_DIR", base / "workspace-copilot"))
    return state_dir / "rerank-v1.json"


def label_key(family: str | None, target: str | None) -> str:
    fam = (family or "").strip()
    if fam in _STAY:
        return NOOP
    return f"{fam}:{(target or '').strip()}"


# ---------------------------------------------------------------- features


def _episode_index(db: Any, *, until: float | None = None, recent: int = 0) -> dict[str, list]:
    """Closed episodes ordered by close time: (ts_after, ts_before, app, workspace).

    With `recent`, only the newest N episodes closed at or before `until` are read
    (enough for HIST_K, the 5 min switch counts and the 2 h recent-apps list).
    """
    sql = """SELECT id, ts_before, ts_after, state_before_json FROM context_episodes
             WHERE closed=1 AND ts_after IS NOT NULL"""
    args: tuple = ()
    if until is not None:
        sql += " AND ts_after<=?"
        args = (until,)
    if recent:
        sql = f"SELECT * FROM ({sql} ORDER BY ts_after DESC, id DESC LIMIT {int(recent)})"
    rows = []
    for r in db.execute(sql + " ORDER BY ts_after, id", args):
        try:
            st = json.loads(r["state_before_json"] or "{}")
        except json.JSONDecodeError:
            st = {}
        rows.append((float(r["ts_after"]), float(r["ts_before"]), st.get("app") or "", st.get("workspace") or ""))
    return {"after": [x[0] for x in rows], "rows": rows}


def history_at(index: dict[str, list], ts: float, current_app: str) -> dict[str, Any]:
    """Recent focus history strictly from episodes closed at or before ts."""
    after, rows = index["after"], index["rows"]
    hi = bisect.bisect_right(after, ts)
    chain = [(rows[k][2], rows[k][3]) for k in range(max(0, hi - HIST_K), hi)]
    n60 = hi - bisect.bisect_right(after, ts - 60)
    n300 = hi - bisect.bisect_right(after, ts - 300)
    mru: list[str] = []
    seen = {current_app}
    for k in range(hi - 1, -1, -1):
        if ts - after[k] > MRU_WINDOW_S or len(mru) >= MRU_K:
            break
        app = rows[k][2]
        if app and app not in seen:
            seen.add(app)
            mru.append(app)
    return {"chain": chain, "mru": mru, "n60": n60, "n300": n300}


def features(state: dict[str, Any], hist: dict[str, Any], ts: float) -> list[str]:
    app = state.get("app") or ""
    chain = hist["chain"]
    prev = chain[-1][0] if chain else ""
    harness = (state.get("harness") or "none") + (":" + state["harness_state"] if state.get("harness_state") else "")
    hour = _dt.datetime.fromtimestamp(ts).hour
    x = [
        f"app={app}",
        f"ws={state.get('workspace') or ''}",
        f"mon={state.get('monitor') or ''}",
        f"harn={harness}",
        f"ts={state.get('task_status') or 'none'}",
        f"hour={hour // 4}",
        f"n60={min(hist['n60'], 6)}",
        f"n300={min(hist['n300'] // 2, 8)}",
        f"app+prev={app}|{prev}",
    ]
    for j, (a, w) in enumerate(reversed(chain[-3:])):
        x += [f"prev{j}={a}", f"prevws{j}={w}"]
    for j, a in enumerate(hist["mru"][:4]):
        x.append(f"mru{j}={a}")
    return x


def training_rows(db: Any) -> list[dict[str, Any]]:
    """One row per closed 60 s horizon, deduped like the offline dataset."""
    index = _episode_index(db)
    out: list[dict[str, Any]] = []
    last: dict[tuple, float] = {}
    for p in db.execute(
        """SELECT p.ts, p.context_id, p.state_json, p.topk_json,
                  h.actual_family, h.actual_target
           FROM shadow_predictions p
           JOIN prediction_horizons h ON h.pred_id=p.pred_id AND h.horizon_ms=?
           WHERE h.closed_at IS NOT NULL ORDER BY p.ts, p.id""",
        (HORIZON_MS,),
    ):
        fam = p["actual_family"] or ""
        if fam == "switch_pane":
            continue
        key = label_key(fam, p["actual_target"])
        if key != NOOP and key.endswith(":"):
            continue
        ts = float(p["ts"])
        twin = (p["context_id"], key)
        if twin in last and ts - last[twin] < 1.0:
            continue
        last[twin] = ts
        try:
            state = json.loads(p["state_json"] or "{}")
            topk = json.loads(p["topk_json"] or "[]")
        except json.JSONDecodeError:
            continue
        hist = history_at(index, ts, state.get("app") or "")
        engine = (topk[0].get("incumbent_keys") if topk else None) or [engine_key(c) for c in topk]
        out.append({"ts": ts, "label": key, "x": features(state, hist, ts), "engine": engine})
    return out


def engine_key(item: dict[str, Any]) -> str:
    """Map a logged top-k item onto the label space (engine's own guess)."""
    if item.get("incumbent_key"):
        return item["incumbent_key"]
    fam = item.get("family") or ""
    if fam in _STAY:
        return NOOP
    if fam == "switch_workspace":
        return f"switch_workspace:{item.get('target') or ''}"
    st = item.get("state") or {}
    return f"switch_app:{item.get('target') or st.get('app') or ''}"


# ---------------------------------------------------------------- model


def _split(rows: list[dict[str, Any]]) -> tuple[list, list]:
    """Newest whole sessions as holdout; purge train rows whose window reaches it."""
    if not rows:
        return [], []
    sess = [0]
    for i in range(1, len(rows)):
        sess.append(sess[-1] + (1 if rows[i]["ts"] - rows[i - 1]["ts"] >= SESSION_GAP_S else 0))
    need = int(len(rows) * HOLDOUT_FRAC)
    cut, cnt = sess[-1], 0
    for s in range(sess[-1], -1, -1):
        cnt += sum(1 for v in sess if v == s)
        cut = s
        if cnt >= need:
            break
    hold = [r for r, s in zip(rows, sess) if s >= cut]
    start = min(r["ts"] for r in hold)
    train = [r for r, s in zip(rows, sess) if s < cut and r["ts"] + HORIZON_MS / 1000 < start]
    return train, hold


def _fit(np: Any, rows: list[dict[str, Any]], lam: float | None = None) -> dict[str, Any]:
    counts = Counter(r["label"] for r in rows)
    classes = [k for k, c in counts.most_common() if c >= MIN_CLASS_COUNT][:MAX_CLASSES]
    if NOOP not in classes:
        classes.append(NOOP)
    cidx = {k: i for i, k in enumerate(classes)}
    vocab: dict[str, int] = {}
    for r in rows:
        for f in r["x"]:
            vocab.setdefault(f, len(vocab))
    F, C = len(vocab), len(classes) + 1  # last column: OTHER (rare labels)
    X = np.zeros((len(rows), F), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i, [vocab[f] for f in r["x"]]] = 1.0
    y = np.array([cidx.get(r["label"], C - 1) for r in rows])
    ts = np.array([r["ts"] for r in rows])
    w = (0.5 ** ((ts.max() - ts) / (HALF_LIFE_DAYS * 86400))).astype(np.float32)
    w /= w.mean()

    def fit(Xs: Any, ys: Any, ws: Any, l2: float) -> tuple[Any, Any]:
        W = np.zeros((F, C), dtype=np.float32)
        b = np.zeros(C, dtype=np.float32)
        Y = np.eye(C, dtype=np.float32)[ys]
        for _ in range(EPOCHS):
            Z = Xs @ W + b
            Z -= Z.max(1, keepdims=True)
            P = np.exp(Z)
            P /= P.sum(1, keepdims=True)
            G = (P - Y) * ws[:, None] / len(ys)
            W -= LR * (Xs.T @ G + l2 * W)
            b -= LR * G.sum(0)
        return W, b

    if lam is None:  # pick L2 on the newest 15% of the training rows
        cut = int(len(rows) * 0.85)
        best = None
        for l2 in LAMBDAS:
            W, b = fit(X[:cut], y[:cut], w[:cut], l2)
            acc = float(((X[cut:] @ W + b).argmax(1) == y[cut:]).mean()) if cut < len(rows) else 0.0
            if best is None or acc > best[0]:
                best = (acc, l2)
        lam = best[1]
    W, b = fit(X, y, w, lam)
    return {"vocab": vocab, "classes": classes, "W": W, "b": b, "lam": lam}


def _scores(np: Any, m: dict[str, Any], x: list[str]) -> list[tuple[str, float]]:
    idx = [m["vocab"][f] for f in x if f in m["vocab"]]
    z = m["b"] + (m["W"][idx].sum(0) if idx else 0)
    z = z - z.max()
    p = np.exp(z)
    p /= p.sum()
    out = [(m["classes"][j], float(p[j])) for j in range(len(m["classes"]))]
    out.sort(key=lambda t: -t[1])
    return out


def _topn(ranked: list[str], gold: str, n: int) -> bool:
    return gold in ranked[:n]


def evaluate(np: Any, m: dict[str, Any], hold: list[dict[str, Any]]) -> dict[str, Any]:
    def rate(pred: Callable[[dict], list[str]], n: int) -> float:
        return round(sum(_topn(pred(r), r["label"], n) for r in hold) / len(hold), 4) if hold else 0.0

    def model_pred(r: dict) -> list[str]:
        return [k for k, _ in _scores(np, m, r["x"])]

    def engine_pred(r: dict) -> list[str]:
        seen: list[str] = []
        for k in r["engine"]:
            if k not in seen:
                seen.append(k)
        return seen

    return {
        "n": len(hold),
        "model_top1": rate(model_pred, 1),
        "model_top3": rate(model_pred, 3),
        "engine_top1": rate(engine_pred, 1),
        "engine_top3": rate(engine_pred, 3),
    }


def train(db: Any, *, path: Path | None = None) -> dict[str, Any]:
    import numpy as np

    t0 = time.time()
    rows = training_rows(db)
    tr, hold = _split(rows)
    if len(tr) < MIN_TRAIN_ROWS or not hold:
        return {"ok": False, "reason": f"not enough rows (train={len(tr)}, holdout={len(hold)})"}
    m = _fit(np, tr)
    metrics = evaluate(np, m, hold)
    promoted = metrics["model_top1"] > metrics["engine_top1"]
    final = _fit(np, rows, lam=m["lam"])  # refit on everything for live use
    out = {
        "schema": MODEL_SCHEMA,
        "trained_at": time.time(),
        "rows": len(rows),
        "train_rows": len(tr),
        "holdout": metrics,
        "promoted": promoted,
        "lambda": m["lam"],
        "classes": final["classes"],
        "vocab": final["vocab"],
        "W": final["W"].round(5).tolist(),
        "b": final["b"].round(5).tolist(),
    }
    path = path or model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":")))
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    _CACHE.clear()
    return {
        "ok": True,
        "path": str(path),
        "promoted": promoted,
        "rows": len(rows),
        "train_rows": len(tr),
        "classes": len(final["classes"]),
        "features": len(final["vocab"]),
        "lambda": m["lam"],
        "holdout": metrics,
        "secs": round(time.time() - t0, 1),
    }


_CACHE: dict[str, Any] = {}


def load(path: Path | None = None) -> dict[str, Any] | None:
    path = path or model_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _CACHE.get("model")
    if hit and hit["mtime"] == mtime and hit["path"] == str(path):
        return hit["m"]
    try:
        import numpy as np

        raw = json.loads(path.read_text())
        if raw.get("schema") != MODEL_SCHEMA:
            return None
        m = {
            **raw,
            "W": np.asarray(raw["W"], dtype=np.float32),
            "b": np.asarray(raw["b"], dtype=np.float32),
        }
    except Exception:
        return None
    _CACHE["model"] = {"mtime": mtime, "path": str(path), "m": m}
    return m


def status(path: Path | None = None) -> dict[str, Any]:
    m = load(path)
    if not m:
        return {"model": None, "active": False, "path": str(path or model_path())}
    age = time.time() - m["trained_at"]
    return {
        "path": str(path or model_path()),
        "active": usable(m),
        "promoted": m["promoted"],
        "age_h": round(age / 3600, 1),
        "rows": m["rows"],
        "classes": len(m["classes"]),
        "holdout": m["holdout"],
    }


def usable(m: dict[str, Any] | None) -> bool:
    return bool(m and m.get("promoted") and time.time() - m["trained_at"] < MAX_MODEL_AGE_S)


# ---------------------------------------------------------------- live


def _match(key: str, cands: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the concrete candidate context for a label key."""
    if key == NOOP:
        for c in cands:
            if c.get("family") in _STAY:
                return c
        return None
    fam, _, tgt = key.partition(":")
    best = None
    for c in cands:
        st = c.get("state") or {}
        if fam == "switch_workspace":
            ok = str(st.get("workspace") or "") == tgt and (st.get("app") or "") == (state.get("app") or "")
            ok = ok or (c.get("family") == "switch_workspace" and c.get("target") == tgt)
        else:
            ok = (st.get("app") or "") == tgt and (st.get("app") or "") != (state.get("app") or "")
        if ok and (best is None or c.get("p", 0) > best.get("p", 0)):
            best = c
    return best


def apply(
    db: Any,
    state: dict[str, Any],
    topk: list[dict[str, Any]],
    *,
    candidates_fn: Callable[[Any, dict[str, Any]], list[dict[str, Any]]],
    operator_fn: Callable[[str, dict[str, Any], dict[str, Any]], str],
    now: float | None = None,
    top_k: int = 5,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Re-rank the engine's top-k with the learned model; pass through on any doubt."""
    m = load(path)
    if not usable(m) or not topk:
        return topk
    try:
        import numpy as np

        ts = now if now is not None else time.time()
        hist = history_at(_episode_index(db, until=ts, recent=400), ts, state.get("app") or "")
        ranked = _scores(np, m, features(state, hist, ts))
        pool = [dict(c) for c in topk]
        known = {c.get("context_id") for c in pool}
        for c in candidates_fn(db, state):
            if c.get("context_id") not in known:
                pool.append({**c, "p": 0.0})
                known.add(c.get("context_id"))
        out: list[dict[str, Any]] = []
        used: set[str] = set()
        for key, p in ranked:
            c = _match(key, pool, state)
            if not c or c.get("context_id") in used:
                continue
            used.add(c["context_id"])
            item = {k: v for k, v in c.items() if k not in ("p", "incumbent_p")}
            item["p"] = p
            item["incumbent_p"] = round(float(c.get("p", 0.0)), 6)
            item["incumbent_key"] = engine_key(c)
            item["source"] = SOURCE
            if "operator_family" not in item:
                item["operator_family"] = operator_fn(item.get("family") or "", item.get("state") or {}, state)
            out.append(item)
            if len(out) >= top_k:
                break
        if not out:
            return topk
        out[0]["incumbent_keys"] = [engine_key(c) for c in topk]
        mass = sum(i["p"] for i in out) or 1.0
        for i in out:
            i["p"] = round(i["p"] / mass, 6)
        return out
    except Exception:
        return topk
