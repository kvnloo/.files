#!/usr/bin/env python3
"""rows.jsonl -> summary.json for android-u2-driver-models-v0.

  summarize.py ROWS.jsonl [--out summary.json]

Per model: scored rows only (status ok) feed the rates; unavailable / timeout / blocked / error /
cancelled rows are counted separately and never turn into a 0. A model with no scored rows is
reported as status "unavailable" (or "no_scored_rows") with null metrics.
Latency: choose_ms is per decision (pooled over steps); total_ms is per task and split into
warm rows and rows that paid a cold load (cold_ms > 0 or cold_expected)."""
import json, math, sys
from collections import defaultdict

def pct(xs, q):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs: return None
    k = (len(xs) - 1) * q; f = math.floor(k); c = math.ceil(k)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 1)

def wilson(k, n, z=1.96):
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]

def rate(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(bool(x) for x in v) / len(v), 3) if v else None

def summarize(rows):
    by = defaultdict(list)
    for r in rows: by[r["model_key"]].append(r)
    models = {}
    for key, rs in by.items():
        scored = [r for r in rs if r["status"] == "ok"]
        counts = defaultdict(int)
        for r in rs: counts[r["status"]] += 1
        m = {"model": rs[0]["model"], "class": rs[0]["class"], "params_b": rs[0].get("params_b"), "quant": rs[0].get("quant"),
             "rows": len(rs), "status_counts": dict(counts)}
        if not scored:
            m["status"] = "unavailable" if counts.get("unavailable") else "no_scored_rows"
            m["why"] = next((r.get("error") for r in rs if r.get("error")), None)
            models[key] = m; continue
        passes = sum(r["oracle_pass"] is True for r in scored)
        cold = [r for r in scored if (r.get("cold_ms") or 0) > 0 or r.get("cold_expected")]
        warm = [r for r in scored if r not in cold]
        eff = [r["steps"] / r["min_steps"] for r in scored if r["oracle_pass"] and r.get("steps") and r.get("min_steps")]
        m.update({
            "status": "scored", "n_scored": len(scored), "oracle_success": round(passes / len(scored), 3),
            "oracle_success_ci95": wilson(passes, len(scored)),
            "multi_step_success": rate([r for r in scored if r["multi_step"]], "oracle_pass"),
            "single_step_success": rate([r for r in scored if not r["multi_step"]], "oracle_pass"),
            "steps_p50": pct([r.get("steps") for r in scored], .5), "step_efficiency_p50": pct(eff, .5),
            "wrong_act_rate": rate(scored, "wrong_act"), "false_done_rate": rate(scored, "false_done"),
            "side_effect_jobs": sum(bool(r.get("side_effect_keys")) for r in rs),
            "abstain_rate": rate(scored, "abstain"),
            "choose_ms_p50": pct([x for r in scored for x in r.get("choose_ms") or []], .5),
            "choose_ms_p95": pct([x for r in scored for x in r.get("choose_ms") or []], .95),
            "total_ms_warm_p50": pct([r.get("total_ms") for r in warm], .5),
            "total_ms_warm_p95": pct([r.get("total_ms") for r in warm], .95),
            "cold_ms_p50": pct([r.get("cold_ms") for r in cold], .5), "cold_rows": len(cold),
            "tokens_in": sum(r.get("tokens_in") or 0 for r in scored) or None,
            "tokens_out": sum(r.get("tokens_out") or 0 for r in scored) or None,
            "cost_usd": round(sum(r.get("cost_usd") or 0 for r in scored), 4) if any(r.get("cost_usd") is not None for r in scored) else None,
        })
        models[key] = m
    tasks = defaultdict(dict)
    for r in rows:
        if r["status"] == "ok":
            cell = tasks[r["task"]].setdefault(r["model_key"], [0, 0]); cell[1] += 1; cell[0] += r["oracle_pass"] is True
    return {"schema": "z0evals.android-u2-driver-models.summary.v1", "suite": "android-u2-driver-models-v0",
            "rows": len(rows), "run_ids": sorted({r["run_id"] for r in rows}), "models": models,
            "task_matrix": {t: {k: f"{a}/{b}" for k, (a, b) in v.items()} for t, v in sorted(tasks.items())}}

if __name__ == "__main__":
    a = sys.argv[1:]; out = None
    if "--out" in a: i = a.index("--out"); out = a[i + 1]; a = a[:i] + a[i + 2:]
    s = summarize([json.loads(l) for l in open(a[0]) if l.strip()])
    txt = json.dumps(s, indent=1)
    (open(out, "w").write(txt) if out else print(txt))
