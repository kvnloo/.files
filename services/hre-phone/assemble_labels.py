#!/usr/bin/env python3
"""Join the phone sweep outputs into HRE corpus/phone-labels.jsonl (one row per corpus id that has
at least one label) and print coverage / throughput.
  assemble_labels.py --sweep DIR/sweep --corpus owner-msgs.jsonl --out phone-labels.jsonl [--thr 0.10]
Row: {id, source, profile, flag, flag_basis, p_flag_d1, kind, kind_p, cue, concepts, ask,
      flag_lfm3, p_flag_lfm3, models, workers, done:{flag,full}}
flag (recall-first, calib-200): "y" if d1-2B p_flag >= thr (recall 1.00 @0.10); when the d1 pass has
not reached the row yet, falls back to the LFM3 flag (recall 1.00, low precision)."""
import argparse, collections, glob, json, os, time

ap = argparse.ArgumentParser()
ap.add_argument("--sweep", required=True); ap.add_argument("--corpus", required=True)
ap.add_argument("--out", required=True); ap.add_argument("--thr", type=float, default=0.10)
ap.add_argument("--flag-job", default="flag-d1-2b"); ap.add_argument("--full-job", default="full-lfm3")
a = ap.parse_args()


def load(job):
    rows = {}
    for f in sorted(glob.glob(os.path.join(a.sweep, job, "out", "*.jsonl"))):
        for l in open(f):
            try:
                r = json.loads(l)
            except ValueError:
                continue          # a torn last line while a worker is writing
            rows.setdefault(r["id"], r)
    return rows


corpus = [json.loads(l) for l in open(a.corpus)]
fl, fu = load(a.flag_job), load(a.full_job)
os.umask(0o077)
tmp = a.out + ".tmp"
n = 0
with open(tmp, "w") as fo:
    for c in corpus:
        d, u = fl.get(c["id"]), fu.get(c["id"])
        if not d and not u:
            continue
        if d:
            flag, basis = ("y" if d["p_flag"] >= a.thr else "n"), f"d1-2B p>={a.thr}"
        else:
            flag, basis = u["flag"], "lfm3 (d1 pending)"
        fo.write(json.dumps({
            "id": c["id"], "source": c.get("source"), "profile": c.get("profile"), "iso": c.get("iso"),
            "flag": flag, "flag_basis": basis,
            "p_flag_d1": d and d["p_flag"], "kind": d and d.get("kind"), "kind_p": d and d.get("kind_p"),
            "cue": u and u.get("cue"), "concepts": u and u.get("concepts"), "ask": u and u.get("ask"),
            "flag_lfm3": u and u.get("flag"), "p_flag_lfm3": u and u.get("p_flag"),
            "models": [x for x in (d and d["model"], u and u["model"]) if x],
            "workers": [x for x in (d and d["worker"], u and u["worker"]) if x],
            "done": {"flag": bool(d), "full": bool(u)}}, ensure_ascii=False) + "\n")
        n += 1
os.replace(tmp, a.out)
N = len(corpus)
now = time.time()
rep = {"corpus": N, "rows_out": n, "flag_done": len(fl), "full_done": len(fu),
       "flag_pct": round(100 * len(fl) / N, 2), "full_pct": round(100 * len(fu) / N, 2),
       "both_pct": round(100 * sum(1 for c in corpus if c["id"] in fl and c["id"] in fu) / N, 2),
       "flag_y": sum(1 for r in fl.values() if r["p_flag"] >= a.thr)}
per = collections.defaultdict(lambda: [0, 0])
for rows in (fl, fu):
    for r in rows.values():
        if now - r["ts"] <= 3600:
            per[r["worker"]][0] += 1
        per[r["worker"]][1] += 1
rep["per_worker"] = {w: {"last_hour": v[0], "total": v[1]} for w, v in per.items()}
print(json.dumps(rep))
