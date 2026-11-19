"""Score calib-<model>.jsonl files against gold-opus.jsonl.
Flag: recall/precision at the model's own y/n and, where p_flag exists, the best threshold reaching recall>=0.9.
Concepts: micro precision/recall with loose match (lowercase, one string contains the other)."""
import json, sys, glob, os
gold = {r["id"]: r for r in map(json.loads, open(sys.argv[1]))}
def norm(s): return " ".join(s.lower().replace("-", " ").replace("_", " ").split())
def cmatch(a, b): a, b = norm(a), norm(b); return bool(a and b) and (a in b or b in a)
res = []
for f in sorted(sys.argv[2:]):
    rows = {r["id"]: r for r in map(json.loads, open(f)) if "error" not in r}
    ids = [i for i in gold if i in rows]
    if not ids: continue
    P = [i for i in ids if gold[i]["flag"] == "y"]
    def rp(pred):
        tp = sum(1 for i in P if pred(i)); fp = sum(1 for i in ids if pred(i) and gold[i]["flag"] != "y")
        return tp / max(1, len(P)), tp / max(1, tp + fp), tp + fp
    rec, prec, npos = rp(lambda i: rows[i]["flag"] == "y")
    o = {"file": os.path.basename(f), "n": len(ids), "gold_pos": len(P), "flag_recall": round(rec, 3),
         "flag_precision": round(prec, 3), "pred_pos": npos}
    ps = [rows[i].get("p_flag") for i in ids]
    if all(p is not None for p in ps):
        pos = [rows[i]["p_flag"] for i in P]; neg = [rows[i]["p_flag"] for i in ids if i not in set(P)]
        o["auc"] = round(sum((x > y) + 0.5 * (x == y) for x in pos for y in neg) / max(1, len(pos) * len(neg)), 3)
        for t in sorted({p for p in ps}, reverse=True):
            r2, p2, n2 = rp(lambda i: rows[i]["p_flag"] >= t)
            if r2 >= 0.9:
                o.update(thr=t, thr_recall=round(r2, 3), thr_precision=round(p2, 3), thr_pred_pos=n2); break
    if any("concepts" in rows[i] for i in ids):
        tp = fp = fn = 0
        for i in ids:
            g, m = gold[i]["concepts"], rows[i].get("concepts", [])
            tp += sum(1 for c in m if any(cmatch(c, x) for x in g))
            fp += sum(1 for c in m if not any(cmatch(c, x) for x in g))
            fn += sum(1 for x in g if not any(cmatch(c, x) for c in m))
        o.update(concept_precision=round(tp / max(1, tp + fp), 3), concept_recall=round(tp / max(1, tp + fn), 3))
        o["ask_nonempty_when_gold_ask"] = round(sum(1 for i in ids if gold[i]["ask"] and rows[i].get("ask")) /
                                                max(1, sum(1 for i in ids if gold[i]["ask"])), 3)
    ms = sorted(rows[i].get("_ms", 0) for i in ids)
    o["median_ms"] = ms[len(ms) // 2]; o["worker"] = rows[ids[0]].get("worker")
    res.append(o)
for o in res: print(json.dumps(o))
