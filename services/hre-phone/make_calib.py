"""200-message stratified calibration set from corpus/owner-msgs.jsonl.
Strata: poteto's regex complaint marker (t1/complaints.jsonl) x source family x length.
100 marker-positive, 100 marker-negative, so flag recall is measured on misses the regex makes too."""
import json, random, pathlib, collections, os
HRE = pathlib.Path("/mnt/zer0models/workspace/zer0/data/operations/history-research-engine-20261118")
rows = [json.loads(l) for l in open(HRE / "corpus/owner-msgs.jsonl")]
comp = set()
for l in open(HRE / "t1/complaints.jsonl"):
    r = json.loads(l); comp.add((r["profile"], str(r["mid"])))
def fam(p):
    return "hermes" if not p.startswith(("av_", "h_", "x_")) else p.split("_")[0]
def ln(t):
    n = len(t); return "s" if n < 200 else "m" if n < 1500 else "l"
rnd = random.Random(20261118)
buckets = collections.defaultdict(list)
for r in rows:
    pos = (r["profile"], str(r["mid"])) in comp
    buckets[(pos, fam(r["profile"]), ln(r["text"]))].append(r)
pick = []
for pos in (True, False):
    keys = [k for k in buckets if k[0] == pos]
    total = sum(len(buckets[k]) for k in keys)
    alloc = {k: max(1, round(100 * len(buckets[k]) / total)) for k in keys}
    while sum(alloc.values()) > 100:
        k = max(alloc, key=alloc.get); alloc[k] -= 1
    while sum(alloc.values()) < 100:
        k = max(keys, key=lambda k: len(buckets[k]) - alloc[k]); alloc[k] += 1
    for k in keys:
        pick += rnd.sample(buckets[k], min(alloc[k], len(buckets[k])))
rnd.shuffle(pick)
out = HRE / "corpus/calib/calib-200.jsonl"
out.parent.mkdir(mode=0o700, exist_ok=True)
with open(out, "w") as f:
    for r in pick:
        f.write(json.dumps({"id": r["id"], "profile": r["profile"], "iso": r["iso"],
                            "regex_marker": (r["profile"], str(r["mid"])) in comp,
                            "text": r["text"][:2500]}, ensure_ascii=False) + "\n")
os.chmod(out, 0o600)
print(len(pick), collections.Counter((fam(r["profile"]), ln(r["text"])) for r in pick).most_common())
