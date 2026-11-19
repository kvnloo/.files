"""Build HRE corpus/owner-msgs.jsonl from poteto's T1 owner filter output (t1/owner.jsonl).
Drops pasted capsules/task bodies (text starting "[" or "# Kanban") and exact-duplicate texts.
Row: id, source, profile, ts, iso, text.  Read-only on inputs."""
import json, hashlib, re, collections, pathlib, os
HRE = pathlib.Path("/mnt/zer0models/workspace/zer0/data/operations/history-research-engine-20261118")
src, out = HRE / "t1/owner.jsonl", HRE / "corpus/owner-msgs.jsonl"
out.parent.mkdir(mode=0o700, exist_ok=True)
seen, st, rows = set(), collections.Counter(), []
for line in open(src):
    r = json.loads(line)
    t = r["text"].strip()
    if t.startswith("[") or t.startswith("# Kanban"):
        st["drop_capsule"] += 1; continue
    k = hashlib.sha1(re.sub(r"\s+", " ", t.lower()).encode()).hexdigest()
    if k in seen:
        st["drop_dup"] += 1; continue
    seen.add(k)
    rid = hashlib.sha1(f'{r["profile"]}|{r["mid"]}|{r.get("kind")}'.encode()).hexdigest()[:16]
    rows.append({"id": rid, "source": r["source"], "profile": r["profile"], "db": r.get("db"),
                 "sid": r.get("sid"), "mid": r["mid"], "ts": r["ts"], "iso": r["iso"], "text": t})
    st["kept"] += 1
assert len({x["id"] for x in rows}) == len(rows)
tmp = out.with_suffix(".tmp")
with open(tmp, "w") as f:
    for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
os.chmod(tmp, 0o600); tmp.replace(out)
print(json.dumps({"input": str(src), "output": str(out), **st}))
