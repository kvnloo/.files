"""Embed owner-msgs.jsonl via a phone llama-server /v1/embeddings (Qwen3-Embedding-0.6B on the Lenovo tab).
Owner text goes only to --url. Resumable: ids already in the output shard are skipped.
Output: <out-dir>/emb-<shard>.npy-free jsonl: {"id","model","dim","emb":[float16-rounded floats]} one row per id."""
import argparse, json, os, sys, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True); ap.add_argument("--key-file")
ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--shard", type=int, default=0); ap.add_argument("--nshards", type=int, default=1)
ap.add_argument("--batch", type=int, default=8); ap.add_argument("--max-chars", type=int, default=6000)
ap.add_argument("--model-tag", default="Qwen3-Embedding-0.6B-Q8_0")
a = ap.parse_args()
key = open(a.key_file).read().strip() if a.key_file else ""
done = set()
if os.path.exists(a.out):
    done = {json.loads(l)["id"] for l in open(a.out) if l.strip()}
rows = [r for i, r in enumerate(map(json.loads, open(a.inp))) if i % a.nshards == a.shard and r["id"] not in done]
print(f"shard {a.shard}/{a.nshards}: {len(rows)} todo, {len(done)} done", flush=True)
h = {"Content-Type": "application/json"}
if key: h["Authorization"] = "Bearer " + key
os.umask(0o077)
t0 = time.time(); n = 0
with open(a.out, "a") as f:
    for b in range(0, len(rows), a.batch):
        chunk = rows[b:b + a.batch]
        texts = [r["text"][:a.max_chars] for r in chunk]
        for attempt in range(5):
            try:
                req = urllib.request.Request(a.url + "/v1/embeddings", json.dumps({"input": texts}).encode(), h)
                with urllib.request.urlopen(req, timeout=600) as r:
                    data = json.load(r)["data"]
                break
            except Exception as e:
                print("retry", attempt, repr(e)[:200], flush=True); time.sleep(10 * (attempt + 1))
        else:
            sys.exit("giving up")
        for r, d in zip(chunk, sorted(data, key=lambda x: x["index"])):
            e = d["embedding"]
            f.write(json.dumps({"id": r["id"], "model": a.model_tag, "dim": len(e),
                                "emb": [round(x, 5) for x in e]}) + "\n")
        f.flush(); n += len(chunk)
        if (b // a.batch) % 25 == 0:
            print(f"{n} rows {n / (time.time() - t0) * 3600:.0f}/h", flush=True)
print(f"done {n} rows in {time.time() - t0:.0f}s", flush=True)
